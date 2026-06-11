from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from klave_engine.common.config import Settings
from klave_engine.ingestion.project_loader import ingest_project
from klave_engine.pipeline import run_full_pipeline
from pydantic import BaseModel

from apps.api.dependencies import ProjectStore, get_settings, get_store

router = APIRouter(prefix="/projects")


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
    return {"projects": store.list_projects()}


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
