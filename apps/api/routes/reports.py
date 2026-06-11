from fastapi import APIRouter, Depends

from apps.api.dependencies import ProjectStore, get_store

router = APIRouter(prefix="/projects")


@router.get("/{project_id}/quantities")
def get_quantities(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return store.read_artifact(project_id, "quantity_report.json")


@router.get("/{project_id}/costs")
def get_costs(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return store.read_artifact(project_id, "cost_report.json")


@router.get("/{project_id}/risks")
def get_risks(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return store.read_artifact(project_id, "risk_report.json")


@router.get("/{project_id}/report")
def get_summary_report(project_id: str, store: ProjectStore = Depends(get_store)) -> dict:
    return {"project_id": project_id, "markdown": store.read_report(project_id, "summary.md")}
