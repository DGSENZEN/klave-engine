"""Invitations: the way a taller actually onboards people.

An admin invites an address with a role and optional project grants. The
link (mailed when a provider exists, always returned to the admin so it can
be handed over by other means) lands on /invitacion, where the invitee sets
a name and password — or continues with Google on the same address — and
comes out active and verified. Open invitations can be resent or revoked.
"""

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import HTTPException
from klave_engine.common.config import Settings
from pydantic import BaseModel, EmailStr, Field

from apps.api.auth.common import (
    audit,
    db_unavailable,
    public_user,
    rate_limit,
    require_admin,
    start_session,
    users_dependency,
    web_link,
)
from apps.api.auth.store import UsersDbUnavailable, UserStore
from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.events import BUS
from apps.api.mail import Mailer, get_mailer, render

router = APIRouter(prefix="/auth/invitations", tags=["auth"])


class ProjectGrant(BaseModel):
    project_id: str = Field(min_length=1, max_length=120)
    role: Literal["viewer", "editor", "owner"]


class InviteInput(BaseModel):
    email: EmailStr
    role: Literal["admin", "member"] = "member"
    project_grants: list[ProjectGrant] = Field(default_factory=list, max_length=50)


class AcceptInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)


def _invite_link(settings: Settings, token: str) -> str:
    return web_link(settings, f"/invitacion?token={token}")


def _serialize(invite: dict[str, Any]) -> dict[str, Any]:
    return {
        "invite_id": str(invite["invite_id"]),
        "email": invite["email"],
        "role": invite["role"],
        "project_grants": invite.get("project_grants") or [],
        "state": invite["state"],
        "inviter_name": invite.get("inviter_name"),
        "created_at": invite["created_at"].isoformat(),
        "expires_at": invite["expires_at"].isoformat(),
        "accepted_at": invite["accepted_at"].isoformat() if invite.get("accepted_at") else None,
    }


def _send_invitation(
    mailer: Mailer, settings: Settings, invite: dict[str, Any], token: str,
    workspace_name: str, inviter_name: str,
) -> bool:
    grants = invite.get("project_grants") or []
    lines = [
        f"{inviter_name} te invitó al taller {workspace_name} en Klave.",
        "Crea tu cuenta desde este enlace; vale siete días.",
    ]
    if grants:
        lines.append(
            f"Al entrar tendrás acceso a {len(grants)} proyecto(s) ya compartido(s) contigo."
        )
    result = mailer.send(
        invite["email"],
        render(
            subject=f"Invitación al taller {workspace_name}",
            greeting="Hola.",
            lines=lines,
            action_label="Aceptar invitación",
            action_url=_invite_link(settings, token),
        ),
    )
    return result.delivered


@router.post("", status_code=201)
def create_invitation(
    body: InviteInput,
    request: Request,
    users: UserStore = Depends(users_dependency),
    settings: Settings = Depends(get_settings),
    store: ProjectStore = Depends(get_store),
) -> dict:
    mailer = get_mailer(settings)
    try:
        admin = require_admin(request, users)
        workspace_id = str(admin["workspace_id"])
        if users.get_by_email(body.email):
            raise HTTPException(
                status_code=409,
                detail={
                    "error_type": "email_taken",
                    "message": "Ese correo ya tiene cuenta; compártele el proyecto directamente.",
                },
            )
        grants: list[dict[str, str]] = []
        for grant in body.project_grants:
            store.get_root(grant.project_id)  # 404 for unknown projects
            if users.project_workspace_id(grant.project_id) != workspace_id:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error_type": "forbidden_project",
                        "message": "Proyecto de otro taller.",
                    },
                )
            grants.append({"project_id": grant.project_id, "role": grant.role})
        invite, token = users.create_invitation(
            workspace_id=workspace_id, email=body.email, role=body.role,
            project_grants=grants, invited_by=str(admin["user_id"]),
        )
        workspace = users.get_workspace(workspace_id) or {"name": settings.workspace_name}
        delivered = _send_invitation(
            mailer, settings, invite, token, workspace["name"], admin["name"]
        )
        audit(
            users, admin, "invitation_created", target_type="invitation",
            target_id=str(invite["invite_id"]),
            detail={"email": invite["email"], "role": body.role, "projects": len(grants)},
        )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    invite["state"] = "open"
    return {
        **_serialize(invite),
        "link": _invite_link(settings, token),
        "delivered": delivered,
        "mail_enabled": mailer.enabled,
    }


