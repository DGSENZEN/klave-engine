"""Aliases and variant mappings: the taller's shared memory of "this drawing
label means this concept" (role design, decision 3).

Editors add what is not mapped yet, during review. Changing or removing an
existing one silently moves quantities in every project of the taller, so it
is the administrator's. The example obra keeps its own catálogo: there the
owner decides everything and nothing reaches the taller's audit log.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException, Request
from klave_engine.common.config import get_settings
from klave_engine.ejemplo import es_obra_de_ejemplo

from apps.api.auth import access
from apps.api.auth.common import audit

ALIAS_CHANGE_MESSAGE = (
    "Ese alias ya existe en el catálogo del taller; cambiarlo o quitarlo lo decide "
    "un administrador."
)
VARIANT_CHANGE_MESSAGE = (
    "Esa variante ya tiene una decisión en el catálogo del taller; cambiarla lo decide un "
    "administrador."
)

MappingAction = Literal[
    "alias_added", "alias_changed", "alias_cleared",
    "variant_mapped", "variant_remapped", "variant_forgotten",
]  # fmt: skip


def _free(request: Request, project_id: str) -> bool:
    """Open mode, an administrator, or the example obra's own sandbox."""
    return (
        getattr(request.state, "user", None) is None
        or access.is_taller_admin(request)
        or es_obra_de_ejemplo(project_id)
    )


def require_mapping_project(request: Request, project_id: str) -> None:
    """A member adds a shared mapping from a project they edit; without one
    there is no project role to check, so only an administrator may."""
    if project_id or getattr(request.state, "user", None) is None:
        return
    access.require_taller_admin(
        request, "Un alias se agrega desde un proyecto en el que puedas editar."
    )


def alias_target(row: dict | None) -> tuple[str | None, int | None, str | None] | None:
    """What an alias points at, comparable across a stored row and a request."""
    if not row:
        return None
    return (row.get("kind"), row.get("ref_id"), row.get("target_code"))


def check_alias_writes(
    request: Request,
    project_id: str,
    existing: dict[str, dict],
    items: list[tuple[str, tuple]],
    adopted_prices: dict[str, float] | None = None,
) -> None:
    """Refuse the whole request when any item would change what the taller
    already decided and the caller may not: re-point an existing alias, or —
    since setting an alias re-prices the concept — replace a price an
    administrator adopted. Re-sending the same target is no change."""
    if _free(request, project_id):
        return
    adopted_prices = adopted_prices or {}
    cambios = [
        {"concept_code": code, "actual": _alias_view(existing[code])}
        for code, target in items
        if code in existing and alias_target(existing[code]) != target
    ] + [
        {"concept_code": code, "actual": {"price_override": adopted_prices[code]}}
        for code, _target in items
        if code not in existing and code in adopted_prices
    ]
    if cambios:
        raise HTTPException(
            status_code=403,
            detail={"error_type": "admin_required", "message": ALIAS_CHANGE_MESSAGE,
                    "cambios": cambios},
        )  # fmt: skip


def _alias_view(row: dict) -> dict:
    return {k: row.get(k) for k in ("kind", "ref_id", "target_code", "clave", "description")}


def check_mapping_removal(
    request: Request, project_id: str, message: str = ALIAS_CHANGE_MESSAGE
) -> None:
    """Removing a shared mapping is the administrator's, except in the sandbox."""
    if es_obra_de_ejemplo(project_id):
        return
    access.require_taller_admin(request, message)


def audit_mapping(
    request: Request,
    project_id: str,
    action: MappingAction,
    target_id: str,
    previous: dict | None,
    new: dict | None,
) -> None:
    """One taller audit entry per write to a taller catálogo's shared mappings."""
    user = getattr(request.state, "user", None)
    if user is None or es_obra_de_ejemplo(project_id):
        return
    users = access.get_user_store(get_settings().users_database_url)
    audit(
        users, user, action,
        target_type="concept" if action.startswith("alias") else "variant",
        target_id=target_id,
        detail={"project_id": project_id, "previous": _plain(previous), "new": _plain(new)},
    )  # fmt: skip


def _plain(row: dict | None) -> dict[str, Any] | None:
    if not row:
        return None
    keep = ("kind", "ref_id", "target_code", "target_kind", "clave", "status")
    return {k: row[k] for k in keep if k in row}


def is_human_decision(row: dict | None) -> bool:
    """A person decided this mapping. Engine proposals (``automatica``,
    ``propuesta``, and ``sin_equivalente`` written by ``motor``) are not
    decisions: editors confirm or replace them as part of review."""
    if not row:
        return False
    if row.get("status") == "confirmada":
        return True
    return row.get("status") == "sin_equivalente" and (row.get("actor") or "") not in ("", "motor")


def mapping_target(
    status: str, target_kind: str | None, target_code: str | None, ref_id: int | None
) -> tuple[str, str | None, str | None, int | None]:
    """A variant mapping's decision, comparable across a stored row (empty
    strings) and a request (None)."""
    return (status, target_kind or None, target_code or None, ref_id)


def check_variant_write(
    request: Request,
    project_id: str,
    previous: dict | None,
    new: tuple[str, str | None, str | None, int | None],
) -> None:
    """Changing a person's decision on a taller variant is the administrator's;
    re-sending the same decision is no change."""
    if _free(request, project_id) or not is_human_decision(previous):
        return
    assert previous is not None
    stored = mapping_target(
        previous["status"], previous.get("target_kind"), previous.get("target_code"),
        previous.get("ref_id"),
    )  # fmt: skip
    if stored != new:
        access.require_taller_admin(request, VARIANT_CHANGE_MESSAGE)
