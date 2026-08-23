"""Access control: one policy for the whole API surface.

Every mutating request must come from an allowed browser origin (CSRF guard,
in open and protected mode alike; non-browser clients send no Origin and pass).
In open mode (no accounts) every request then passes untouched, preserving the
original local-first behavior. In protected mode a session cookie is required,
pending/disabled accounts are refused, and project routes enforce per-project
roles (viewer < editor < owner; admins pass everything within their workspace). If the
users database goes down after accounts have been seen, the API fails closed.
"""

import json
import re
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import urlsplit

from klave_engine.common.config import get_settings

from apps.api.auth.store import ROLE_RANK, UsersDbUnavailable, get_user_store

SESSION_COOKIE = "klave_session"

OPEN_PREFIXES = ("/health", "/auth/", "/docs", "/openapi.json", "/redoc")

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
_LOCAL_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")


def allowed_origins() -> list[str]:
    """Browser origins that may call the API with credentials."""
    settings = get_settings()
    origins = [settings.web_origin.rstrip("/")]
    origins += [o.strip().rstrip("/") for o in settings.extra_origins.split(",") if o.strip()]
    return origins


def origin_allowed(origin: str | None) -> bool:
    if origin is None:
        return True  # non-browser clients carry no session cookie to forge with
    origin = origin.rstrip("/")
    return origin in allowed_origins() or bool(_LOCAL_ORIGIN.match(origin))


def _header(scope: dict[str, Any], name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None


def _request_origin(scope: dict[str, Any]) -> str | None:
    """Origin, or the Referer's origin when a browser omitted Origin."""
    origin = _header(scope, b"origin")
    if origin:
        return origin
    referer = _header(scope, b"referer")
    if referer:
        parsed = urlsplit(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return None


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


def _set_actor_header(scope: dict, name: str) -> None:
    headers = [(k, v) for k, v in scope.get("headers", []) if k.lower() != b"x-actor"]
    headers.append((b"x-actor", name.encode("utf-8", "replace")[:120]))
    scope["headers"] = headers


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
        if method == "OPTIONS" or path == "/":
            await self.app(scope, receive, send)
            return
        # CSRF: a browser must come from our own origin to change anything.
        # This runs before the open-prefix pass so login/register are covered.
        if method in _MUTATING and not origin_allowed(_request_origin(scope)):
            status, body = _deny(
                403, "origin_not_allowed",
                "Solicitud desde un origen no permitido.",
            )
            await _respond(send, status, body)
            return
        if any(path == p.rstrip("/") or path.startswith(p) for p in OPEN_PREFIXES):
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
                # Attribution is the session's, never the header's: a signed
                # in user cannot sign a review or a version as someone else.
                _set_actor_header(scope, str(user["name"]))
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
        await _respond(send, status, body)


async def _respond(send: Any, status: int, body: bytes) -> None:
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
