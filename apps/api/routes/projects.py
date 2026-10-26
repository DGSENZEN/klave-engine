import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, UploadFile
from klave_engine.common.config import Settings
from klave_engine.common.errors import ProjectManifestError
from klave_engine.common.ids import short_uuid, slugify
from klave_engine.common.io import read_json, write_text
from klave_engine.common.version import engine_fingerprint
from klave_engine.costing.catalog_store import drop_catalog_store
from klave_engine.costing.defaults import apply_workspace_defaults
from klave_engine.ejemplo import es_obra_de_ejemplo, sample_project_id
from klave_engine.ejemplo.catalogo import sembrar_catalogo_didactico
from klave_engine.ejemplo.obra import build_obra_ejemplo
from klave_engine.ingestion.manifest import load_manifest, manifest_path, save_manifest
from klave_engine.ingestion.project_loader import find_drawing_files, ingest_project
from pydantic import BaseModel

from apps.api.auth.access import require_project_role
from apps.api.auth.common import db_unavailable, rate_limit
from apps.api.auth.store import UsersDbUnavailable, get_user_store
from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import BUS, clean_actor
from apps.api.jobs import JOB_STORE, JobQueueFullError
from apps.api.observability import context_from_request
from apps.api.tenancy import defaults_scope, request_workspace_id, store_for_project

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
    created = False
    try:
        with destination.open("xb") as out:
            created = True
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
        if created:
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
    except UsersDbUnavailable as exc:
        # An unassigned project falls back to the default workspace. Never
        # publish another taller's uploaded drawings when ownership failed.
        raise db_unavailable() from exc


def visible_project_filter(request: Request, store: ProjectStore) -> Callable[[str], bool]:
    """Which projects the request may see: everything in open mode, every
    project of their workspace for admins (projects that predate workspaces
    belong to the default one), and explicit grants for members."""
    user = _state_user(request)
    if user is None:
        return lambda project_id: True
    propia = sample_project_id(str(user["workspace_id"]), str(user["user_id"]))
    filtro = _filtro_de_cuentas(user, store)
    # La obra de ejemplo es de quien la hizo: ni un administrador ve la ajena.
    return lambda project_id: (
        project_id == propia if es_obra_de_ejemplo(project_id) else filtro(project_id)
    )


def _filtro_de_cuentas(user: dict, store: ProjectStore) -> Callable[[str], bool]:
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
    # Importar una carpeta del servidor es de quien opera la máquina, no de un
    # usuario de la web: en producción la ruta no existe (la web no la usa).
    if settings.env == "production":
        raise HTTPException(status_code=404, detail="Not Found")
    root = Path(body.root_path)
    if not root.is_dir():
        raise HTTPException(
            status_code=400,
            detail={"error_type": "invalid_root_path", "root_path": body.root_path},
        )
    root = store.managed_root(root)
    if _state_user(request) is not None:
        # Import is also a write to an existing project: check before ingestion
        # changes its manifest or _grant_owner can upgrade the caller's role.
        existing_ids = {
            pid for pid, registered in store.roots().items()
            if (
                root.is_relative_to(registered.resolve())
                or registered.resolve().is_relative_to(root)
            )
        }
        # A retained manifest also protects a soft-deleted project's subfolders.
        for candidate in (root, *root.parents):
            if not candidate.is_relative_to(settings.data_dir.resolve()):
                break
            try:
                existing_ids.add(load_manifest(candidate, settings.processed_dir_name).project_id)
            except ProjectManifestError:
                continue
        for existing_id in existing_ids:
            require_project_role(request, existing_id, "owner")
    manifest = ingest_project(
        root,
        project_name=body.project_name,
        processed_dir_name=settings.processed_dir_name,
    )
    _grant_owner(request, settings, manifest.project_id)
    store.register(manifest.project_id, root)
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
    if start_index - 1 + len(files) > MAX_FILES_PER_PROJECT:
        raise HTTPException(
            status_code=413,
            detail={
                "error_type": "too_many_files",
                "message": f"Un proyecto lleva hasta {MAX_FILES_PER_PROJECT} hojas.",
                "max_files": MAX_FILES_PER_PROJECT,
            },
        )
    saved: list[Path] = []
    try:
        for offset, file in enumerate(files):
            filename, suffix = _validated_upload_name(file.filename or "plano.dxf")
            stem = slugify(Path(filename).stem)[:40] or "plano"
            destination = drawings / f"{start_index + offset:02d}-{stem}{suffix}"
            await _save_upload(file, destination, max_bytes)
            saved.append(destination)
    except Exception:
        for path in saved:
            path.unlink(missing_ok=True)
        raise
    return saved


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
    rate_limit(request, "upload", max_attempts=20, window_seconds=3600.0)
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
        _grant_owner(request, settings, project_id)
        # La conversión DWG→DXF corre en el trabajo, no aquí: tarda minutos en
        # un juego grande y, dentro de la petición, congelaba todo el servidor
        # (la pantalla se quedaba cargando). El avance se ve hoja por hoja.
        warnings: list[str] = []
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise

    store.register(project_id, root)
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
        job, _ = JOB_STORE.enqueue(
            project_id, root, settings, context=context_from_request(request, project_id=project_id)
        )
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


