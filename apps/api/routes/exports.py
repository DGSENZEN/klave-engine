"""Deliverable downloads: the formatted XLSX presupuesto in Klave's full
layout or in OPUS/Neodata import-friendly layouts."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from klave_engine.common.config import Settings
from klave_engine.common.ids import slugify
from klave_engine.costing.exports import build_presupuesto_workbook
from klave_engine.costing.models import CostReport
from klave_engine.costing.reviews import load_reviews
from klave_engine.detection.results import Detection

from apps.api.dependencies import ProjectStore, get_settings, get_store

router = APIRouter(prefix="/projects")

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


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

    content = build_presupuesto_workbook(
        report,
        detections,
        reviews,
        project_name=manifest.project_name,
        client=manifest.client,
        fmt=format,
    )
    suffix = "" if format == "klave" else f"_{format}"
    filename = f"presupuesto_{slugify(manifest.project_name)[:40]}{suffix}.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
