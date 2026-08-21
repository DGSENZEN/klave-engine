"""Accounts, sessions, Google sign-in, the admin confirmation loop, and
project sharing. Session cookies live on the API origin (HttpOnly, Lax);
localhost ports are same-site, so the browser sends them on fetch/SSE.
"""

import secrets
import threading
import time
from collections import deque
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse, Response
from klave_engine.common.config import Settings
from pydantic import BaseModel, EmailStr, Field

from apps.api.auth.middleware import SESSION_COOKIE
from apps.api.auth.store import (
    PROJECT_ROLES,
    UsersDbUnavailable,
    UserStore,
    get_user_store,
    verify_password,
)
from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import BUS

router = APIRouter(tags=["auth"])

# Sliding-window rate limit for credential endpoints: 10 attempts per 5
# minutes per client address. In-memory is right for the single-process
# workspace API; a shared limiter belongs to the hosted deployment.
_RATE_WINDOW_SECONDS = 300.0
_RATE_MAX_ATTEMPTS = 10
_rate_buckets: dict[str, deque[float]] = {}
_rate_lock = threading.Lock()


def _rate_limit(request: Request, bucket: str) -> None:
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

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
STATE_COOKIE = "klave_oauth_state"


def get_users(settings: Settings = Depends(get_settings)) -> UserStore:
    return get_user_store(settings.users_database_url)


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": str(user["user_id"]),
        "email": user["email"],
        "name": user["name"],
        "picture": user.get("picture"),
        "role": user["role"],
        "status": user["status"],
    }


def _session_user(
    request: Request, users: UserStore
) -> dict[str, Any] | None:
    return users.get_session_user(request.cookies.get(SESSION_COOKIE))


def _require_user(request: Request, users: UserStore) -> dict[str, Any]:
    user = _session_user(request, users)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"error_type": "auth_required", "message": "Inicia sesión."},
        )
    return user


def _require_admin(request: Request, users: UserStore) -> dict[str, Any]:
    user = _require_user(request, users)
    if user["role"] != "admin" or user["status"] != "active":
        raise HTTPException(
            status_code=403,
            detail={"error_type": "admin_required", "message": "Requiere administrador."},
        )
    return user


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.web_origin.startswith("https"),
        max_age=60 * 60 * 24 * 30,
        path="/",
    )


