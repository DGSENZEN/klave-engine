"""Croquis for the números generadores: per concept, the plantas with that
concept's elements highlighted. Rendered on demand from the run's cached
sheet renders and cached per run."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from klave_engine.common.config import Settings
from klave_engine.costing.croquis import Croquis, croquis_for_line
from klave_engine.costing.models import CostReport
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation

from apps.api.dependencies import ProjectStore, get_settings, get_store

router = APIRouter(prefix="/projects")


def _safe(code: str) -> bool:
    return bool(code) and code.replace("-", "").replace("_", "").isalnum()


def _croquis(
    store: ProjectStore, settings: Settings, project_id: str, concept_code: str
) -> list[Croquis]:
    report = CostReport.model_validate(store.read_artifact(project_id, "cost_report.json"))
    line = next((ln for ln in report.boq.lines if ln.concept_code == concept_code), None)
    if line is None:
        raise HTTPException(
            status_code=404, detail={"error_type": "concept_not_in_presupuesto"}
        )
    detections = {
        d["detection_id"]: Detection.model_validate(d)
        for d in store.read_artifact(project_id, "detections.json")
    }
    try:
        segmentation: SheetSegmentation | None = SheetSegmentation.model_validate(
            store.read_artifact(project_id, "views.json")
        )
    except HTTPException:
        segmentation = None
    try:
        frames = [
            SheetFrame.model_validate(f) for f in store.read_artifact(project_id, "frames.json")
        ]
    except HTTPException:
        frames = []
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    return croquis_for_line(
        store.artifact_root(project_id),
        control_dir,
        line,
        detections,
        segmentation,
        frames,
        run_id=store.active_run_id(project_id) or "run",
    )


@router.get("/{project_id}/croquis/{concept_code}")
def list_croquis(
    project_id: str,
    concept_code: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not _safe(concept_code):
        raise HTTPException(status_code=404, detail={"error_type": "concept_not_found"})
    items = _croquis(store, settings, project_id, concept_code.upper())
    return {
        "concept_code": concept_code.upper(),
        "croquis": [
            {
                "view_id": c.view_id,
                "title": c.title,
                "count": c.count,
                "url": f"/projects/{project_id}/croquis/{concept_code.upper()}/{c.view_id}.png",
            }
            for c in items
        ],
    }


@router.get("/{project_id}/croquis/{concept_code}/{view_id}.png")
def croquis_png(
    project_id: str,
    concept_code: str,
    view_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    if not _safe(concept_code) or not _safe(view_id):
        raise HTTPException(status_code=404, detail={"error_type": "croquis_not_found"})
    items = _croquis(store, settings, project_id, concept_code.upper())
    match = next((c for c in items if c.view_id == view_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail={"error_type": "croquis_not_found"})
    return FileResponse(match.path, media_type="image/png")
