"""Presupuesto versions: save the current state under a name, list, compare
(a version against the current presupuesto or against another version),
restore the human decisions of a version onto the current run, delete."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from klave_engine.common.config import Settings
from klave_engine.common.errors import ReportGenerationError
from klave_engine.costing.models import CostingOverrides, CostReport
from klave_engine.costing.presentation import publishable_total
from klave_engine.costing.recompute import (
    load_overrides,
    recompute_and_persist,
    save_overrides,
)
from klave_engine.costing.reviews import load_reviews, save_reviews
from klave_engine.costing.versions import (
    VersionDiff,
    delete_version,
    diff_reports,
    list_versions,
    load_version,
    save_version,
)
from pydantic import BaseModel, Field

from apps.api.dependencies import (
    ProjectStore,
    get_settings,
    get_store,
    project_recompute_lock,
)
from apps.api.events import BUS, clean_actor, clean_client_id
from apps.api.tenancy import store_for_project

router = APIRouter(prefix="/projects")


class VersionInput(BaseModel):
    label: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=500)


def _current_report(store: ProjectStore, project_id: str) -> CostReport:
    return CostReport.model_validate(store.read_artifact(project_id, "cost_report.json"))


def _not_found(version_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error_type": "version_not_found", "version_id": version_id},
    )


@router.get("/{project_id}/versions")
def get_versions(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    versions = list_versions(control_dir)
    return {
        "versions": [v.model_dump(mode="json") for v in versions],
        "active_run_id": store.active_run_id(project_id),
    }


@router.post("/{project_id}/versions", status_code=201)
def create_version(
    project_id: str,
    body: VersionInput,
    x_actor: Annotated[str | None, Header()] = None,
    x_client_id: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    actor = clean_actor(x_actor) or ""
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    with project_recompute_lock(project_id):
        report = _current_report(store, project_id)
        reviews = load_reviews(control_dir)
        summary = save_version(
            control_dir,
            report,
            reviews,
            load_overrides(control_dir) or CostingOverrides(),
            label=body.label,
            note=body.note,
            actor=actor,
            run_id=store.active_run_id(project_id),
        )
    # The saved version keeps its own total (it is the record of what was
    # signed), but the broadcast is a money surface: nothing on the bus
    # carries a total the presupuesto page refuses to show.
    BUS.publish(
        "version_saved",
        project_id=project_id,
        actor=actor,
        data={
            "client_id": clean_client_id(x_client_id),
            "version_id": summary.version_id,
            "number": summary.number,
            "label": summary.label,
            "grand_total": publishable_total(report, reviews.verification),
        },
    )
    return summary.model_dump(mode="json")


@router.get("/{project_id}/versions/{version_id}")
def get_version(
    project_id: str,
    version_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    version = load_version(control_dir, version_id)
    if version is None:
        raise _not_found(version_id)
    return version.model_dump(mode="json")


@router.get("/{project_id}/versions/{version_id}/diff")
def get_version_diff(
    project_id: str,
    version_id: str,
    against: str = "current",
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Movement from the version to ``against`` ("current" or another
    version id): what the presupuesto gained, lost, and changed since."""
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    version = load_version(control_dir, version_id)
    if version is None:
        raise _not_found(version_id)
    before_label = f"v{version.summary.number} · {version.summary.label}"
    if against == "current":
        after = _current_report(store, project_id)
        after_label = "Presupuesto actual"
    else:
        other = load_version(control_dir, against)
        if other is None:
            raise _not_found(against)
        after = other.report
        after_label = f"v{other.summary.number} · {other.summary.label}"
    diff: VersionDiff = diff_reports(
        version.report, after, before_label=before_label, after_label=after_label
    )
    active = store.active_run_id(project_id)
    saved_on = version.summary.run_id
    if against == "current" and saved_on and active and saved_on != active:
        diff.notes.append(
            "La versión se guardó sobre otra corrida de detección; parte del movimiento "
            "puede venir de una nueva lectura del plano, no de decisiones humanas."
        )
    return diff.model_dump(mode="json")


@router.post("/{project_id}/versions/{version_id}/restore")
def restore_version(
    project_id: str,
    version_id: str,
    x_actor: Annotated[str | None, Header()] = None,
    x_client_id: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Reapply the version's human decisions (reviews, adjustments, costing
    overrides) on the current run and recompute. The current state is saved
    first as its own version, so nothing is lost by restoring."""
    actor = clean_actor(x_actor) or ""
    root = store.get_root(project_id)
    control_dir = root / settings.processed_dir_name
    version = load_version(control_dir, version_id)
    if version is None:
        raise _not_found(version_id)
    with project_recompute_lock(project_id):
        try:
            current = _current_report(store, project_id)
        except HTTPException:
            current = None
        current_overrides = load_overrides(control_dir) or CostingOverrides()
        # Captured before save_reviews below replaces them: the "antes" total
        # belongs to the sign-off that was in force when that report was the
        # live one, and the "después" total to the sign-off being restored.
        previous_reviews = load_reviews(control_dir)
        if current is not None:
            save_version(
                control_dir,
                current,
                previous_reviews,
                current_overrides,
                label=f"Antes de restaurar v{version.summary.number}",
                note="Guardada automáticamente al restaurar.",
                actor=actor,
                run_id=store.active_run_id(project_id),
            )
        restored = version.overrides.model_copy(
            update={"version": current_overrides.version + 1, "updated_by": actor or None}
        )
        save_reviews(control_dir, version.reviews)
        save_overrides(control_dir, restored)
        try:
            report = recompute_and_persist(
                store.artifact_root(project_id), control_dir, root / "reports", project_id,
                restored,
                catalog_store=store_for_project(settings, project_id),
            )
        except ReportGenerationError as exc:
            raise HTTPException(
                status_code=409,
                detail={"error_type": "not_processed", "message": str(exc)},
            ) from exc
    BUS.publish(
        "version_restored",
        project_id=project_id,
        actor=actor,
        data={
            "client_id": clean_client_id(x_client_id),
            "version_id": version_id,
            "number": version.summary.number,
            "label": version.summary.label,
        },
    )
    BUS.publish(
        "costing_updated",
        project_id=project_id,
        actor=actor,
        data={
            "client_id": clean_client_id(x_client_id),
            "version": restored.version,
            "direct_cost": report.boq.direct_cost_total,
            "grand_total": publishable_total(report, version.reviews.verification),
            "prev_grand_total": (
                publishable_total(current, previous_reviews.verification)
                if current else None
            ),
            "review_action": "version_restored",
        },
    )
    return {
        "restored": version.summary.model_dump(mode="json"),
        "direct_cost": report.boq.direct_cost_total,
        "grand_total": report.integration.grand_total,
        "same_run": version.summary.run_id == store.active_run_id(project_id),
    }


@router.delete("/{project_id}/versions/{version_id}")
def remove_version(
    project_id: str,
    version_id: str,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    with project_recompute_lock(project_id):
        if not delete_version(control_dir, version_id):
            raise _not_found(version_id)
    BUS.publish(
        "version_deleted",
        project_id=project_id,
        actor=clean_actor(x_actor) or "",
        data={"version_id": version_id},
    )
    return {"deleted": version_id}
