"""Which taller's data a request or a project works on.

The catálogo, its defaults and everything derived from them are one file per
workspace (``data/catalogs/<workspace_id>.db``). Open mode — no user store,
the original local-first deployment — keeps the single ``data/catalog.db``.
The default workspace adopts that legacy file the first time it is opened,
so a taller that grew into protected mode keeps every price it had.
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

from fastapi import Request
from klave_engine.common.config import Settings
from klave_engine.common.logging import get_logger
from klave_engine.costing.catalog_store import CATALOG_DB_FILENAME, CatalogStore, get_catalog_store

from apps.api.auth.store import UsersDbUnavailable, get_user_store

logger = get_logger(__name__)
_ADOPT_LOCK = threading.Lock()

CATALOGS_DIR = "catalogs"


def request_workspace_id(request: Request | None) -> str | None:
    """The taller of the signed-in user; None in open mode."""
    if request is None:
        return None
    user = getattr(request.state, "user", None)
    if not user:
        return None
    workspace = user.get("workspace_id")
    return str(workspace) if workspace else None


def default_workspace_id(settings: Settings) -> str | None:
    try:
        users = get_user_store(settings.users_database_url)
        if not users.has_users():
            return None
        return str(users.default_workspace()["workspace_id"])
    except UsersDbUnavailable:
        return None


def project_workspace_id(settings: Settings, project_id: str) -> str | None:
    """The taller a project belongs to; None in open mode."""
    try:
        users = get_user_store(settings.users_database_url)
        if not users.has_users():
            return None
        return users.project_workspace_id(project_id)
    except UsersDbUnavailable:
        return None


def _adopt_legacy(settings: Settings, workspace_id: str) -> None:
    """The default workspace inherits the pre-workspace catálogo and defaults."""
    target = settings.data_dir / CATALOGS_DIR / f"{workspace_id}.db"
    legacy = settings.data_dir / CATALOG_DB_FILENAME
    with _ADOPT_LOCK:
        if target.exists() or not legacy.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, target)
        legacy_defaults = settings.data_dir / "taller_defaults.json"
        if legacy_defaults.exists():
            shutil.copy2(
                legacy_defaults, settings.data_dir / CATALOGS_DIR / f"{workspace_id}-defaults.json"
            )
        logger.info(
            "catalog_adopted_by_default_workspace", extra={"workspace_id": workspace_id}
        )


def workspace_store(settings: Settings, workspace_id: str | None) -> CatalogStore:
    """The taller's own catálogo; the legacy shared one only in open mode."""
    if workspace_id is None:
        return get_catalog_store(settings.data_dir)
    if workspace_id == default_workspace_id(settings):
        _adopt_legacy(settings, workspace_id)
    return get_catalog_store(settings.data_dir, workspace_id=workspace_id)


def store_for_request(settings: Settings, request: Request | None) -> CatalogStore:
    return workspace_store(settings, request_workspace_id(request))


def store_for_project(settings: Settings, project_id: str) -> CatalogStore:
    return workspace_store(settings, project_workspace_id(settings, project_id))


def defaults_scope(settings: Settings, workspace_id: str | None) -> Path:
    """Where this taller's ``taller_defaults`` live (a directory + prefix contract
    shared with ``klave_engine.costing.defaults``)."""
    if workspace_id is None:
        return settings.data_dir
    if workspace_id == default_workspace_id(settings):
        _adopt_legacy(settings, workspace_id)
    return settings.data_dir / CATALOGS_DIR / workspace_id
