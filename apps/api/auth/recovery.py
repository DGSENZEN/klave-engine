"""Password recovery and email verification.

Two honest paths to a new password: the emailed reset link (when a mail
provider is configured) and the admin-issued recovery link (always
available, audited, handed over out of band). Verification never blocks
sign-in — an unconfigured mailer must not lock a taller out.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import HTTPException
from klave_engine.common.config import Settings
from pydantic import BaseModel, EmailStr, Field

from apps.api.auth.common import (
    audit,
    db_unavailable,
    mask_email,
    rate_limit,
    require_admin,
    require_user,
    session_token,
    start_session,
    users_dependency,
    web_link,
)
from apps.api.auth.passwords import password_problem
from apps.api.auth.store import (
    ADMIN_RECOVERY_TTL,
    RESET_TTL,
    VERIFY_TTL,
    UsersDbUnavailable,
    UserStore,
    verify_password,
)
from apps.api.dependencies import get_settings
from apps.api.mail import get_mailer, render

router = APIRouter(tags=["auth"])


class RecoverInput(BaseModel):
    email: EmailStr


class ResetInput(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class EmailChangeInput(BaseModel):
    new_email: EmailStr
    current_password: str = Field(default="", max_length=128)


def send_verification(users: UserStore, settings: Settings, user: dict[str, Any]) -> dict:
    """Verification mail for the account's current address (idempotent)."""
    mailer = get_mailer(settings)
    if user.get("email_verified_at"):
        return {"delivered": False, "mail_enabled": mailer.enabled, "already_verified": True}
    token = users.issue_token(str(user["user_id"]), "verify", VERIFY_TTL)
    link = web_link(settings, f"/verificar?token={token}")
    result = mailer.send(
        user["email"],
        render(
            subject="Confirma tu correo en Klave",
            greeting=f"Hola, {user['name']}.",
            lines=["Confirma que este correo es tuyo para completar tu cuenta."],
            action_label="Confirmar correo",
            action_url=link,
        ),
    )
    return {"delivered": result.delivered, "mail_enabled": mailer.enabled}


