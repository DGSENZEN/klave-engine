"""Workspace-level surfaces: the home overview (what needs attention), the
taller defaults new projects inherit, and the workspace name."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from klave_engine.common.config import Settings
from klave_engine.common.io import read_json
from klave_engine.common.version import engine_fingerprint
from klave_engine.costing.defaults import (
    clear_workspace_defaults,
    load_workspace_defaults,
    save_workspace_defaults,
)
from klave_engine.costing.models import CostingConfig
from klave_engine.costing.reviews import REVIEWS_FILENAME, load_reviews
from klave_engine.costing.vigencia import FRESH_MONTHS, freshness
from pydantic import BaseModel, Field

from apps.api.auth.store import UsersDbUnavailable, get_user_store
from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import BUS, clean_actor
from apps.api.jobs import JOB_STORE
from apps.api.routes.projects import visible_project_filter
from apps.api.tenancy import defaults_scope, request_workspace_id, store_for_request

router = APIRouter(prefix="/workspace", tags=["workspace"])

STALE_MONTHS = FRESH_MONTHS  # "más de 6 meses" = the catálogo's revisar + vencido


def _state_user(request: Request) -> dict[str, Any] | None:
    return getattr(request.state, "user", None)


def _require_admin_if_protected(request: Request) -> dict[str, Any] | None:
    """Open mode (no accounts) keeps the local-first freedom; protected mode
    restricts workspace-wide settings to administrators."""
    user = _state_user(request)
    if user is not None and user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail={"error_type": "admin_required", "message": "Requiere administrador."},
        )
    return user


def _months_old(vigencia: str | None, today: datetime) -> int | None:
    if not vigencia:
        return None
    try:
        year, month = (int(part) for part in vigencia.split("-")[:2])
    except ValueError:
        return None
    return (today.year - year) * 12 + (today.month - month)


def _latest_mtime(paths: list[Path]) -> datetime | None:
    stamps = [path.stat().st_mtime for path in paths if path.exists()]
    if not stamps:
        return None
    return datetime.fromtimestamp(max(stamps), tz=UTC)


def _project_overview(
    store: ProjectStore, settings: Settings, project_id: str, root: Path
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "project_id": project_id,
        "name": project_id,
        "status": "unknown",
        "client": None,
        "archived": False,
        "sheet_count": 0,
        "created_at": None,
        "verified": False,
        "exported": (root / settings.processed_dir_name / "last_export.json").exists(),
        "verification": {"units": False, "detections": False, "assumptions": False},
        "excluded_count": 0,
        "adjustment_count": 0,
        "grand_total": None,
        "currency": "MXN",
        "last_activity": None,
        "job_error": None,
        "engine_stale": False,
    }
    control_dir = root / settings.processed_dir_name
    try:
        manifest = store.get_manifest(project_id)
        entry.update(
            name=manifest.project_name,
            status=manifest.processing_status.value,
            client=manifest.client,
            archived=manifest.archived,
            sheet_count=len(manifest.source_files),
            created_at=manifest.created_at.isoformat(),
        )
    except Exception:
        return entry
    job = JOB_STORE.get(project_id, root, settings)
    if job is not None:
        if job.state in ("queued", "running"):
            entry["status"] = job.state
        elif job.state == "failed":
            entry["status"] = "failed"
            entry["job_error"] = job.error

    reviews = load_reviews(control_dir)
    verification = reviews.verification
    steps = {
        "units": verification.units_confirmed_at is not None,
        "detections": verification.detections_confirmed_at is not None,
        "assumptions": verification.assumptions_confirmed_at is not None,
    }
    entry["verification"] = steps
    entry["verified"] = all(steps.values())
    entry["excluded_count"] = sum(
        1 for r in reviews.detections.values() if r.status == "excluded"
    )
    entry["adjustment_count"] = len(reviews.adjustments)

    override = control_dir / "cost_report_override.json"
    report_path = (
        override if override.exists() else store.artifact_root(project_id) / "cost_report.json"
    )
    if report_path.exists():
        try:
            report = read_json(report_path)
            entry["grand_total"] = report["integration"]["grand_total"]
            entry["currency"] = report.get("currency", "MXN")
        except (KeyError, TypeError, ValueError, OSError):
            pass
    if entry["status"] == "processed":
        engine_path = store.artifact_root(project_id) / "engine.json"
        try:
            stamp = read_json(engine_path) if engine_path.exists() else {}
        except (ValueError, OSError):
            stamp = {}
        entry["engine_stale"] = stamp.get("fingerprint") != engine_fingerprint()
    activity = _latest_mtime(
        [control_dir / REVIEWS_FILENAME, override, control_dir / "active_run.json", report_path]
    )
    entry["last_activity"] = (activity.isoformat() if activity else entry["created_at"])
    return entry


@router.get("/overview")
def overview(
    request: Request,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Everything the home needs in one call: projects with their verification
    and totals, plus the counts that deserve attention."""
    keep = visible_project_filter(request, store)
    projects = [
        _project_overview(store, settings, project_id, Path(root))
        for project_id, root in store.list_projects().items()
        if keep(project_id)
    ]
    projects.sort(key=lambda p: p.get("last_activity") or "", reverse=True)
    active = [p for p in projects if not p["archived"]]

    user = _state_user(request)
    pending_users: int | None = None
    workspace: dict[str, Any] | None = None
    if user is not None:
        try:
            users = get_user_store(settings.users_database_url)
            ws = users.get_workspace(str(user["workspace_id"]))
            workspace = {"slug": ws["slug"], "name": ws["name"]} if ws else None
            if user["role"] == "admin":
                members = users.list_users(str(user["workspace_id"]))
                pending_users = sum(1 for u in members if u["status"] == "pending")
        except UsersDbUnavailable:
            pass

    stale = 0
    try:
        for row in store_for_request(settings, request).list_insumos():
            if freshness(row.get("vigencia")) != "vigente":
                stale += 1
    except Exception:
        stale = 0

    catalog_store = store_for_request(settings, request)
    onboarding = {
        "sample_explored": any(p["project_id"].startswith("obra_de_ejemplo") for p in projects),
        "first_project": any(
            not p["project_id"].startswith("obra_de_ejemplo") for p in projects
        ),
        "any_verified": any(p["verified"] for p in projects),
        "aliases": len(catalog_store.load_concept_aliases()),
        "any_exported": any(p.get("exported") for p in projects),
    }
    return {
        "projects": projects,
        "onboarding": onboarding,
        "attention": {
            "processing": sum(1 for p in active if p["status"] in ("queued", "running")),
            "failed": sum(1 for p in active if p["status"] == "failed"),
            "unverified": sum(
                1 for p in active if p["status"] == "processed" and not p["verified"]
            ),
            "stale_runs": sum(1 for p in active if p["engine_stale"]),
            "pending_users": pending_users,
            "stale_insumos": stale,
            "stale_threshold_months": STALE_MONTHS,
        },
        "workspace": workspace
        or {"slug": settings.workspace_slug, "name": settings.workspace_name},
        "mode": "protected" if user is not None else "open",
        "is_admin": user is None or user["role"] == "admin",
    }


