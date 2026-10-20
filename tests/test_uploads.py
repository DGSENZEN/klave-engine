"""Upload limits and failures must preserve the existing drawing set."""

import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, Request, UploadFile
from klave_engine.common.config import Settings
from klave_engine.ingestion.manifest import ProcessingStatus, manifest_path, save_manifest
from klave_engine.ingestion.project_loader import ingest_project

from apps.api.auth.store import UsersDbUnavailable
from apps.api.dependencies import ProjectStore
from apps.api.jobs import Job
from apps.api.routes import projects
from apps.api.routes.projects import _save_sheet_uploads, _save_upload

DWG_CONTENT = b"AC1032" + b"\0" * 64


@pytest.mark.parametrize(("start_index", "count"), [(1, 40), (40, 1)])
def test_upload_accepts_the_fortieth_sheet(tmp_path, start_index, count):
    files = [
        UploadFile(filename=f"sheet-{index}.dwg", file=BytesIO(DWG_CONTENT))
        for index in range(count)
    ]

    saved = asyncio.run(_save_sheet_uploads(files, tmp_path, 1024, start_index))

    assert len(saved) == count
    assert saved[-1].name.startswith("40-")
    assert all(path.read_bytes() == DWG_CONTENT for path in saved)


@pytest.mark.parametrize(("start_index", "count"), [(1, 41), (40, 2), (41, 1)])
def test_upload_rejects_more_than_forty_sheets_without_saving(tmp_path, start_index, count):
    files = [
        UploadFile(filename=f"sheet-{index}.dwg", file=BytesIO(DWG_CONTENT))
        for index in range(count)
    ]

    with pytest.raises(HTTPException) as error:
        asyncio.run(_save_sheet_uploads(files, tmp_path, 1024, start_index))

    assert error.value.status_code == 413
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("filename", "content", "status"),
    [
        ("bad.txt", DWG_CONTENT, 400),
        ("bad.dwg", b"invalid", 422),
        ("large.dwg", DWG_CONTENT * 20, 413),
    ],
    ids=["unsupported-name", "invalid-signature", "too-large"],
)
def test_failed_batch_removes_earlier_uploads_and_preserves_existing(
    tmp_path, filename, content, status
):
    existing = tmp_path / "01-existing.dwg"
    existing.write_bytes(DWG_CONTENT)
    files = [
        UploadFile(filename="valid.dwg", file=BytesIO(DWG_CONTENT)),
        UploadFile(filename=filename, file=BytesIO(content)),
    ]

    with pytest.raises(HTTPException) as error:
        asyncio.run(_save_sheet_uploads(files, tmp_path, 1024, 2))

    assert error.value.status_code == status
    assert list(tmp_path.iterdir()) == [existing]
    assert existing.read_bytes() == DWG_CONTENT


def test_collision_does_not_delete_an_existing_drawing(tmp_path):
    destination = tmp_path / "01-existing.dwg"
    destination.write_bytes(DWG_CONTENT)
    upload = UploadFile(filename="existing.dwg", file=BytesIO(b"replacement"))

    with pytest.raises(FileExistsError):
        asyncio.run(_save_upload(upload, destination, 1024))

    assert destination.read_bytes() == DWG_CONTENT


@pytest.mark.parametrize("failure_stage", ["save", "ingest"])
def test_new_upload_removes_the_project_directory_on_io_error(
    data_dir, monkeypatch, failure_stage
):
    settings = Settings(data_dir=data_dir)
    store = ProjectStore(settings)

    class BrokenReadStream(BytesIO):
        def read(self, *_args):
            raise OSError("upload read failed")

    def fail_ingest(*args, **kwargs):
        ingest_project(*args, **kwargs)
        raise OSError("ingestion failed")

    if failure_stage == "ingest":
        monkeypatch.setattr(projects, "ingest_project", fail_ingest)
    stream = BrokenReadStream(DWG_CONTENT) if failure_stage == "save" else BytesIO(DWG_CONTENT)
    upload = UploadFile(filename="sheet.dwg", file=stream)

    with pytest.raises(OSError):
        asyncio.run(projects.upload_project(
            Request({"type": "http"}), [upload], store=store, settings=settings
        ))

    assert list((data_dir / "uploads").iterdir()) == []
    assert store.list_projects() == {}


@pytest.mark.parametrize("error", [OSError("ingestion failed"), HTTPException(422)])
def test_adding_sheets_restores_drawings_and_manifest_after_ingest_failure(
    data_dir, monkeypatch, error
):
    settings = Settings(data_dir=data_dir)
    store = ProjectStore(settings)
    root = data_dir / "uploads" / "existing"
    drawings = root / "drawings"
    drawings.mkdir(parents=True)
    existing = drawings / "01-existing.dwg"
    existing.write_bytes(DWG_CONTENT)
    manifest = ingest_project(root, project_id="existing")
    manifest.processing_status = ProcessingStatus.processed
    save_manifest(manifest)
    store.register(manifest.project_id, root)
    original_manifest = manifest_path(root).read_bytes()

    def fail_ingest(*args, **kwargs):
        ingest_project(*args, **kwargs)
        raise error

    monkeypatch.setattr(projects, "ingest_project", fail_ingest)
    upload = UploadFile(filename="new.dwg", file=BytesIO(DWG_CONTENT))

    with pytest.raises(type(error)):
        asyncio.run(projects.add_project_files(
            "existing", Request({"type": "http"}), [upload], store=store, settings=settings
        ))

    assert list(drawings.iterdir()) == [existing]
    assert existing.read_bytes() == DWG_CONTENT
    assert manifest_path(root).read_bytes() == original_manifest


