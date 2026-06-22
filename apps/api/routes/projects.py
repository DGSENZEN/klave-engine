import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from klave_engine.common.config import Settings
from klave_engine.common.ids import short_uuid, slugify
from klave_engine.conversion.libredwg import convert_dwg_to_dxf
from klave_engine.ingestion.project_loader import ingest_project
from klave_engine.pipeline import run_full_pipeline
from pydantic import BaseModel

from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.jobs import JOB_STORE

router = APIRouter(prefix="/projects")

ALLOWED_SUFFIXES = {".dwg", ".dxf"}


class CreateProjectRequest(BaseModel):
    project_name: str
    root_path: str


class ProcessSummaryResponse(BaseModel):
    project_id: str
    processing_status: str
    entity_count: int
    detection_count: int
    risk_count: int
    warnings: list[str]


@router.get("")
def list_projects(store: ProjectStore = Depends(get_store)) -> dict:
    """Projects with name + status for the landing page."""
    projects: list[dict] = []
    for project_id, root in store.list_projects().items():
        entry = {"project_id": project_id, "root_path": root, "name": project_id}
        try:
            manifest = store.get_manifest(project_id)
            entry["name"] = manifest.project_name
            entry["status"] = manifest.processing_status.value
            entry["created_at"] = manifest.created_at.isoformat()
        except Exception:
            entry["status"] = "unknown"
        job = JOB_STORE.get(project_id)
        if job is not None and job.state in ("queued", "running"):
            entry["status"] = job.state
        projects.append(entry)
    projects.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return {"projects": projects}


@router.post("", status_code=201)
def create_project(
    request: CreateProjectRequest,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    root = Path(request.root_path)
    if not root.is_dir():
        raise HTTPException(
            status_code=400,
            detail={"error_type": "invalid_root_path", "root_path": request.root_path},
        )
    manifest = ingest_project(
        root,
        project_name=request.project_name,
        processed_dir_name=settings.processed_dir_name,
    )
    store.register(manifest.project_id, root)
    return manifest.model_dump(mode="json")


@router.post("/upload", status_code=202)
async def upload_project(
    background: BackgroundTasks,
    file: UploadFile,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Accept a DWG/DXF upload, convert if needed, and process in the background."""
    filename = file.filename or "plano.dxf"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail={"error_type": "unsupported_file", "filename": filename},
        )

    project_id = f"{slugify(Path(filename).stem)[:32] or 'plano'}_{short_uuid('p')[2:]}"
    root = settings.data_dir / "uploads" / project_id
    drawings = root / "drawings"
    drawings.mkdir(parents=True, exist_ok=True)
    saved = drawings / filename
    with saved.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    warnings: list[str] = []
    if suffix == ".dwg":
        dxf_path, message = convert_dwg_to_dxf(saved)
        if dxf_path is None:
            raise HTTPException(
                status_code=422,
                detail={"error_type": "conversion_failed", "message": message},
            )
        warnings.append(message)

    manifest = ingest_project(
        root,
        project_name=Path(filename).stem,
        project_id=project_id,
        processed_dir_name=settings.processed_dir_name,
    )
    store.register(project_id, root)
    JOB_STORE.start(project_id)
    background.add_task(JOB_STORE.run, project_id, root, settings)
    return {
        "project_id": project_id,
        "project_name": manifest.project_name,
        "state": "queued",
        "warnings": warnings,
    }


@router.get("/{project_id}/status")
def project_status(
    project_id: str, store: ProjectStore = Depends(get_store)
) -> dict:
    """Processing status for the upload-progress screen."""
    store.get_root(project_id)  # 404 if unknown
    job = JOB_STORE.get(project_id)
    if job is not None:
        return {
            "project_id": project_id,
            "state": job.state,
            "stage": job.stage,
            "error": job.error,
            "entity_count": job.entity_count,
            "detection_count": job.detection_count,
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
        }
    except Exception:
        return {"project_id": project_id, "state": "unknown", "stage": "Desconocido"}


@router.get("/{project_id}")
def get_project(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return store.get_manifest(project_id).model_dump(mode="json")


@router.post("/{project_id}/ingest")
def reingest_project(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    manifest = ingest_project(
        store.get_root(project_id),
        project_id=project_id,
        processed_dir_name=settings.processed_dir_name,
    )
    return manifest.model_dump(mode="json")


@router.post("/{project_id}/process")
def process_project(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> ProcessSummaryResponse:
    result = run_full_pipeline(store.get_root(project_id), settings)
    return ProcessSummaryResponse(
        project_id=result.manifest.project_id,
        processing_status=result.manifest.processing_status.value,
        entity_count=len(result.entities),
        detection_count=len(result.detections),
        risk_count=len(result.risk_report.findings) if result.risk_report else 0,
        warnings=result.warnings,
    )
