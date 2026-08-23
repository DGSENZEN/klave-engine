import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, UploadFile
from klave_engine.common.config import Settings
from klave_engine.common.ids import short_uuid, slugify
from klave_engine.common.io import read_json
from klave_engine.common.version import engine_fingerprint
from klave_engine.conversion.libredwg import convert_dwg_to_dxf
from klave_engine.costing.defaults import apply_workspace_defaults
from klave_engine.ingestion.manifest import ConvertedFile, save_manifest
from klave_engine.ingestion.project_loader import ingest_project
from pydantic import BaseModel

from apps.api.auth.store import UsersDbUnavailable, get_user_store
from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import BUS, clean_actor
from apps.api.jobs import JOB_STORE, JobQueueFullError
from apps.api.tenancy import defaults_scope, request_workspace_id

router = APIRouter(prefix="/projects")

ALLOWED_SUFFIXES = {".dwg", ".dxf"}
UPLOAD_CHUNK_BYTES = 1024 * 1024
# A residential set is ~16 sheets; 40 leaves room without inviting abuse.
MAX_FILES_PER_PROJECT = 40


class CreateProjectRequest(BaseModel):
    project_name: str
    root_path: str


class ProcessAcceptedResponse(BaseModel):
    project_id: str
    job_id: str
    run_id: str
    state: str
    stage: str


def _validated_upload_name(filename: str) -> tuple[str, str]:
    """Validate the client-provided display name before touching the filesystem."""
    if (
        not filename
        or len(filename) > 255
        or "\x00" in filename
        or "/" in filename
        or "\\" in filename
    ):
        raise HTTPException(
            status_code=400,
            detail={"error_type": "invalid_filename", "message": "Nombre de archivo inválido."},
        )
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail={"error_type": "unsupported_file", "filename": filename},
        )
    return filename, suffix


def _validate_upload_signature(suffix: str, header: bytes) -> None:
    """Reject obvious content-type spoofing before invoking a CAD parser/converter."""
    valid = False
    if suffix == ".dwg":
        valid = bool(re.fullmatch(rb"AC10\d{2}", header[:6]))
    elif header.startswith(b"AutoCAD Binary DXF"):
        valid = True
    else:
        # ASCII DXF permits comments before the first SECTION, so look for a
        # complete group-code/value pair rather than assuming byte zero.
        valid = bool(re.search(rb"(?:^|[\r\n])\s*0\s*[\r\n]+\s*SECTION(?:[\r\n]|$)", header))
    if not valid:
        raise HTTPException(
            status_code=422,
            detail={
                "error_type": "invalid_file_signature",
                "message": "El archivo no coincide con el formato DWG/DXF declarado.",
            },
        )


async def _save_upload(file: UploadFile, destination: Path, max_bytes: int) -> None:
    """Stream an upload with a hard byte limit and remove partial files on failure."""
    written = 0
    header = bytearray()
    try:
        with destination.open("xb") as out:
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "error_type": "upload_too_large",
                            "max_upload_bytes": max_bytes,
                        },
                    )
                if len(header) < 64 * 1024:
                    header.extend(chunk[: 64 * 1024 - len(header)])
                out.write(chunk)
        _validate_upload_signature(destination.suffix.lower(), bytes(header))
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


def _state_user(request: Request) -> dict | None:
    return getattr(request.state, "user", None)


def _grant_owner(request: Request, settings: Settings, project_id: str) -> None:
    """In protected mode the creator becomes the project owner."""
    user = _state_user(request)
    if user is None:
        return
    try:
        users = get_user_store(settings.users_database_url)
        users.grant_access(project_id, str(user["user_id"]), "owner", str(user["user_id"]))
        users.register_project(project_id, str(user["workspace_id"]))
    except UsersDbUnavailable:
        pass


def visible_project_filter(request: Request, store: ProjectStore) -> Callable[[str], bool]:
    """Which projects the request may see: everything in open mode, every
    project of their workspace for admins (projects that predate workspaces
    belong to the default one), and explicit grants for members."""
    user = _state_user(request)
    if user is None:
        return lambda project_id: True
    try:
        users = get_user_store(store.settings.users_database_url)
        if user["role"] == "admin":
            workspace_of = users.project_workspace_map()
            admin_workspace = str(user["workspace_id"])
            default_workspace = str(users.default_workspace()["workspace_id"])
            return (
                lambda project_id: workspace_of.get(project_id, default_workspace)
                == admin_workspace
            )
        allowed = users.project_ids_for_user(str(user["user_id"]))
    except UsersDbUnavailable:
        allowed = set()
    return lambda project_id: project_id in allowed