@router.get("")
def list_invitations(request: Request, users: UserStore = Depends(users_dependency)) -> dict:
    try:
        admin = require_admin(request, users)
        rows = users.list_invitations(str(admin["workspace_id"]))
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {"invitations": [_serialize(row) for row in rows]}


@router.delete("/{invite_id}")
def revoke_invitation(
    invite_id: str, request: Request, users: UserStore = Depends(users_dependency)
) -> dict:
    try:
        admin = require_admin(request, users)
        invite = users.get_invitation(invite_id, str(admin["workspace_id"]))
        if invite is None or not users.revoke_invitation(invite_id, str(admin["workspace_id"])):
            raise HTTPException(status_code=404, detail={"error_type": "invitation_not_found"})
        audit(
            users, admin, "invitation_revoked", target_type="invitation", target_id=invite_id,
            detail={"email": invite["email"]},
        )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {"invite_id": invite_id, "revoked": True}


@router.post("/{invite_id}/resend")
def resend_invitation(
    invite_id: str,
    request: Request,
    users: UserStore = Depends(users_dependency),
    settings: Settings = Depends(get_settings),
) -> dict:
    mailer = get_mailer(settings)
    try:
        admin = require_admin(request, users)
        workspace_id = str(admin["workspace_id"])
        invite = users.get_invitation(invite_id, workspace_id)
        if invite is None or invite["state"] in ("accepted", "revoked"):
            raise HTTPException(status_code=404, detail={"error_type": "invitation_not_found"})
        token = users.refresh_invitation(invite_id, workspace_id)
        if token is None:
            raise HTTPException(status_code=404, detail={"error_type": "invitation_not_found"})
        workspace = users.get_workspace(workspace_id) or {"name": settings.workspace_name}
        delivered = _send_invitation(
            mailer, settings, invite, token, workspace["name"], admin["name"]
        )
        audit(
            users, admin, "invitation_resent", target_type="invitation", target_id=invite_id,
            detail={"email": invite["email"]},
        )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {
        "invite_id": invite_id,
        "link": _invite_link(settings, token),
        "delivered": delivered,
        "mail_enabled": mailer.enabled,
    }


# -------------------------------------------------------------- public

@router.get("/by-token/{token}")
def invitation_info(
    token: str,
    users: UserStore = Depends(users_dependency),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        invite = users.get_invitation_by_token(token)
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    if invite is None:
        raise HTTPException(status_code=404, detail={"error_type": "invitation_not_found"})
    return {
        "state": invite["state"],
        "email": invite["email"],
        "role": invite["role"],
        "workspace_name": invite["workspace_name"],
        "inviter_name": invite.get("inviter_name"),
        "project_count": len(invite.get("project_grants") or []),
        "expires_at": invite["expires_at"].isoformat(),
        "google_enabled": bool(settings.auth_google_id and settings.auth_google_secret),
    }


@router.post("/by-token/{token}/accept", status_code=201)
def accept_invitation(
    token: str,
    body: AcceptInput,
    request: Request,
    response: Response,
    users: UserStore = Depends(users_dependency),
    settings: Settings = Depends(get_settings),
) -> dict:
    rate_limit(request, "invite_accept")
    try:
        invite = users.get_invitation_by_token(token)
        if invite is None or invite["state"] != "open":
            raise HTTPException(
                status_code=410,
                detail={
                    "error_type": "invitation_closed",
                    "message": "La invitación ya no está abierta; pide una nueva.",
                },
            )
        if users.get_by_email(invite["email"]):
            raise HTTPException(
                status_code=409,
                detail={"error_type": "email_taken", "message": "Ese correo ya tiene cuenta."},
            )
        user = users.accept_invitation(invite, name=body.name, password=body.password)
        start_session(request, response, users, settings, str(user["user_id"]))
        audit(
            users, user, "invitation_accepted", target_type="invitation",
            target_id=str(invite["invite_id"]), detail={"email": user["email"], "via": "password"},
        )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    BUS.publish("user_joined", actor=user["name"], data={"email": user["email"]})
    return public_user(user)
