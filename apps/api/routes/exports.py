"""Deliverable downloads: the formatted XLSX presupuesto in Klave's full
layout or in OPUS/Neodata import-friendly layouts."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from klave_engine.common.config import Settings
from klave_engine.common.ids import slugify
from klave_engine.costing.croquis import croquis_for_line
from klave_engine.costing.exports import CroquisProvider, build_presupuesto_workbook
from klave_engine.costing.models import BoqLine, CostReport
from klave_engine.costing.reviews import load_reviews
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation

from apps.api.dependencies import ProjectStore, get_settings, get_store

router = APIRouter(prefix="/projects")

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _croquis_provider(
    store: ProjectStore, settings: Settings, project_id: str, detections: list[Detection]
) -> CroquisProvider:
    """Croquis per line for the Generadores sheet, from the run's cached
    renders; a line whose croquis fails to draw simply has none."""
    by_id = {d.detection_id: d for d in detections}
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
    artifact_dir = store.artifact_root(project_id)
    run_id = store.active_run_id(project_id) or "run"

    def provide(line: BoqLine) -> list[tuple[str, Path]]:
        try:
            items = croquis_for_line(
                artifact_dir, control_dir, line, by_id, segmentation, frames, run_id=run_id
            )
        except (OSError, ValueError):
            return []
        return [(c.title, c.path) for c in items]

    return provide


@router.get("/{project_id}/export/presupuesto.xlsx")
def export_presupuesto(
    project_id: str,
    format: Literal["klave", "opus", "neodata"] = "klave",
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    manifest = store.get_manifest(project_id)
    try:
        report = CostReport.model_validate(
            store.read_artifact(project_id, "cost_report.json")
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error_type": "report_unreadable",
                "message": "El reporte de costos no se pudo leer; vuelve a procesar.",
            },
        ) from exc
    detections = [
        Detection.model_validate(d)
        for d in store.read_artifact(project_id, "detections.json")
    ]
    reviews = load_reviews(store.get_root(project_id) / settings.processed_dir_name)
    try:
        inventory = store.read_artifact(project_id, "inventory.json")
    except HTTPException:
        inventory = None  # runs older than the levantamiento

    content = build_presupuesto_workbook(
        report,
        detections,
        reviews,
        project_name=manifest.project_name,
        client=manifest.client,
        fmt=format,
        inventory=inventory,
        croquis=(
            _croquis_provider(store, settings, project_id, detections)
            if format == "klave"
            else None
        ),
    )
    suffix = "" if format == "klave" else f"_{format}"
    filename = f"presupuesto_{slugify(manifest.project_name)[:40]}{suffix}.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