@router.get("")
def list_projects(request: Request, store: ProjectStore = Depends(get_store)) -> dict:
    """Projects with name + status; in protected mode, only those the user
    can access (admins see their workspace)."""
    keep = visible_project_filter(request, store)
    projects: list[dict] = []
    for project_id, root in store.list_projects().items():
        if not keep(project_id):
            continue
        entry: dict[str, object] = {
            "project_id": project_id,
            "root_path": root,
            "name": project_id,
        }
        try:
            manifest = store.get_manifest(project_id)
            entry["name"] = manifest.project_name
            entry["status"] = manifest.processing_status.value
            entry["created_at"] = manifest.created_at.isoformat()
            entry["client"] = manifest.client
            entry["archived"] = manifest.archived
            entry["sheet_count"] = len(manifest.source_files)
        except Exception:
            entry["status"] = "unknown"
        job = JOB_STORE.get(project_id, Path(root), store.settings)
        if job is not None and job.state in ("queued", "running"):
            entry["status"] = job.state
        projects.append(entry)
    projects.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return {"projects": projects}


@router.post("", status_code=201)
def create_project(
    body: CreateProjectRequest,
    request: Request,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    root = Path(body.root_path)
    if not root.is_dir():
        raise HTTPException(
            status_code=400,
            detail={"error_type": "invalid_root_path", "root_path": body.root_path},
        )
    root = store.managed_root(root)
    manifest = ingest_project(
        root,
        project_name=body.project_name,
        processed_dir_name=settings.processed_dir_name,
    )
    store.register(manifest.project_id, root)
    _grant_owner(request, settings, manifest.project_id)
    apply_workspace_defaults(
        defaults_scope(settings, request_workspace_id(request)),
        root / settings.processed_dir_name,
    )
    BUS.publish(
        "project_created",
        project_id=manifest.project_id,
        actor=clean_actor(x_actor),
        data={"project_name": manifest.project_name},
    )
    return manifest.model_dump(mode="json")


async def _save_sheet_uploads(
    files: list[UploadFile],
    drawings: Path,
    max_bytes: int,
    start_index: int,
) -> list[Path]:
    """Validate and stream every sheet to path-safe deterministic names that
    keep the original stem, so sheet-number inference still works."""
    if not files:
        raise HTTPException(
            status_code=400,
            detail={"error_type": "no_files", "message": "Sube al menos un archivo."},
        )
    if start_index + len(files) > MAX_FILES_PER_PROJECT:
        raise HTTPException(
            status_code=413,
            detail={
                "error_type": "too_many_files",
                "message": f"Un proyecto lleva hasta {MAX_FILES_PER_PROJECT} hojas.",
                "max_files": MAX_FILES_PER_PROJECT,
            },
        )
    saved: list[Path] = []
    for offset, file in enumerate(files):
        filename, suffix = _validated_upload_name(file.filename or "plano.dxf")
        stem = slugify(Path(filename).stem)[:40] or "plano"
        destination = drawings / f"{start_index + offset:02d}-{stem}{suffix}"
        await _save_upload(file, destination, max_bytes)
        saved.append(destination)
    return saved


def _convert_new_dwgs(root: Path, manifest, settings: Settings) -> list[str]:
    """Convert DWG sources that lack a successful conversion. A sheet that
    cannot be converted is recorded as failed with its reason and the rest
    of the project goes on; the caller decides whether anything is left."""
    warnings: list[str] = []
    converted_ids = {c.source_file_id for c in manifest.converted_files}
    for source in manifest.source_files:
        if source.file_type.value != "dwg" or source.file_id in converted_ids:
            continue
        dxf_path, message = convert_dwg_to_dxf(
            root / source.path, timeout_seconds=settings.converter_timeout_seconds
        )
        converted = (
            root
            / settings.converted_dir_name
            / source.file_id
            / f"{Path(source.path).stem}.dxf"
        )
        if dxf_path is None:
            manifest.converted_files.append(
                ConvertedFile(
                    source_file_id=source.file_id,
                    path=str(converted.relative_to(root)),
                    conversion_status="failed",
                    error=message,
                )
            )
            warnings.append(f"{Path(source.path).name}: {message}")
            continue
        converted.parent.mkdir(parents=True, exist_ok=True)
        dxf_path.replace(converted)
        manifest.converted_files.append(
            ConvertedFile(
                source_file_id=source.file_id,
                path=str(converted.relative_to(root)),
            )
        )
        warnings.append(message)
    save_manifest(manifest, settings.processed_dir_name)
    return warnings


def _require_readable_sheet(manifest, root: Path) -> None:
    """Reject a project only when not one sheet can be read."""
    if manifest.dxf_paths():
        return
    failures = [c.error for c in manifest.converted_files if c.conversion_status == "failed"]
    shutil.rmtree(root, ignore_errors=True)
    raise HTTPException(
        status_code=422,
        detail={
            "error_type": "conversion_failed",
            "message": "Ninguna hoja se pudo leer. " + (failures[0] or "")[:300],
            "failures": failures,
        },
    )


@router.post("/upload", status_code=202)
async def upload_project(
    request: Request,
    files: list[UploadFile],
    project_name: Annotated[str | None, Form()] = None,
    client: Annotated[str | None, Form()] = None,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Accept one or more DWG/DXF sheets as a new project and process them.
    The name and client are optional; the first file's stem is the fallback."""
    first_name, _ = _validated_upload_name(files[0].filename or "plano.dxf")
    name = " ".join((project_name or "").split())[:120] or Path(first_name).stem
    project_id = f"{slugify(name)[:32] or 'plano'}_{short_uuid('p')[2:]}"
    root = (settings.data_dir / "uploads" / project_id).resolve()
    drawings = root / "drawings"
    drawings.mkdir(parents=True, exist_ok=True)

    try:
        await _save_sheet_uploads(files, drawings, settings.max_upload_bytes, 1)
        manifest = ingest_project(
            root,
            project_name=name,
            project_id=project_id,
            processed_dir_name=settings.processed_dir_name,
        )
        cleaned_client = " ".join((client or "").split())[:120]
        if cleaned_client:
            manifest.client = cleaned_client
            save_manifest(manifest, settings.processed_dir_name)
        warnings = _convert_new_dwgs(root, manifest, settings)
        _require_readable_sheet(manifest, root)
    except HTTPException:
        shutil.rmtree(root, ignore_errors=True)
        raise

    store.register(project_id, root)
    _grant_owner(request, settings, project_id)
    apply_workspace_defaults(
        defaults_scope(settings, request_workspace_id(request)),
        root / settings.processed_dir_name,
    )
    BUS.publish(
        "project_created",
        project_id=project_id,
        actor=clean_actor(x_actor),
        data={"project_name": manifest.project_name},
    )
    try:
        job, _ = JOB_STORE.enqueue(project_id, root, settings)
    except JobQueueFullError as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "error_type": "processing_queue_full",
                "project_id": project_id,
                "message": "La cola de procesamiento está llena. Inténtalo de nuevo pronto.",
            },
            headers={"Retry-After": "30"},
        ) from exc
    return {
        "project_id": project_id,
        "project_name": manifest.project_name,
        "job_id": job.job_id,
        "run_id": job.run_id,
        "state": job.state,
        "warnings": warnings,
    }


