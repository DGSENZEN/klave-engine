from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from klave_engine.common.config import Settings
from klave_engine.costing.hallazgos import diagnose
from klave_engine.costing.models import CostingConfig, CostingOverrides, CostReport
from klave_engine.costing.recompute import load_overrides, recompute_and_persist
from klave_engine.costing.reviews import load_reviews
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection
from klave_engine.llm.coverage import coverage_flags
from klave_engine.llm.service import load_ai_reads

from apps.api.dependencies import (
    ProjectStore,
    get_settings,
    get_store,
    project_recompute_lock,
)
from apps.api.events import BUS, clean_actor, clean_client_id
from apps.api.jobs import ACTIVE_STATES, JOB_STORE
from apps.api.tenancy import store_for_project

router = APIRouter(prefix="/projects")


@router.get("/{project_id}/quantities")
def get_quantities(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return store.read_artifact(project_id, "quantity_report.json")


@router.get("/{project_id}/costs")
def get_costs(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return store.read_artifact(project_id, "cost_report.json")


@router.get("/{project_id}/diagnostico")
def get_diagnostico(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """What is wrong with this presupuesto, ranked by consequence.

    Computed on demand rather than persisted: it is a reading of the current
    report, reviews and AI coverage, and it must never go stale behind them."""
    report = CostReport.model_validate(store.read_artifact(project_id, "cost_report.json"))
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    reviews = load_reviews(control_dir)
    cobertura: list[dict] = []
    try:
        reads = load_ai_reads(control_dir)
        if reads.readings:
            detections = [
                Detection.model_validate(d)
                for d in store.read_artifact(project_id, "detections.json")
            ]
            frames = [
                SheetFrame.model_validate(f)
                for f in store.read_artifact(project_id, "frames.json")
            ]
            cobertura = [
                f.model_dump()
                for f in coverage_flags(
                    [r.model_dump() for r in reads.readings], detections, frames
                )
            ]
    except HTTPException:
        cobertura = []  # older run without those artifacts: no coverage to add
    return diagnose(report, reviews=reviews, cobertura=cobertura).model_dump()


@router.get("/{project_id}/views")
def get_views(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return store.read_artifact(project_id, "views.json")


@router.get("/{project_id}/dimensions")
def get_dimensions(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return store.read_artifact(project_id, "dimensions.json")


@router.get("/{project_id}/costing-config")
def get_costing_config(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Effective costing parameters + insumo catalog for the editor."""
    processed = store.get_root(project_id) / settings.processed_dir_name
    overrides = load_overrides(processed)
    config = overrides.config if overrides else CostingConfig()
    prices = overrides.insumo_prices if overrides else {}
    catalog_book = store_for_project(settings, project_id).load_price_book()
    insumos = [
        {**resource.model_dump(mode="json"), "unit_cost": prices.get(code, resource.unit_cost)}
        for code, resource in catalog_book.items()
    ]
    return {
        "config": config.model_dump(mode="json"),
        "insumos": insumos,
        "insumo_prices": prices,
        "has_overrides": overrides is not None,
        "version": overrides.version if overrides else 0,
        "updated_by": overrides.updated_by if overrides else None,
        "updated_at": (
            overrides.updated_at.isoformat()
            if overrides and overrides.updated_at
            else None
        ),
    }


@router.post("/{project_id}/recompute")
def recompute(
    project_id: str,
    overrides: CostingOverrides,
    x_actor: Annotated[str | None, Header()] = None,
    x_client_id: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Rebuild the cost report with edited parameters/prices (no re-detection).

    Optimistic concurrency: the submitted ``version`` must match the stored
    one; a mismatch means a collaborator saved first and returns 409 so the
    client can reload their changes instead of silently overwriting them.
    """
    root = store.get_root(project_id)
    job = JOB_STORE.get(project_id, root, settings)
    if job is not None and job.state in ACTIVE_STATES:
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": "project_processing",
                "message": "Espera a que termine el procesamiento antes de recalcular costos.",
            },
        )
    actor = clean_actor(x_actor)
    control_dir = root / settings.processed_dir_name
    # Snapshot the total before recomputing so the broadcast can show the delta.
    try:
        prev_grand_total = store.read_artifact(project_id, "cost_report.json")[
            "integration"
        ]["grand_total"]
    except (HTTPException, KeyError, TypeError):
        prev_grand_total = None
    with project_recompute_lock(project_id):
        current = load_overrides(control_dir)
        current_version = current.version if current else 0
        if overrides.version != current_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_type": "version_conflict",
                    "current_version": current_version,
                    "updated_by": current.updated_by if current else None,
                    "updated_at": (
                        current.updated_at.isoformat()
                        if current and current.updated_at
                        else None
                    ),
                    "message": "Otro usuario guardó cambios; recarga antes de recalcular.",
                },
            )
        overrides.version = current_version + 1
        overrides.updated_by = actor
        overrides.updated_at = datetime.now(UTC)
        report = recompute_and_persist(
            store.artifact_root(project_id),
            control_dir,
            root / "reports",
            project_id,
            overrides,
            catalog_store=store_for_project(settings, project_id),
        )
    BUS.publish(
        "costing_updated",
        project_id=project_id,
        actor=actor,
        data={
            "client_id": clean_client_id(x_client_id),
            "version": overrides.version,
            "direct_cost": report.boq.direct_cost_total,
            "grand_total": report.integration.grand_total,
            "prev_grand_total": prev_grand_total,
            "insumo_overrides": len(overrides.insumo_prices),
        },
    )
    return report.model_dump(mode="json")


@router.get("/{project_id}/diff")
def get_run_diff(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    """Changes vs the previous processing; absent on first runs."""
    try:
        diff = store.read_artifact(project_id, "run_diff.json")
    except HTTPException:
        return {"available": False}
    return {"available": True, **diff}


@router.get("/{project_id}/risks")
def get_risks(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return store.read_artifact(project_id, "risk_report.json")


@router.get("/{project_id}/report")
def get_summary_report(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return {"project_id": project_id, "markdown": store.read_report(project_id, "summary.md")}