class RegisterInput(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class StatusInput(BaseModel):
    status: Literal["active", "disabled"]


class RoleInput(BaseModel):
    role: Literal["admin", "member"]


class AccessInput(BaseModel):
    email: EmailStr
    role: Literal["viewer", "editor", "owner"]


@router.get("/auth/session")
def auth_session(
    request: Request,
    users: UserStore = Depends(get_users),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Workspace auth state: mode, current user, and available methods."""
    google_enabled = bool(settings.auth_google_id and settings.auth_google_secret)
    try:
        protected = users.has_users()
        user = _session_user(request, users)
    except UsersDbUnavailable:
        return {
            "mode": "unavailable",
            "user": None,
            "google_enabled": google_enabled,
        }
    return {
        "mode": "protected" if protected else "open",
        "user": _public_user(user) if user else None,
        "google_enabled": google_enabled,
    }


@router.post("/auth/register", status_code=201)
def register(
    body: RegisterInput,
    request: Request,
    response: Response,
    users: UserStore = Depends(get_users),
    settings: Settings = Depends(get_settings),
) -> dict:
    _rate_limit(request, "register")
    try:
        if users.get_by_email(body.email):
            raise HTTPException(
                status_code=409,
                detail={"error_type": "email_taken", "message": "Ese correo ya tiene cuenta."},
            )
        user = users.create_user(email=body.email, name=body.name, password=body.password)
    except UsersDbUnavailable as exc:
        raise _db_unavailable() from exc
    if user["status"] == "active":
        _set_session_cookie(response, users.create_session(str(user["user_id"])), settings)
    else:
        BUS.publish(
            "user_pending", actor=user["name"], data={"email": user["email"]}
        )
    return _public_user(user)


@router.post("/auth/login")
def login(
    body: LoginInput,
    request: Request,
    response: Response,
    users: UserStore = Depends(get_users),
    settings: Settings = Depends(get_settings),
) -> dict:
    _rate_limit(request, "login")
    try:
        user = users.get_by_email(body.email)
        if user is None or not verify_password(body.password, user.get("password_hash")):
            raise HTTPException(
                status_code=401,
                detail={
                    "error_type": "invalid_credentials",
                    "message": "Correo o contraseña incorrectos.",
                },
            )
        if user["status"] == "disabled":
            raise HTTPException(
                status_code=403,
                detail={"error_type": "account_disabled", "message": "Cuenta deshabilitada."},
            )
        _set_session_cookie(response, users.create_session(str(user["user_id"])), settings)
    except UsersDbUnavailable as exc:
        raise _db_unavailable() from exc
    return _public_user(user)


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    users: UserStore = Depends(get_users),
) -> dict:
    try:
        users.delete_session(request.cookies.get(SESSION_COOKIE))
    except UsersDbUnavailable:
        pass
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


def _db_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error_type": "users_db_unavailable",
            "message": "La base de datos de usuarios no está disponible (make users-db-up).",
        },
    )


class PasswordInput(BaseModel):
    current_password: str = Field(default="", max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/auth/password")
def change_password(
    body: PasswordInput,
    request: Request,
    users: UserStore = Depends(get_users),
) -> dict:
    """Change (or set, for Google-only accounts) the session user's password.
    All other sessions are revoked afterwards."""
    _rate_limit(request, "password")
    try:
        user = _require_user(request, users)
        stored = users.get_by_email(user["email"]) or {}
        existing_hash = stored.get("password_hash")
        if existing_hash and not verify_password(body.current_password, existing_hash):
            raise HTTPException(
                status_code=401,
                detail={
                    "error_type": "invalid_credentials",
                    "message": "La contraseña actual no coincide.",
                },
            )
        users.set_password(str(user["user_id"]), body.new_password)
        users.delete_sessions_for_user(str(user["user_id"]))
    except UsersDbUnavailable as exc:
        raise _db_unavailable() from exc
    return {"ok": True, "sessions_revoked": True}


@router.post("/auth/logout-all")
def logout_all(
    request: Request,
    response: Response,
    users: UserStore = Depends(get_users),
) -> dict:
    try:
        user = _require_user(request, users)
        revoked = users.delete_sessions_for_user(str(user["user_id"]))
    except UsersDbUnavailable as exc:
        raise _db_unavailable() from exc
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True, "sessions_revoked": revoked}


# ------------------------------------------------------------------ google

@router.get("/auth/google")
def google_start(request: Request, settings: Settings = Depends(get_settings)) -> Response:
    if not (settings.auth_google_id and settings.auth_google_secret):
        raise HTTPException(status_code=404, detail={"error_type": "google_not_configured"})
    state = secrets.token_urlsafe(24)
    redirect_uri = str(request.base_url).rstrip("/") + "/auth/google/callback"
    from urllib.parse import urlencode

    url = GOOGLE_AUTH_URL + "?" + urlencode(
        {
            "client_id": settings.auth_google_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        }
    )
    response = RedirectResponse(url)
    response.set_cookie(
        STATE_COOKIE, state, httponly=True, samesite="lax", max_age=600, path="/auth"
    )
    return response


@router.get("/auth/google/callback")
async def google_callback(
    request: Request,
    users: UserStore = Depends(get_users),
    settings: Settings = Depends(get_settings),
) -> Response:
    def fail(reason: str) -> Response:
        return RedirectResponse(f"{settings.web_origin}/bienvenida?error={reason}")

    if not (settings.auth_google_id and settings.auth_google_secret):
        return fail("google")
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state or state != request.cookies.get(STATE_COOKIE):
        return fail("google")

    import httpx

    redirect_uri = str(request.base_url).rstrip("/") + "/auth/google/callback"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.auth_google_id,
                    "client_secret": settings.auth_google_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
    except httpx.HTTPError:
        return fail("google")
    if token_response.status_code != 200:
        return fail("google")
    id_token = token_response.json().get("id_token")
    if not id_token:
        return fail("google")

    import base64
    import json

    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, IndexError):
        return fail("google")
    sub = claims.get("sub")
    email = (claims.get("email") or "").lower()
    if not sub or not email:
        return fail("google")
    name = claims.get("name") or email.split("@")[0]
    picture = claims.get("picture")

    try:
        user = users.get_by_google_sub(sub)
        if user is None:
            user = users.get_by_email(email)
            if user is not None:
                users.link_google(str(user["user_id"]), sub, picture)
            else:
                user = users.create_user(
                    email=email, name=name, google_sub=sub, picture=picture
                )
                if user["status"] == "pending":
                    BUS.publish(
                        "user_pending", actor=user["name"], data={"email": user["email"]}
                    )
        if user["status"] == "disabled":
            return fail("disabled")
        response = RedirectResponse(
            settings.web_origin
            if user["status"] == "active"
            else f"{settings.web_origin}/bienvenida?pending=1"
        )
        if user["status"] == "active":
            _set_session_cookie(
                response, users.create_session(str(user["user_id"])), settings
            )
        response.delete_cookie(STATE_COOKIE, path="/auth")
        return response
    except UsersDbUnavailable:
        return fail("db")


# ------------------------------------------------- admin confirmation loop

@router.get("/auth/users")
def list_users(request: Request, users: UserStore = Depends(get_users)) -> dict:
    try:
        _require_admin(request, users)
        rows = users.list_users()
    except UsersDbUnavailable as exc:
        raise _db_unavailable() from exc
    return {
        "users": [
            {**_public_user(row), "created_at": row["created_at"].isoformat()}
            for row in rows
        ]
    }


@router.put("/auth/users/{user_id}/status")
def set_user_status(
    user_id: str,
    body: StatusInput,
    request: Request,
    users: UserStore = Depends(get_users),
) -> dict:
    try:
        admin = _require_admin(request, users)
        if str(admin["user_id"]) == user_id and body.status == "disabled":
            raise HTTPException(
                status_code=422,
                detail={
                    "error_type": "cannot_disable_self",
                    "message": "No puedes deshabilitar tu propia cuenta.",
                },
            )
        if not users.set_status(user_id, body.status, str(admin["user_id"])):
            raise HTTPException(status_code=404, detail={"error_type": "user_not_found"})
    except UsersDbUnavailable as exc:
        raise _db_unavailable() from exc
    BUS.publish(
        "user_status_changed",
        actor=admin["name"],
        data={"user_id": user_id, "status": body.status},
    )
    return {"user_id": user_id, "status": body.status}


@router.put("/auth/users/{user_id}/role")
def set_user_role(
    user_id: str,
    body: RoleInput,
    request: Request,
    users: UserStore = Depends(get_users),
) -> dict:
    try:
        admin = _require_admin(request, users)
        if str(admin["user_id"]) == user_id and body.role == "member":
            raise HTTPException(
                status_code=422,
                detail={
                    "error_type": "cannot_demote_self",
                    "message": "No puedes quitarte el rol de administrador.",
                },
            )
        if not users.set_role(user_id, body.role):
            raise HTTPException(status_code=404, detail={"error_type": "user_not_found"})
    except UsersDbUnavailable as exc:
        raise _db_unavailable() from exc
    return {"user_id": user_id, "role": body.role}


# --------------------------------------------------------- project sharing

def _require_project_admin(
    request: Request, users: UserStore, project_id: str
) -> dict[str, Any]:
    user = _require_user(request, users)
    if user["role"] == "admin":
        return user
    if users.project_role(project_id, str(user["user_id"])) != "owner":
        raise HTTPException(
            status_code=403,
            detail={
                "error_type": "forbidden_project",
                "message": "Solo el propietario o un administrador comparte el proyecto.",
            },
        )
    return user


@router.get("/projects/{project_id}/access")
def project_access(
    project_id: str,
    request: Request,
    users: UserStore = Depends(get_users),
    store: ProjectStore = Depends(get_store),
) -> dict:
    store.get_root(project_id)
    try:
        _require_project_admin(request, users, project_id)
        members = users.project_members(project_id)
        workspace = users.list_users()
    except UsersDbUnavailable as exc:
        raise _db_unavailable() from exc
    member_ids = {str(m["user_id"]) for m in members}
    return {
        "members": [
            {
                "user_id": str(m["user_id"]),
                "email": m["email"],
                "name": m["name"],
                "picture": m.get("picture"),
                "status": m["status"],
                "project_role": m["project_role"],
            }
            for m in members
        ],
        "invitable": [
            _public_user(u)
            for u in workspace
            if str(u["user_id"]) not in member_ids and u["status"] == "active"
        ],
    }


@router.post("/projects/{project_id}/access", status_code=201)
def grant_project_access(
    project_id: str,
    body: AccessInput,
    request: Request,
    users: UserStore = Depends(get_users),
    store: ProjectStore = Depends(get_store),
) -> dict:
    store.get_root(project_id)
    try:
        granter = _require_project_admin(request, users, project_id)
        target = users.get_by_email(body.email)
        if target is None or target["status"] != "active":
            raise HTTPException(
                status_code=404,
                detail={
                    "error_type": "user_not_found",
                    "message": "No hay una cuenta activa con ese correo.",
                },
            )
        users.grant_access(
            project_id, str(target["user_id"]), body.role, str(granter["user_id"])
        )
    except UsersDbUnavailable as exc:
        raise _db_unavailable() from exc
    BUS.publish(
        "project_shared",
        project_id=project_id,
        actor=granter["name"],
        data={"email": target["email"], "role": body.role},
    )
    return {"project_id": project_id, "email": target["email"], "role": body.role}


@router.delete("/projects/{project_id}/access/{user_id}")
def revoke_project_access(
    project_id: str,
    user_id: str,
    request: Request,
    users: UserStore = Depends(get_users),
    store: ProjectStore = Depends(get_store),
) -> dict:
    store.get_root(project_id)
    try:
        _require_project_admin(request, users, project_id)
        if not users.revoke_access(project_id, user_id):
            raise HTTPException(status_code=404, detail={"error_type": "access_not_found"})
    except UsersDbUnavailable as exc:
        raise _db_unavailable() from exc
    return {"project_id": project_id, "user_id": user_id, "revoked": True}


# PROJECT_ROLES is re-exported for the routes that grant the uploader owner.
__all__ = ["router", "PROJECT_ROLES"]