def _ya_procesada(store: ProjectStore, project_id: str, root: Path, settings: Settings) -> bool:
    """La obra de ejemplo ya está leída: volver a abrirla no la reprocesa."""
    job = JOB_STORE.get(project_id, root, settings)
    if job is not None:
        return job.state == "processed"
    try:
        manifest = load_manifest(root, settings.processed_dir_name)
    except ProjectManifestError:
        return False
    return manifest.processing_status.value == "processed"


@router.post("/demo", status_code=202)
def create_demo_project(
    request: Request,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """La obra de ejemplo de esta persona: la obra didáctica del recorrido
    guiado, con su propio catálogo, creada una vez y procesada como trabajo.
    Abrirla otra vez no la vuelve a leer si ya está leída."""
    rate_limit(request, "process", max_attempts=30, window_seconds=3600.0)
    user = _state_user(request)
    project_id = sample_project_id(
        request_workspace_id(request), str(user["user_id"]) if user else None
    )
    root = (settings.data_dir / "uploads" / project_id).resolve()
    fresh = not root.exists()
    if not fresh and _ya_procesada(store, project_id, root, settings):
        _grant_owner(request, settings, project_id)
        store.register(project_id, root)
        return {"project_id": project_id, "job_id": None, "fresh": False}
    try:
        if fresh:
            build_obra_ejemplo(root, "A")
            sembrar_catalogo_didactico(store_for_project(settings, project_id))
        manifest = ingest_project(
            root,
            project_name="Obra de ejemplo",
            project_id=project_id,
            processed_dir_name=settings.processed_dir_name,
        )
        _grant_owner(request, settings, project_id)
    except Exception:
        if fresh:
            shutil.rmtree(root, ignore_errors=True)
            drop_catalog_store(settings.data_dir, project_id)
        raise

    store.register(project_id, root)
    if fresh:
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
        job, _ = JOB_STORE.enqueue(
            project_id, root, settings, context=context_from_request(request, project_id=project_id)
        )
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
    return {"project_id": project_id, "job_id": job.job_id, "fresh": fresh}


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
    request: Request,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> ProcessAcceptedResponse:
    rate_limit(request, "process", max_attempts=30, window_seconds=3600.0)
    root = store.get_root(project_id)
    try:
        job, _ = JOB_STORE.enqueue(
            project_id, root, settings, context=context_from_request(request, project_id=project_id)
        )
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
    request: Request,
    files: list[UploadFile],
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Add sheets to an existing project and reprocess it as one drawing set."""
    rate_limit(request, "upload", max_attempts=20, window_seconds=3600.0)
    root = store.get_root(project_id)
    drawings = root / "drawings"
    drawings.mkdir(parents=True, exist_ok=True)
    existing = len(find_drawing_files(root))
    saved = await _save_sheet_uploads(
        files, drawings, settings.max_upload_bytes, existing + 1
    )
    # Streaming yields to other requests: preserve the manifest as it stands
    # after the upload, including metadata edits acknowledged in the meantime.
    previous_manifest_path = manifest_path(root, settings.processed_dir_name)
    try:
        previous_manifest = (
            previous_manifest_path.read_text(encoding="utf-8")
            if previous_manifest_path.exists()
            else None
        )
    except Exception:
        for path in saved:
            path.unlink(missing_ok=True)
        raise
    try:
        manifest = ingest_project(
            root, project_id=project_id, processed_dir_name=settings.processed_dir_name
        )
        warnings: list[str] = []  # se convierten en el trabajo (ver upload_project)
    except Exception:
        for path in saved:
            path.unlink(missing_ok=True)
        # Re-ingesting would reset the original processing status and metadata.
        if previous_manifest is None:
            previous_manifest_path.unlink(missing_ok=True)
        else:
            write_text(previous_manifest_path, previous_manifest)
        raise
    BUS.publish(
        "project_updated",
        project_id=project_id,
        actor=clean_actor(x_actor),
        data={"action": "sheets_added", "sheet_count": len(manifest.source_files)},
    )
    try:
        job, _ = JOB_STORE.enqueue(
            project_id, root, settings, context=context_from_request(request, project_id=project_id)
        )
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