@router.get("/{project_id}/status")
def project_status(
    project_id: str, store: ProjectStore = Depends(get_store)
) -> dict:
    """Processing status for the upload-progress screen."""
    root = store.get_root(project_id)  # 404 if unknown
    # Failure must stay useful: if a previous run left readable artifacts,
    # the client can still open the viewer and the lectura.
    artifacts_available = (store.artifact_root(project_id) / "normalized_entities.json").exists()
    job = JOB_STORE.get(project_id, root, store.settings)
    if job is not None:
        return {
            "project_id": project_id,
            "job_id": job.job_id,
            "run_id": job.run_id,
            "state": job.state,
            "stage": job.stage,
            "error": job.error,
            "entity_count": job.entity_count,
            "detection_count": job.detection_count,
            "artifacts_available": artifacts_available,
        }
    # No active job: fall back to the persisted manifest status.
    try:
        manifest = store.get_manifest(project_id)
        processed = manifest.processing_status.value == "processed"
        return {
            "project_id": project_id,
            "state": "processed" if processed else manifest.processing_status.value,
            "stage": "Completado" if processed else manifest.processing_status.value,
            "error": None,
            "artifacts_available": artifacts_available,
        }
    except Exception:
        return {
            "project_id": project_id,
            "state": "unknown",
            "stage": "Desconocido",
            "artifacts_available": artifacts_available,
        }


