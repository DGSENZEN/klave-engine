"""Deliverable downloads: the formatted XLSX presupuesto in Klave's full
layout or in OPUS/Neodata import-friendly layouts."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from klave_engine.common.config import Settings
from klave_engine.common.ids import slugify
from klave_engine.costing.croquis import croquis_for_line
from klave_engine.costing.exports import (
    CroquisProvider,
    build_apus_workbook,
    build_explosion_workbook,
    build_presupuesto_workbook,
)
from klave_engine.costing.hallazgos import diagnose
from klave_engine.costing.models import BoqLine, CostReport
from klave_engine.costing.reviews import load_reviews
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation

from apps.api.auth.common import rate_limit
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


def _blocking_findings(store: ProjectStore, project_id: str, settings: Settings) -> list[str]:
    """Findings that make this deliverable wrong, not merely incomplete.

    A red banner beside a working download button gets clicked through — the
    browser-warning literature measures that at 70% — so a blocking finding
    stops the export instead of decorating it. The way past is a written
    reason, and the reason is stamped into the workbook."""
    try:
        report = CostReport.model_validate(store.read_artifact(project_id, "cost_report.json"))
    except HTTPException:
        return []
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    diagnostico = diagnose(report, reviews=load_reviews(control_dir))
    return [h.title for h in diagnostico.hallazgos if h.severity == "bloqueante"]


def _licitacion_bloqueantes(report: CostReport) -> list[str]:
    """El formato de licitación con un componente por porcentaje declarado es
    el documento desechable que este análisis existe para impedir. La utilidad
    declarada es un criterio de diseño y nunca bloquea."""
    resueltos = {c.code: c for c in report.integracion_resuelta}
    if not resueltos:
        return [
            "La integración no trae fuentes (reporte anterior a los análisis): "
            "reprocesa el proyecto."
        ]
    extra: list[str] = []
    for code, nombre in (
        ("CI-C", "indirectos de campo"), ("CI-O", "indirectos de oficina central"),
        ("FI", "financiamiento"), ("CA", "cargos adicionales"),
    ):
        comp = resueltos.get(code)
        if comp is not None and comp.fuente == "declarado":
            extra.append(
                f"El formato de licitación lleva {nombre} por porcentaje "
                f"declarado ({code}): sin análisis, es causal de desechamiento."
            )
    return extra


def _guard_export(
    store: ProjectStore, project_id: str, settings: Settings, motivo: str,
    extra_blocking: list[str] | None = None,
) -> str:
    """Refuse a deliverable that would be wrong, unless the engineer says why."""
    blocking = _blocking_findings(store, project_id, settings) + list(extra_blocking or [])
    if blocking and not motivo.strip():
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": "export_blocked",
                "message": (
                    "Este presupuesto tiene "
                    + (f"{len(blocking)} hallazgos bloqueantes"
                       if len(blocking) > 1 else "un hallazgo bloqueante")
                    + ": entregarlo así estaría mal. Resuélvelo, o escribe por qué "
                    "lo entregas de todos modos (queda escrito en el Excel)."
                ),
                "bloqueantes": blocking,
            },
        )
    return motivo.strip()[:300]


def _mark_exported(store: ProjectStore, project_id: str) -> None:
    """A tiny marker so onboarding can tell a delivery has happened."""
    try:
        from datetime import UTC, datetime

        from klave_engine.common.io import write_json

        control = store.get_root(project_id) / store.settings.processed_dir_name
        control.mkdir(parents=True, exist_ok=True)
        write_json(control / "last_export.json", {"at": datetime.now(UTC).isoformat()})
    except Exception:  # noqa: BLE001 — a marker must never fail an export
        pass


@router.get("/{project_id}/export/explosion.xlsx")
def export_explosion(
    request: Request,
    project_id: str,
    motivo: str = "",
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Explosión de insumos: what the presupuesto consumes, per resource."""
    rate_limit(request, "export", max_attempts=60, window_seconds=3600.0)
    _guard_export(store, project_id, settings, motivo)
    manifest = store.get_manifest(project_id)
    _mark_exported(store, project_id)
    report = CostReport.model_validate(store.read_artifact(project_id, "cost_report.json"))
    filename = f"explosion_insumos_{slugify(manifest.project_name)[:40]}.xlsx"
    return Response(
        content=build_explosion_workbook(report),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project_id}/export/apus.xlsx")
def export_apus(
    request: Request,
    project_id: str,
    motivo: str = "",
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Análisis de precios unitarios: one block per concept with its matrix."""
    rate_limit(request, "export", max_attempts=60, window_seconds=3600.0)
    _guard_export(store, project_id, settings, motivo)
    manifest = store.get_manifest(project_id)
    _mark_exported(store, project_id)
    report = CostReport.model_validate(store.read_artifact(project_id, "cost_report.json"))
    filename = f"apus_{slugify(manifest.project_name)[:40]}.xlsx"
    return Response(
        content=build_apus_workbook(report),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project_id}/export/presupuesto.xlsx")
def export_presupuesto(
    request: Request,
    project_id: str,
    format: Literal["klave", "opus", "neodata", "licitacion", "licitacion_larga"] = "klave",
    motivo: str = "",
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    rate_limit(request, "export", max_attempts=60, window_seconds=3600.0)
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
    extra = (
        _licitacion_bloqueantes(report)
        if format in ("licitacion", "licitacion_larga") else []
    )
    reason = _guard_export(store, project_id, settings, motivo, extra_blocking=extra)
    _mark_exported(store, project_id)
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
        override_reason=reason,
    )
    suffix = "" if format == "klave" else f"_{format}"
    filename = f"presupuesto_{slugify(manifest.project_name)[:40]}{suffix}.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
