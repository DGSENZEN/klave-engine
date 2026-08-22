"""Access control: one policy for the whole API surface.

In open mode (no accounts) every request passes untouched, preserving the
original local-first behavior. In protected mode a session cookie is required,
pending/disabled accounts are refused, and project routes enforce per-project
roles (viewer < editor < owner; admins pass everything within their workspace). If the
users database goes down after accounts have been seen, the API fails closed.
"""

import json
from http.cookies import SimpleCookie
from typing import Any

from klave_engine.common.config import get_settings

from apps.api.auth.store import ROLE_RANK, UsersDbUnavailable, get_user_store

SESSION_COOKIE = "klave_session"

OPEN_PREFIXES = ("/health", "/auth/", "/docs", "/openapi.json", "/redoc")

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _cookie_token(scope: dict[str, Any]) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            cookie = SimpleCookie()
            cookie.load(value.decode("latin-1"))
            morsel = cookie.get(SESSION_COOKIE)
            return morsel.value if morsel else None
    return None


def _required_project_role(segments: list[str], method: str) -> str | None:
    """Role needed for /projects/... paths; None means active-user only."""
    if len(segments) < 2 or segments[1] == "upload":
        return None
    if len(segments) == 2:
        return "owner" if method in ("PATCH", "DELETE") else "viewer"
    if segments[2] in ("files", "access"):
        return "owner"
    if method in _MUTATING:
        return "editor"
    return "viewer"


def _deny(status: int, error_type: str, message: str) -> tuple[int, bytes]:
    return status, json.dumps(
        {"detail": {"error_type": error_type, "message": message}}
    ).encode()


class AccessControlMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method: str = scope["method"]
        path: str = scope["path"]
        if method == "OPTIONS" or path == "/" or any(
            path == p.rstrip("/") or path.startswith(p) for p in OPEN_PREFIXES
        ):
            await self.app(scope, receive, send)
            return

        store = get_user_store(get_settings().users_database_url)
        denial: tuple[int, bytes] | None = None
        try:
            if not store.has_users():
                scope.setdefault("state", {})["user"] = None
                await self.app(scope, receive, send)
                return
            user = store.get_session_user(_cookie_token(scope))
            if user is None:
                denial = _deny(401, "auth_required", "Inicia sesión para continuar.")
            elif user["status"] == "pending":
                denial = _deny(
                    403, "pending_approval",
                    "Tu cuenta espera la aprobación de un administrador.",
                )
            elif user["status"] != "active":
                denial = _deny(403, "account_disabled", "Tu cuenta está deshabilitada.")
            else:
                scope.setdefault("state", {})["user"] = user
                segments = [s for s in path.split("/") if s]
                if segments and segments[0] == "projects":
                    required = _required_project_role(segments, method)
                    if required is not None and user["role"] == "admin":
                        # Admins pass every role check, but only inside
                        # their own workspace.
                        if store.project_workspace_id(segments[1]) != str(
                            user["workspace_id"]
                        ):
                            denial = _deny(
                                403, "forbidden_project", "Proyecto de otro taller."
                            )
                    elif required is not None:
                        role = store.project_role(segments[1], str(user["user_id"]))
                        if role is None or ROLE_RANK[role] < ROLE_RANK[required]:
                            denial = _deny(
                                403, "forbidden_project",
                                "No tienes acceso suficiente a este proyecto.",
                            )
        except UsersDbUnavailable:
            if store.last_known_has_users:
                denial = _deny(
                    503, "users_db_unavailable",
                    "La base de datos de usuarios no está disponible.",
                )
            else:
                scope.setdefault("state", {})["user"] = None
                await self.app(scope, receive, send)
                return

        if denial is None:
            await self.app(scope, receive, send)
            return
        status, body = denial
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
