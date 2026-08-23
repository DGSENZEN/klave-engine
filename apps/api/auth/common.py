"""Helpers shared by the auth routers: session lookup, guards, cookies,
rate limiting, audit, and the public user shape."""

import threading
import time
from collections import deque
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import HTTPException
from klave_engine.common.config import Settings, get_settings

from apps.api.auth.middleware import SESSION_COOKIE
from apps.api.auth.store import UserStore, get_user_store

# Sliding-window rate limit for credential endpoints: 10 attempts per 5
# minutes per client address. In-memory is right for the single-process
# workspace API; a shared limiter belongs to the hosted deployment.
_RATE_WINDOW_SECONDS = 300.0
_RATE_MAX_ATTEMPTS = 10
_rate_buckets: dict[str, deque[float]] = {}
_rate_lock = threading.Lock()


def rate_limit(request: Request, bucket: str) -> None:
    host = request.client.host if request.client else "?"
    key = f"{bucket}:{host}"
    now = time.monotonic()
    with _rate_lock:
        attempts = _rate_buckets.setdefault(key, deque())
        while attempts and now - attempts[0] > _RATE_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= _RATE_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=429,
                detail={
                    "error_type": "rate_limited",
                    "message": "Demasiados intentos; espera unos minutos.",
                },
                headers={"Retry-After": "60"},
            )
        attempts.append(now)


def get_users(settings: Settings | None = None) -> UserStore:
    settings = settings or get_settings()
    return get_user_store(settings.users_database_url)


def users_dependency() -> UserStore:
    return get_users(get_settings())


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    has_password = (
        bool(user["has_password"]) if "has_password" in user else bool(user.get("password_hash"))
    )
    has_google = (
        bool(user["has_google"]) if "has_google" in user else bool(user.get("google_sub"))
    )
    return {
        "user_id": str(user["user_id"]),
        "email": user["email"],
        "name": user["name"],
        "picture": user.get("picture"),
        "role": user["role"],
        "status": user["status"],
        "email_verified": user.get("email_verified_at") is not None,
        "pending_email": user.get("pending_email"),
        "has_password": has_password,
        "has_google": has_google,
    }


def session_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def session_user(request: Request, users: UserStore) -> dict[str, Any] | None:
    return users.get_session_user(session_token(request))


def require_user(request: Request, users: UserStore) -> dict[str, Any]:
    user = session_user(request, users)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"error_type": "auth_required", "message": "Inicia sesión."},
        )
    return user


def require_active_user(request: Request, users: UserStore) -> dict[str, Any]:
    user = require_user(request, users)
    if user["status"] != "active":
        raise HTTPException(
            status_code=403,
            detail={"error_type": "account_inactive", "message": "Tu cuenta no está activa."},
        )
    return user


def require_admin(request: Request, users: UserStore) -> dict[str, Any]:
    user = require_user(request, users)
    if user["role"] != "admin" or user["status"] != "active":
        raise HTTPException(
            status_code=403,
            detail={"error_type": "admin_required", "message": "Requiere administrador."},
        )
    return user


def client_meta(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    return user_agent, ip


def start_session(
    request: Request,
    response: Response,
    users: UserStore,
    settings: Settings,
    user_id: str,
    *,
    remember: bool = False,
) -> None:
    user_agent, ip = client_meta(request)
    token = users.create_session(user_id, remember=remember, user_agent=user_agent, ip=ip)
    set_session_cookie(response, token, settings, remember=remember)


def set_session_cookie(
    response: Response, token: str, settings: Settings, *, remember: bool = False
) -> None:
    # Without "remember" the cookie is browser-session scoped; the server side
    # still slides its 24 h expiry while the tab stays in use.
    samesite = settings.cookie_samesite.lower()
    if samesite not in ("lax", "none", "strict"):
        samesite = "lax"
    secure = (
        settings.cookie_secure
        if settings.cookie_secure is not None
        else settings.web_origin.startswith("https") or samesite == "none"
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite=samesite,  # type: ignore[arg-type]
        secure=secure,
        max_age=60 * 60 * 24 * 30 if remember else None,
        path="/",
        domain=settings.cookie_domain or None,
    )


def db_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error_type": "users_db_unavailable",
            "message": "La base de datos de usuarios no está disponible (make users-db-up).",
        },
    )


def web_link(settings: Settings, path: str) -> str:
    return settings.web_origin.rstrip("/") + path


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[:1]}…@{domain}"
    return f"{local[:2]}…{local[-1]}@{domain}"


def audit(
    users: UserStore,
    actor: dict[str, Any] | None,
    action: str,
    *,
    workspace_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    users.record_audit(
        workspace_id=workspace_id or (str(actor["workspace_id"]) if actor else None),
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
