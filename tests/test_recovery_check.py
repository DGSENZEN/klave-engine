"""Recovery validates everything before creating resources or extracting files."""

import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/recovery_check.py"


def recovery():
    if not SCRIPT.exists():
        pytest.fail("isolated recovery implementation is missing")
    spec = importlib.util.spec_from_file_location("pilot_recovery", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unowned_target_is_rejected_before_restore(tmp_path):
    (tmp_path / "precious").write_text("keep")
    with pytest.raises(ValueError, match="owned"):
        recovery().validate_target(tmp_path)
    assert (tmp_path / "precious").read_text() == "keep"


@pytest.mark.parametrize("project", ["klave", "klave-smoke-../../live", "klave-smoke-"])
def test_marker_cannot_name_active_or_arbitrary_resources(tmp_path, project):
    (tmp_path / "smoke.json").write_text(
        json.dumps(
            {
                "owner": "klave-container-smoke-v1",
                "project": project,
                "api_image": "synthetic",
                "web_image": "synthetic",
            }
        )
    )
    with pytest.raises(ValueError, match="owned"):
        recovery().validate_target(tmp_path)


@pytest.mark.parametrize(
    "name,kind",
    [
        ("../outside", "file"),
        ("/absolute", "file"),
        ("link", "symlink"),
        ("link", "hardlink"),
        ("device", "device"),
    ],
)
def test_unsafe_archive_does_not_write_any_files(tmp_path, name, kind):
    path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        safe = tarfile.TarInfo("safe")
        safe.size = 3
        archive.addfile(safe, io.BytesIO(b"yes"))
        member = tarfile.TarInfo(name)
        if kind == "file":
            member.size = 3
            archive.addfile(member, io.BytesIO(b"bad"))
        else:
            member.type = {
                "symlink": tarfile.SYMTYPE,
                "hardlink": tarfile.LNKTYPE,
                "device": tarfile.CHRTYPE,
            }[kind]
            member.linkname = "../outside"
            archive.addfile(member)
    destination = tmp_path / "fresh"
    with pytest.raises(ValueError, match="Unsafe"):
        recovery().extract_safe(path, destination)
    assert not destination.exists()
    assert not (tmp_path / "outside").exists()


def test_existing_restore_directory_is_never_overwritten(tmp_path):
    archive = tmp_path / "empty.tar.gz"
    with tarfile.open(archive, "w:gz"):
        pass
    target = tmp_path / "active"
    target.mkdir()
    (target / "drawing").write_text("keep")
    with pytest.raises(ValueError, match="fresh|empty"):
        recovery().extract_safe(archive, target)
    assert (target / "drawing").read_text() == "keep"


def test_safe_extraction_preserves_nested_unicode_and_sqlite(tmp_path):
    path = tmp_path / "safe.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("a folder/ñ 'drawing'\n.dxf")
        member.size = 4
        archive.addfile(member, io.BytesIO(b"DXF!"))
    recovery().extract_safe(path, tmp_path / "restored")
    assert (tmp_path / "restored/a folder/ñ 'drawing'\n.dxf").read_bytes() == b"DXF!"


def test_incomplete_backup_is_rejected_before_resources(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "smoke.json").write_text(
        json.dumps(
            {
                "owner": "klave-container-smoke-v1",
                "project": "klave-smoke-0123456789",
                "api_image": "synthetic",
                "web_image": "synthetic",
            }
        )
    )
    backup = tmp_path / "incomplete"
    backup.mkdir()
    with pytest.raises(ValueError, match="complete"):
        recovery().restore(state, backup)
    assert list(state.iterdir()) == [state / "smoke.json"]


def prepared_backup(tmp_path, monkeypatch):
    module = recovery()

    def pg(args):
        if args[0] == "pg_dump":
            Path(args[args.index("-f") + 1]).write_bytes(b"synthetic postgres dump")
        return ""

    monkeypatch.setattr(module.backup, "_run_pg", pg)
    data = tmp_path / "original"
    data.mkdir()
    (data / "drawing.dxf").write_bytes(b"original drawing")
    source = module.backup.run_backup(data, tmp_path / "backups", 14)
    state = tmp_path / "state"
    state.mkdir()
    (state / "smoke.json").write_text(
        json.dumps(
            {
                "owner": "klave-container-smoke-v1",
                "project": "klave-smoke-0123456789",
                "api_image": "synthetic",
                "web_image": "synthetic",
            }
        )
    )
    return module, source, state


def test_corrupt_backup_cannot_allocate_resources(tmp_path, monkeypatch):
    module, source, state = prepared_backup(tmp_path, monkeypatch)
    (source / "users.dump").write_bytes(b"changed")
    with pytest.raises(ValueError, match="integrity|checksum"):
        module.restore(state, source)
    assert list(state.iterdir()) == [state / "smoke.json"]


def test_failed_pg_restore_has_no_success_and_cleans_only_new_project(tmp_path, monkeypatch):
    module, source, directory = prepared_backup(tmp_path, monkeypatch)
    cleaned = []

    def dc(state, *args):
        if "pg_restore" in args:
            raise RuntimeError("restore failed")
        return ""

    monkeypatch.setattr(module, "dc", dc)
    monkeypatch.setattr(module.smoke, "command", lambda *a, **kw: "")
    monkeypatch.setattr(module, "cleanup", lambda state: cleaned.append(state["project"]))
    with pytest.raises(RuntimeError, match="restore failed"):
        module.restore(directory, source)
    assert len(cleaned) == 1
    assert cleaned[0].startswith("klave-recovery-")
    assert cleaned[0] != "klave-smoke-0123456789"
    assert not list(directory.glob("**/SUCCESS"))
    assert (tmp_path / "original/drawing.dxf").read_bytes() == b"original drawing"


def test_existing_scratch_resources_are_never_attached_or_deleted(tmp_path, monkeypatch):
    module, source, directory = prepared_backup(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "dc", lambda *a: pytest.fail("must not attach or delete"))
    monkeypatch.setattr(module.smoke, "command", lambda *a, **kw: "existing-volume")
    with pytest.raises(ValueError, match="fresh"):
        module.restore(directory, source)
    assert (tmp_path / "original/drawing.dxf").read_bytes() == b"original drawing"