# ---------------------------------------------------------------- defaults

class DefaultsInput(BaseModel):
    config: CostingConfig


def _defaults_payload(settings: Settings, request: Request | None = None) -> dict:
    scope = defaults_scope(settings, request_workspace_id(request))
    defaults = load_workspace_defaults(scope)
    return {
        "config": (defaults.config if defaults else CostingConfig()).model_dump(mode="json"),
        "customized": defaults is not None,
        "updated_by": defaults.updated_by if defaults else None,
        "updated_at": (
            defaults.updated_at.isoformat() if defaults and defaults.updated_at else None
        ),
    }


@router.get("/defaults")
def get_defaults(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    return _defaults_payload(settings, request)


@router.put("/defaults")
def put_defaults(
    body: DefaultsInput,
    request: Request,
    x_actor: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> dict:
    user = _require_admin_if_protected(request)
    actor = user["name"] if user else clean_actor(x_actor)
    save_workspace_defaults(
        defaults_scope(settings, request_workspace_id(request)), body.config, actor
    )
    if user is not None:
        try:
            get_user_store(settings.users_database_url).record_audit(
                workspace_id=str(user["workspace_id"]), actor=user,
                action="workspace_defaults_updated", target_type="workspace", target_id=None,
            )
        except UsersDbUnavailable:
            pass
    BUS.publish(
        "workspace_defaults_updated", actor=actor, data={},
        workspace_id=request_workspace_id(request),
    )
    return _defaults_payload(settings, request)


@router.delete("/defaults")
def delete_defaults(
    request: Request,
    x_actor: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> dict:
    user = _require_admin_if_protected(request)
    clear_workspace_defaults(defaults_scope(settings, request_workspace_id(request)))
    BUS.publish(
        "workspace_defaults_updated",
        actor=user["name"] if user else clean_actor(x_actor),
        data={"reset": True},
        workspace_id=request_workspace_id(request),
    )
    return _defaults_payload(settings, request)


# ------------------------------------------------------------------- name

class WorkspaceInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)


@router.put("")
def rename_workspace(
    body: WorkspaceInput, request: Request, settings: Settings = Depends(get_settings)
) -> dict:
    user = _require_admin_if_protected(request)
    if user is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": "open_mode",
                "message": "Activa las cuentas del taller para nombrarlo.",
            },
        )
    try:
        users = get_user_store(settings.users_database_url)
        workspace = users.rename_workspace(str(user["workspace_id"]), body.name)
        users.record_audit(
            workspace_id=str(user["workspace_id"]), actor=user,
            action="workspace_renamed", target_type="workspace", target_id=None,
            detail={"name": body.name},
        )
    except UsersDbUnavailable as exc:
        raise HTTPException(status_code=503, detail={"error_type": "users_db_unavailable"}) from exc
    return {"slug": workspace["slug"], "name": workspace["name"]}
