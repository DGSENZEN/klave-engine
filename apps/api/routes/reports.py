import threading
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from klave_engine.common.config import Settings
from klave_engine.costing.insumos import default_price_book
from klave_engine.costing.models import CostingConfig, CostingOverrides
from klave_engine.costing.recompute import load_overrides, recompute_and_persist

from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import BUS, clean_actor, clean_client_id
from apps.api.jobs import ACTIVE_STATES, JOB_STORE

router = APIRouter(prefix="/projects")

# Serializes the read-check-write of a project's costing overrides so two
# concurrent recomputes cannot interleave between version check and save.
_recompute_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _recompute_lock(project_id: str) -> threading.Lock:
    with _locks_guard:
        return _recompute_locks.setdefault(project_id, threading.Lock())


@router.get("/{project_id}/quantities")
def get_quantities(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return store.read_artifact(project_id, "quantity_report.json")


@router.get("/{project_id}/costs")
def get_costs(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return store.read_artifact(project_id, "cost_report.json")


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
    insumos = [
        {**resource.model_dump(mode="json"), "unit_cost": prices.get(code, resource.unit_cost)}
        for code, resource in default_price_book().items()
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
    with _recompute_lock(project_id):
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


@router.get("/{project_id}/risks")
def get_risks(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return store.read_artifact(project_id, "risk_report.json")


@router.get("/{project_id}/report")
def get_summary_report(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return {"project_id": project_id, "markdown": store.read_report(project_id, "summary.md")}