@router.get("/{project_id}")
def get_project(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    payload = store.get_manifest(project_id).model_dump(mode="json")
    engine_path = store.artifact_root(project_id) / "engine.json"
    stamp: dict = {}
    if engine_path.exists():
        try:
            stamp = read_json(engine_path)
        except (ValueError, OSError):
            stamp = {}
    payload["engine"] = {
        "fingerprint": stamp.get("fingerprint"),
        "processed_at": stamp.get("processed_at"),
        "current": engine_fingerprint(),
        "stale": payload.get("processing_status") == "processed"
        and stamp.get("fingerprint") != engine_fingerprint(),
    }
    return payload


@router.post("/{project_id}/ingest")
def reingest_project(
    project_id: str,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    manifest = ingest_project(
        store.get_root(project_id),
        project_id=project_id,
        processed_dir_name=settings.processed_dir_name,
    )
    BUS.publish(
        "project_updated",
        project_id=project_id,
        actor=clean_actor(x_actor),
        data={"project_name": manifest.project_name},
    )
    return manifest.model_dump(mode="json")


@router.post("/{project_id}/process", status_code=202)
def process_project(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> ProcessAcceptedResponse:
    root = store.get_root(project_id)
    try:
        job, _ = JOB_STORE.enqueue(project_id, root, settings)
    except JobQueueFullError as exc:
        raise HTTPException(
            status_code=429,
            detail={"error_type": "processing_queue_full", "project_id": project_id},
            headers={"Retry-After": "30"},
        ) from exc
    return ProcessAcceptedResponse(
        project_id=project_id,
        job_id=job.job_id,
        run_id=job.run_id,
        state=job.state,
        stage=job.stage,
    )


class ProjectPatch(BaseModel):
    name: str | None = None
    client: str | None = None
    archived: bool | None = None


@router.post("/{project_id}/files", status_code=202)
async def add_project_files(
    project_id: str,
    files: list[UploadFile],
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Add sheets to an existing project and reprocess it as one drawing set."""
    root = store.get_root(project_id)
    drawings = root / "drawings"
    drawings.mkdir(parents=True, exist_ok=True)
    existing = len(
        [p for p in drawings.iterdir() if p.suffix.lower() in ALLOWED_SUFFIXES]
    )
    saved = await _save_sheet_uploads(
        files, drawings, settings.max_upload_bytes, existing + 1
    )
    try:
        manifest = ingest_project(
            root, project_id=project_id, processed_dir_name=settings.processed_dir_name
        )
        warnings = _convert_new_dwgs(root, manifest, settings)
    except HTTPException:
        for path in saved:
            path.unlink(missing_ok=True)
        ingest_project(
            root, project_id=project_id, processed_dir_name=settings.processed_dir_name
        )
        raise
    BUS.publish(
        "project_updated",
        project_id=project_id,
        actor=clean_actor(x_actor),
        data={"action": "sheets_added", "sheet_count": len(manifest.source_files)},
    )
    try:
        job, _ = JOB_STORE.enqueue(project_id, root, settings)
    except JobQueueFullError as exc:
        raise HTTPException(
            status_code=429,
            detail={"error_type": "processing_queue_full", "project_id": project_id},
            headers={"Retry-After": "30"},
        ) from exc
    return {
        "project_id": project_id,
        "sheet_count": len(manifest.source_files),
        "job_id": job.job_id,
        "state": job.state,
        "warnings": warnings,
    }


@router.patch("/{project_id}")
def patch_project(
    project_id: str,
    body: ProjectPatch,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Organization metadata: rename, client, archive. Never touches drawings."""
    manifest = store.get_manifest(project_id)
    if body.name is not None:
        name = " ".join(body.name.split())[:80]
        if not name:
            raise HTTPException(
                status_code=422,
                detail={
                    "error_type": "invalid_name",
                    "message": "El nombre no puede quedar vacío.",
                },
            )
        manifest.project_name = name
    if body.client is not None:
        manifest.client = " ".join(body.client.split())[:80] or None
    if body.archived is not None:
        manifest.archived = body.archived
    save_manifest(manifest, settings.processed_dir_name)
    BUS.publish(
        "project_updated",
        project_id=project_id,
        actor=clean_actor(x_actor),
        data={"action": "organized", "name": manifest.project_name},
    )
    return {
        "project_id": project_id,
        "name": manifest.project_name,
        "client": manifest.client,
        "archived": manifest.archived,
    }


@router.delete("/{project_id}")
def remove_project(
    project_id: str,
    request: Request,
    purge: bool = False,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
) -> dict:
    """Remove the project from the workspace list. With ``purge`` the files
    on disk go too — drawings, runs, reviews, versions, everything; without
    it they stay for a manual rescue."""
    root = store.get_root(project_id)  # 404 for unknown ids
    store.unregister(project_id)
    purged = False
    if purge:
        resolved = root.resolve()
        # Only ever delete a directory that lives under the uploads tree.
        uploads = (store.settings.data_dir / "uploads").resolve()
        if resolved != uploads and uploads in resolved.parents:
            shutil.rmtree(resolved, ignore_errors=True)
            purged = True
    user = _state_user(request)
    if user is not None:
        try:
            get_user_store(store.settings.users_database_url).record_audit(
                workspace_id=str(user["workspace_id"]), actor=user,
                action="project_removed", target_type="project", target_id=project_id,
                detail={"purged": purge},
            )
        except UsersDbUnavailable:
            pass
    BUS.publish(
        "project_removed",
        project_id=project_id,
        actor=clean_actor(x_actor),
        data={},
    )
    return {"project_id": project_id, "removed": True, "purged": purged}
