"""Sessions, registration, Google sign-in, the admin confirmation loop, and
project sharing. Session cookies live on the API origin (HttpOnly, Lax);
localhost ports are same-site, so the browser sends them on fetch/SSE.

Invitations, recovery, and the account page live in sibling routers.
"""

import base64
import json
import secrets
from typing import Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse, Response
from klave_engine.common.config import Settings
from klave_engine.common.ids import slugify
from pydantic import BaseModel, EmailStr, Field

from apps.api.auth.common import (
    audit,
    db_unavailable,
    public_user,
    rate_limit,
    require_admin,
    require_user,
    session_user,
    start_session,
    users_dependency,
    web_link,
)
from apps.api.auth.passwords import password_problem
from apps.api.auth.recovery import send_verification
from apps.api.auth.store import (
    PROJECT_ROLES,
    UsersDbUnavailable,
    UserStore,
    verify_password,
)
from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import BUS
from apps.api.mail import get_mailer

router = APIRouter(tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


def google_claims_problem(claims: dict[str, Any], client_id: str | None) -> str | None:
    """Why an id_token must not sign anyone in, or None when it may: the
    token must be issued by Google for this app, still valid, and carry an
    email Google has verified."""
    import time

    if claims.get("iss") not in GOOGLE_ISSUERS:
        return "google"
    aud = claims.get("aud")
    audiences = aud if isinstance(aud, list) else [aud]
    if not client_id or client_id not in audiences:
        return "google"
    try:
        if float(claims.get("exp") or 0) < time.time():
            return "google"
    except (TypeError, ValueError):
        return "google"
    if not claims.get("sub") or not claims.get("email"):
        return "google"
    if claims.get("email_verified") is not True:
        return "google_unverified"
    return None
STATE_COOKIE = "klave_oauth_state"
INVITE_COOKIE = "klave_oauth_invite"


class RegisterInput(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    # Founding a new taller: this account becomes its first (admin) member,
    # active immediately. Absent, the account asks to join the default taller
    # and waits for an admin's approval.
    workspace_name: str | None = Field(default=None, min_length=2, max_length=80)


class LoginInput(BaseModel):
    email: EmailStr
    password: str
    remember: bool = False


class StatusInput(BaseModel):
    status: Literal["active", "disabled"]


class RoleInput(BaseModel):
    role: Literal["admin", "member"]


class AccessInput(BaseModel):
    email: EmailStr
    role: Literal["viewer", "editor", "owner"]


def _workspace_payload(users: UserStore, user: dict[str, Any] | None) -> dict[str, Any] | None:
    workspace = (
        users.get_workspace(str(user["workspace_id"]))
        if user and user.get("workspace_id")
        else users.default_workspace()
    )
    if workspace is None:
        return None
    return {"slug": workspace["slug"], "name": workspace["name"]}


@router.get("/auth/session")
def auth_session(
    request: Request,
    users: UserStore = Depends(users_dependency),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Deployment auth state: mode, current user, workspace, and methods."""
    google_enabled = bool(settings.auth_google_id and settings.auth_google_secret)
    mail_enabled = get_mailer(settings).enabled
    try:
        protected = users.has_users()
        user = session_user(request, users)
        workspace = _workspace_payload(users, user)
    except UsersDbUnavailable:
        return {
            "mode": "unavailable",
            "user": None,
            "workspace": None,
            "google_enabled": google_enabled,
            "mail_enabled": mail_enabled,
            "registration": settings.registration,
        }
    return {
        "mode": "protected" if protected else "open",
        "user": public_user(user) if user else None,
        "workspace": workspace,
        "google_enabled": google_enabled,
        "mail_enabled": mail_enabled,
        "registration": settings.registration,
    }


@router.post("/auth/register", status_code=201)
def register(
    body: RegisterInput,
    request: Request,
    response: Response,
    users: UserStore = Depends(users_dependency),
    settings: Settings = Depends(get_settings),
) -> dict:
    rate_limit(request, "register")
    if settings.registration == "invite_only":
        raise HTTPException(
            status_code=403,
            detail={
                "error_type": "registration_closed",
                "message": "Este servidor es solo por invitación; pide una a un "
                "administrador del taller.",
            },
        )
    problem = password_problem(body.password, body.email)
    if problem:
        raise HTTPException(
            status_code=422, detail={"error_type": "weak_password", "message": problem}
        )
    try:
        if users.get_by_email(body.email):
            raise HTTPException(
                status_code=409,
                detail={"error_type": "email_taken", "message": "Ese correo ya tiene cuenta."},
            )
        workspace_id: str | None = None
        if body.workspace_name:
            base = slugify(body.workspace_name)[:40] or "taller"
            slug = base
            for _ in range(4):
                try:
                    workspace = users.create_workspace(slug, body.workspace_name.strip())
                    workspace_id = str(workspace["workspace_id"])
                    break
                except ValueError:
                    slug = f"{base}-{secrets.token_hex(2)}"
            if workspace_id is None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error_type": "workspace_slug_taken",
                        "message": "No se pudo crear el taller; intenta con otro nombre.",
                    },
                )
        user = users.create_user(
            email=body.email, name=body.name, password=body.password,
            workspace_id=workspace_id,
        )
        if user["status"] == "active":
            start_session(request, response, users, settings, str(user["user_id"]))
        else:
            BUS.publish(
                "user_pending", data={"user_id": str(user["user_id"])},
                workspace_id=str(user["workspace_id"]),
            )
        send_verification(users, settings, user)
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return public_user(user)


@router.post("/auth/login")
def login(
    body: LoginInput,
    request: Request,
    response: Response,
    users: UserStore = Depends(users_dependency),
    settings: Settings = Depends(get_settings),
) -> dict:
    rate_limit(request, "login")
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
        start_session(
            request, response, users, settings, str(user["user_id"]), remember=body.remember
        )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return public_user(user)


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    users: UserStore = Depends(users_dependency),
) -> dict:
    from apps.api.auth.middleware import SESSION_COOKIE

    try:
        users.delete_session(request.cookies.get(SESSION_COOKIE))
    except UsersDbUnavailable:
        pass
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


# ------------------------------------------------------------------ google

@router.get("/auth/google")
def google_start(
    request: Request,
    invite: str | None = None,
    settings: Settings = Depends(get_settings),
) -> Response:
    if not (settings.auth_google_id and settings.auth_google_secret):
        raise HTTPException(status_code=404, detail={"error_type": "google_not_configured"})
    state = secrets.token_urlsafe(24)
    redirect_uri = str(request.base_url).rstrip("/") + "/auth/google/callback"
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
    if invite:
        # Accepting an invitation with Google: the token rides a short-lived
        # cookie and is honored only when the Google email matches it.
        response.set_cookie(
            INVITE_COOKIE, invite, httponly=True, samesite="lax", max_age=600, path="/auth"
        )
    return response


@router.get("/auth/google/callback")
async def google_callback(
    request: Request,
    users: UserStore = Depends(users_dependency),
    settings: Settings = Depends(get_settings),
) -> Response:
    def fail(reason: str) -> Response:
        response = RedirectResponse(web_link(settings, f"/bienvenida?error={reason}"))
        response.delete_cookie(STATE_COOKIE, path="/auth")
        response.delete_cookie(INVITE_COOKIE, path="/auth")
        return response

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
    # The id_token arrives straight from Google's token endpoint over TLS, so
    # its signature is not re-checked; its claims still must be ours (iss,
    # aud, exp) and the email must be one Google itself verified.
    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, IndexError):
        return fail("google")
    problem = google_claims_problem(claims, settings.auth_google_id)
    if problem is not None:
        return fail(problem)
    sub = claims["sub"]
    email = claims["email"].lower()
    name = claims.get("name") or email.split("@")[0]
    picture = claims.get("picture")
    invite_token = request.cookies.get(INVITE_COOKIE)

    try:
        user = users.get_by_google_sub(sub)
        if user is None:
            # Linking Google to an account that already exists needs proof of
            # that account: a live session (the user came from Tu cuenta).
            # An unauthenticated sign-in with a matching email is not proof.
            signed_in = session_user(request, users)
            existing = users.get_by_email(email)
            if signed_in is not None:
                users.link_google(str(signed_in["user_id"]), sub, picture)
                audit(
                    users, signed_in, "google_linked",
                    target_type="user", target_id=str(signed_in["user_id"]),
                    detail={"email": email},
                )
                user = users.get_by_google_sub(sub) or signed_in
            elif existing is not None:
                return fail("google_link_required")
            elif settings.registration == "invite_only" and not invite_token:
                return fail("invite")
            elif invite_token:
                invite = users.get_invitation_by_token(invite_token)
                if invite is None or invite["state"] != "open":
                    return fail("invite")
                if invite["email"] != email:
                    return fail("invite_email")
                user = users.accept_invitation(
                    invite, name=name, google_sub=sub, picture=picture
                )
                audit(
                    users, user, "invitation_accepted",
                    target_type="invitation", target_id=str(invite["invite_id"]),
                    detail={"email": email, "via": "google"},
                )
            else:
                user = users.create_user(
                    email=email, name=name, google_sub=sub, picture=picture,
                    email_verified=True,
                )
                if user["status"] == "pending":
                    BUS.publish(
                        "user_pending", data={"user_id": str(user["user_id"])},
                        workspace_id=str(user["workspace_id"]),
                    )
        if user["status"] == "disabled":
            return fail("disabled")
        response = RedirectResponse(
            web_link(settings, "/")
            if user["status"] == "active"
            else web_link(settings, "/bienvenida?pending=1")
        )
        if user["status"] == "active":
            start_session(request, response, users, settings, str(user["user_id"]))
        response.delete_cookie(STATE_COOKIE, path="/auth")
        response.delete_cookie(INVITE_COOKIE, path="/auth")
        return response
    except UsersDbUnavailable:
        return fail("db")


# ------------------------------------------------- admin confirmation loop

@router.get("/auth/users")
def list_users(request: Request, users: UserStore = Depends(users_dependency)) -> dict:
    try:
        admin = require_admin(request, users)
        rows = users.list_users(str(admin["workspace_id"]))
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {
        "users": [
            {
                **public_user(row),
                "created_at": row["created_at"].isoformat(),
                "approved_at": row["approved_at"].isoformat() if row.get("approved_at") else None,
            }
            for row in rows
        ]
    }


def _admin_target(users: UserStore, admin: dict[str, Any], user_id: str) -> dict[str, Any]:
    target = users.get_by_id(user_id)
    if target is None or str(target["workspace_id"]) != str(admin["workspace_id"]):
        raise HTTPException(status_code=404, detail={"error_type": "user_not_found"})
    return target


@router.put("/auth/users/{user_id}/status")
def set_user_status(
    user_id: str,
    body: StatusInput,
    request: Request,
    users: UserStore = Depends(users_dependency),
) -> dict:
    try:
        admin = require_admin(request, users)
        target = _admin_target(users, admin, user_id)
        if str(admin["user_id"]) == user_id and body.status == "disabled":
            raise HTTPException(
                status_code=422,
                detail={
                    "error_type": "cannot_disable_self",
                    "message": "No puedes deshabilitar tu propia cuenta.",
                },
            )
        if body.status == "disabled" and users.is_last_active_admin(target):
            raise HTTPException(
                status_code=422,
                detail={
                    "error_type": "last_admin",
                    "message": "Es el último administrador activo del taller.",
                },
            )
        users.set_status(user_id, body.status, str(admin["user_id"]))
        audit(
            users, admin, "user_status_changed", target_type="user", target_id=user_id,
            detail={"email": target["email"], "from": target["status"], "to": body.status},
        )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    BUS.publish(
        "user_status_changed",
        actor=admin["name"],
        data={"user_id": user_id, "status": body.status},
        workspace_id=str(admin["workspace_id"]),
    )
    return {"user_id": user_id, "status": body.status}


@router.put("/auth/users/{user_id}/role")
def set_user_role(
    user_id: str,
    body: RoleInput,
    request: Request,
    users: UserStore = Depends(users_dependency),
) -> dict:
    try:
        admin = require_admin(request, users)
        target = _admin_target(users, admin, user_id)
        if str(admin["user_id"]) == user_id and body.role == "member":
            raise HTTPException(
                status_code=422,
                detail={
                    "error_type": "cannot_demote_self",
                    "message": "No puedes quitarte el rol de administrador.",
                },
            )
        if body.role == "member" and users.is_last_active_admin(target):
            raise HTTPException(
                status_code=422,
                detail={
                    "error_type": "last_admin",
                    "message": "Es el último administrador activo del taller.",
                },
            )
        users.set_role(user_id, body.role)
        audit(
            users, admin, "user_role_changed", target_type="user", target_id=user_id,
            detail={"email": target["email"], "from": target["role"], "to": body.role},
        )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {"user_id": user_id, "role": body.role}


# --------------------------------------------------------- project sharing

def _require_project_admin(
    request: Request, users: UserStore, project_id: str
) -> dict[str, Any]:
    user = require_user(request, users)
    if user["role"] == "admin":
        if users.project_workspace_id(project_id) != str(user["workspace_id"]):
            raise HTTPException(
                status_code=403,
                detail={"error_type": "forbidden_project", "message": "Proyecto de otro taller."},
            )
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
    users: UserStore = Depends(users_dependency),
    store: ProjectStore = Depends(get_store),
) -> dict:
    store.get_root(project_id)
    try:
        actor = _require_project_admin(request, users, project_id)
        members = users.project_members(project_id)
        workspace = users.list_users(str(actor["workspace_id"]))
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
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
            public_user(u)
            for u in workspace
            if str(u["user_id"]) not in member_ids and u["status"] == "active"
        ],
    }


@router.post("/projects/{project_id}/access", status_code=201)
def grant_project_access(
    project_id: str,
    body: AccessInput,
    request: Request,
    users: UserStore = Depends(users_dependency),
    store: ProjectStore = Depends(get_store),
) -> dict:
    store.get_root(project_id)
    try:
        granter = _require_project_admin(request, users, project_id)
        target = users.get_by_email(body.email)
        if (
            target is None
            or target["status"] != "active"
            or str(target["workspace_id"]) != str(granter["workspace_id"])
        ):
            raise HTTPException(
                status_code=404,
                detail={
                    "error_type": "user_not_found",
                    "message": "No hay una cuenta activa con ese correo en este taller.",
                },
            )
        users.grant_access(
            project_id, str(target["user_id"]), body.role, str(granter["user_id"])
        )
        audit(
            users, granter, "project_access_granted", target_type="project",
            target_id=project_id, detail={"email": target["email"], "role": body.role},
        )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    BUS.publish(
        "project_shared",
        project_id=project_id,
        actor=granter["name"],
        data={"name": target["name"], "role": body.role},
    )
    return {"project_id": project_id, "email": target["email"], "role": body.role}


@router.delete("/projects/{project_id}/access/{user_id}")
def revoke_project_access(
    project_id: str,
    user_id: str,
    request: Request,
    users: UserStore = Depends(users_dependency),
    store: ProjectStore = Depends(get_store),
) -> dict:
    store.get_root(project_id)
    try:
        actor = _require_project_admin(request, users, project_id)
        if not users.revoke_access(project_id, user_id):
            raise HTTPException(status_code=404, detail={"error_type": "access_not_found"})
        audit(
            users, actor, "project_access_revoked", target_type="project",
            target_id=project_id, detail={"user_id": user_id},
        )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {"project_id": project_id, "user_id": user_id, "revoked": True}


# PROJECT_ROLES is re-exported for the routes that grant the uploader owner.
__all__ = ["router", "PROJECT_ROLES"]
