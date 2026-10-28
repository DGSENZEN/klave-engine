"""Sessions, registration, the admin confirmation loop, and
project sharing. Session cookies live on the API origin (HttpOnly, Lax);
localhost ports are same-site, so the browser sends them on fetch/SSE.

Invitations, recovery, and the account page live in sibling routers.
"""

import secrets
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import Response
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
            "mail_enabled": mail_enabled,
            "registration": settings.registration,
        }
    return {
        "mode": "protected" if protected else "open",
        "user": public_user(user) if user else None,
        "workspace": workspace,
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
    # Sólo por invitación, salvo la primera cuenta del servidor: alguien tiene
    # que fundar el taller, y sin esto un despliegue nuevo no tenía entrada.
    if settings.registration == "invite_only" and users.has_users():
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
