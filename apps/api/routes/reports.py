from fastapi import APIRouter, Depends
from klave_engine.common.config import Settings
from klave_engine.costing.insumos import default_price_book
from klave_engine.costing.models import CostingConfig, CostingOverrides
from klave_engine.costing.recompute import load_overrides, recompute_and_persist

from apps.api.dependencies import ProjectStore, get_settings, get_store

router = APIRouter(prefix="/projects")


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
        "has_overrides": overrides is not None,
    }


@router.post("/{project_id}/recompute")
def recompute(
    project_id: str,
    overrides: CostingOverrides,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Rebuild the cost report with edited parameters/prices (no re-detection)."""
    root = store.get_root(project_id)
    report = recompute_and_persist(
        root / settings.processed_dir_name, root / "reports", project_id, overrides
    )
    return report.model_dump(mode="json")


@router.get("/{project_id}/risks")
def get_risks(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return store.read_artifact(project_id, "risk_report.json")


@router.get("/{project_id}/report")
def get_summary_report(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return {"project_id": project_id, "markdown": store.read_report(project_id, "summary.md")}