def test_failed_addition_preserves_metadata_updated_during_upload(data_dir, monkeypatch):
    settings = Settings(data_dir=data_dir)
    store = ProjectStore(settings)
    root = data_dir / "uploads" / "existing"
    drawings = root / "drawings"
    drawings.mkdir(parents=True)
    existing = drawings / "01-existing.dwg"
    existing.write_bytes(DWG_CONTENT)
    manifest = ingest_project(root, project_id="existing", project_name="Original")
    store.register(manifest.project_id, root)

    class RenameDuringRead(BytesIO):
        def read(self, *args):
            latest = store.get_manifest("existing")
            latest.project_name = "Acknowledged name"
            latest.client = "Acknowledged client"
            save_manifest(latest)
            return super().read(*args)

    def fail_ingest(*args, **kwargs):
        ingest_project(*args, **kwargs)
        raise OSError("ingestion failed")

    monkeypatch.setattr(projects, "ingest_project", fail_ingest)
    upload = UploadFile(filename="new.dwg", file=RenameDuringRead(DWG_CONTENT))

    with pytest.raises(OSError, match="ingestion failed"):
        asyncio.run(projects.add_project_files(
            "existing", Request({"type": "http"}), [upload], store=store, settings=settings
        ))

    restored = store.get_manifest("existing")
    assert restored.project_name == "Acknowledged name"
    assert restored.client == "Acknowledged client"
    assert list(drawings.iterdir()) == [existing]


def test_failed_manifest_snapshot_removes_saved_uploads(data_dir, monkeypatch):
    settings = Settings(data_dir=data_dir)
    store = ProjectStore(settings)
    root = data_dir / "uploads" / "existing"
    drawings = root / "drawings"
    drawings.mkdir(parents=True)
    existing = drawings / "01-existing.dwg"
    existing.write_bytes(DWG_CONTENT)
    manifest = ingest_project(root, project_id="existing")
    store.register(manifest.project_id, root)
    original_manifest = manifest_path(root).read_bytes()
    read_text = Path.read_text

    def fail_snapshot(path, *args, **kwargs):
        if path == manifest_path(root):
            raise OSError("manifest read failed")
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_snapshot)
    upload = UploadFile(filename="new.dwg", file=BytesIO(DWG_CONTENT))

    with pytest.raises(OSError, match="manifest read failed"):
        asyncio.run(projects.add_project_files(
            "existing", Request({"type": "http"}), [upload], store=store, settings=settings
        ))

    assert list(drawings.iterdir()) == [existing]
    assert manifest_path(root).read_bytes() == original_manifest


@pytest.mark.parametrize(("root_count", "drawings_count"), [(40, 0), (20, 20)])
def test_imported_project_counts_root_drawings_toward_upload_limit(
    data_dir, monkeypatch, root_count, drawings_count
):
    settings = Settings(data_dir=data_dir)
    store = ProjectStore(settings)
    root = data_dir / "imported"
    drawings = root / "drawings"
    drawings.mkdir(parents=True)
    for index in range(root_count):
        (root / f"root-{index}.dwg").write_bytes(DWG_CONTENT)
    for index in range(drawings_count):
        (drawings / f"drawing-{index}.dwg").write_bytes(DWG_CONTENT)
    manifest = ingest_project(root, project_id="existing")
    store.register(manifest.project_id, root)
    job = Job(project_id="existing", job_id="j", run_id="r")
    monkeypatch.setattr(projects.JOB_STORE, "enqueue", lambda *_a: (job, True))
    upload = UploadFile(filename="new.dwg", file=BytesIO(DWG_CONTENT))

    with pytest.raises(HTTPException) as error:
        asyncio.run(projects.add_project_files(
            "existing", Request({"type": "http"}), [upload], store=store, settings=settings
        ))

    assert error.value.status_code == 413
    assert len(list(drawings.iterdir())) == drawings_count
    assert len(store.get_manifest("existing").source_files) == 40


@pytest.mark.parametrize("failure_stage", ["grant_access", "register_project"])
def test_upload_never_publishes_a_project_without_its_workspace_owner(
    data_dir, monkeypatch, failure_stage,
):
    settings = Settings(data_dir=data_dir)
    store = ProjectStore(settings)

    class UnavailableUsers:
        def grant_access(self, *_args):
            if failure_stage == "grant_access":
                raise UsersDbUnavailable("users database disconnected")

        def register_project(self, *_args):
            raise UsersDbUnavailable("users database disconnected")

    monkeypatch.setattr(projects, "get_user_store", lambda _url: UnavailableUsers())
    request = Request({"type": "http", "state": {"user": {
        "user_id": "u-b", "workspace_id": "ws-b",
    }}})
    upload = UploadFile(filename="sheet.dwg", file=BytesIO(DWG_CONTENT))

    with pytest.raises(HTTPException) as caught:
        asyncio.run(projects.upload_project(
            request, [upload], store=store, settings=settings,
        ))

    assert caught.value.status_code == 503
    assert store.list_projects() == {}
    assert list((data_dir / "uploads").iterdir()) == []