@router.post("/auth/recover")
def recover(
    body: RecoverInput,
    request: Request,
    users: UserStore = Depends(users_dependency),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Always answers the same way, so addresses cannot be enumerated."""
    rate_limit(request, "recover")
    mailer = get_mailer(settings)
    try:
        user = users.get_by_email(body.email)
        if user is not None and user["status"] != "disabled" and mailer.enabled:
            token = users.issue_token(str(user["user_id"]), "reset", RESET_TTL)
            link = web_link(settings, f"/restablecer?token={token}")
            mailer.send(
                user["email"],
                render(
                    subject="Restablece tu contraseña de Klave",
                    greeting=f"Hola, {user['name']}.",
                    lines=[
                        "Recibimos una solicitud para restablecer tu contraseña.",
                        "El enlace vale una hora y se usa una sola vez.",
                    ],
                    action_label="Elegir nueva contraseña",
                    action_url=link,
                    footer="Si no lo pediste, ignora este correo; tu contraseña sigue igual.",
                ),
            )
            audit(
                users, None, "password_reset_requested",
                workspace_id=str(user["workspace_id"]), target_type="user",
                target_id=str(user["user_id"]), detail={"email": user["email"]},
            )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {"ok": True, "mail_enabled": mailer.enabled}


@router.get("/auth/reset/{token}")
def reset_info(token: str, users: UserStore = Depends(users_dependency)) -> dict:
    try:
        row = users.peek_token(token, "reset")
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    if row is None:
        return {"valid": False}
    return {"valid": True, "email": mask_email(row["email"]), "name": row["name"]}


@router.post("/auth/reset/{token}")
def reset_password(
    token: str,
    body: ResetInput,
    request: Request,
    response: Response,
    users: UserStore = Depends(users_dependency),
    settings: Settings = Depends(get_settings),
) -> dict:
    rate_limit(request, "reset")
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(
            status_code=422, detail={"error_type": "weak_password", "message": problem}
        )
    try:
        row = users.consume_token(token, "reset")
        if row is None:
            raise HTTPException(
                status_code=410,
                detail={
                    "error_type": "token_invalid",
                    "message": "El enlace ya no es válido; pide uno nuevo.",
                },
            )
        user_id = str(row["user_id"])
        users.set_password(user_id, body.password)
        users.mark_email_verified(user_id)  # reaching the inbox proves the address
        users.delete_sessions_for_user(user_id)
        user = users.get_by_id(user_id)
        assert user is not None
        if user["status"] == "disabled":
            raise HTTPException(
                status_code=403,
                detail={"error_type": "account_disabled", "message": "Cuenta deshabilitada."},
            )
        if user["status"] == "active":
            start_session(request, response, users, settings, user_id)
        audit(
            users, user, "password_reset", target_type="user", target_id=user_id,
            detail={"email": user["email"]},
        )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {"ok": True, "status": user["status"]}


@router.post("/auth/users/{user_id}/recovery-link")
def admin_recovery_link(
    user_id: str,
    request: Request,
    users: UserStore = Depends(users_dependency),
    settings: Settings = Depends(get_settings),
) -> dict:
    """The no-email path: an admin generates a one-time link and hands it
    over personally. Valid 24 h, audited, voids previous reset links."""
    try:
        admin = require_admin(request, users)
        target = users.get_by_id(user_id)
        if target is None or str(target["workspace_id"]) != str(admin["workspace_id"]):
            raise HTTPException(status_code=404, detail={"error_type": "user_not_found"})
        token = users.issue_token(user_id, "reset", ADMIN_RECOVERY_TTL)
        audit(
            users, admin, "recovery_link_issued", target_type="user", target_id=user_id,
            detail={"email": target["email"]},
        )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {
        "link": web_link(settings, f"/restablecer?token={token}"),
        "expires_in_hours": int(ADMIN_RECOVERY_TTL.total_seconds() // 3600),
        "email": target["email"],
    }


# ------------------------------------------------------------ verification

@router.post("/auth/verify/send")
def verify_send(
    request: Request,
    users: UserStore = Depends(users_dependency),
    settings: Settings = Depends(get_settings),
) -> dict:
    rate_limit(request, "verify")
    try:
        user = require_user(request, users)
        return send_verification(users, settings, user)
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc


@router.post("/auth/verify/{token}")
def verify_confirm(token: str, users: UserStore = Depends(users_dependency)) -> dict:
    try:
        row = users.consume_token(token, "verify")
        if row is None:
            raise HTTPException(
                status_code=410,
                detail={
                    "error_type": "token_invalid",
                    "message": "El enlace de confirmación ya no es válido.",
                },
            )
        user_id = str(row["user_id"])
        new_email = row.get("payload")
        if new_email:
            if not users.apply_pending_email(user_id, new_email):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error_type": "email_taken",
                        "message": "Ese correo ya pertenece a otra cuenta.",
                    },
                )
            user = users.get_by_id(user_id)
            audit(
                users, user, "email_changed", target_type="user", target_id=user_id,
                detail={"from": row["email"], "to": new_email},
            )
            return {"ok": True, "email": new_email, "changed": True}
        users.mark_email_verified(user_id)
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {"ok": True, "email": row["email"], "changed": False}


@router.post("/auth/email")
def change_email(
    body: EmailChangeInput,
    request: Request,
    users: UserStore = Depends(users_dependency),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Start an email change: the new address gets the confirmation link, so
    ownership is proven before anything switches."""
    rate_limit(request, "email")
    mailer = get_mailer(settings)
    if not mailer.enabled:
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": "mail_not_configured",
                "message": "Cambiar el correo requiere envío de correos configurado.",
            },
        )
    try:
        user = require_user(request, users)
        if user.get("password_hash") and not verify_password(
            body.current_password, user["password_hash"]
        ):
            raise HTTPException(
                status_code=401,
                detail={
                    "error_type": "invalid_credentials",
                    "message": "La contraseña actual no coincide.",
                },
            )
        new_email = body.new_email.lower()
        if new_email == user["email"]:
            raise HTTPException(
                status_code=422,
                detail={"error_type": "same_email", "message": "Es el mismo correo."},
            )
        if users.get_by_email(new_email):
            raise HTTPException(
                status_code=409,
                detail={"error_type": "email_taken", "message": "Ese correo ya tiene cuenta."},
            )
        users.set_pending_email(str(user["user_id"]), new_email)
        token = users.issue_token(str(user["user_id"]), "verify", VERIFY_TTL, payload=new_email)
        result = mailer.send(
            new_email,
            render(
                subject="Confirma tu nuevo correo en Klave",
                greeting=f"Hola, {user['name']}.",
                lines=[
                    f"Pediste cambiar el correo de tu cuenta de {user['email']} a {new_email}.",
                    "Confirma desde este enlace para completar el cambio.",
                ],
                action_label="Confirmar nuevo correo",
                action_url=web_link(settings, f"/verificar?token={token}"),
            ),
        )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {"ok": True, "delivered": result.delivered, "pending_email": new_email}


_ = session_token  # re-exported for account routes
