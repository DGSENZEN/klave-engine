"""The signed-in user's own account: profile, password, sessions, Google
link — plus the admin-only activity log."""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import HTTPException
from pydantic import BaseModel, Field

from apps.api.auth.common import (
    audit,
    db_unavailable,
    public_user,
    rate_limit,
    require_admin,
    require_user,
    session_token,
    users_dependency,
)
from apps.api.auth.middleware import SESSION_COOKIE
from apps.api.auth.passwords import password_problem
from apps.api.auth.store import UsersDbUnavailable, UserStore, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class ProfileInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class PasswordInput(BaseModel):
    current_password: str = Field(default="", max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.get("/me")
def me(request: Request, users: UserStore = Depends(users_dependency)) -> dict:
    try:
        user = require_user(request, users)
        workspace = users.get_workspace(str(user["workspace_id"]))
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {
        **public_user(user),
        "workspace": {"slug": workspace["slug"], "name": workspace["name"]} if workspace else None,
        "created_at": user["created_at"].isoformat(),
    }


@router.put("/me")
def update_me(
    body: ProfileInput, request: Request, users: UserStore = Depends(users_dependency)
) -> dict:
    try:
        user = require_user(request, users)
        updated = users.update_profile(str(user["user_id"]), name=body.name)
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    assert updated is not None
    return public_user(updated)


@router.post("/password")
def change_password(
    body: PasswordInput,
    request: Request,
    users: UserStore = Depends(users_dependency),
) -> dict:
    """Change (or set, for Google-only accounts) the password. Every other
    session is revoked; the current one stays signed in."""
    rate_limit(request, "password")
    try:
        user = require_user(request, users)
        existing_hash = user.get("password_hash")
        if existing_hash and not verify_password(body.current_password, existing_hash):
            raise HTTPException(
                status_code=401,
                detail={
                    "error_type": "invalid_credentials",
                    "message": "La contraseña actual no coincide.",
                },
            )
        problem = password_problem(body.new_password, str(user.get("email") or ""))
        if problem:
            raise HTTPException(
                status_code=422, detail={"error_type": "weak_password", "message": problem}
            )
        users.set_password(str(user["user_id"]), body.new_password)
        revoked = users.delete_sessions_for_user(
            str(user["user_id"]), keep_token=session_token(request)
        )
        audit(users, user, "password_changed", target_type="user", target_id=str(user["user_id"]))
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {"ok": True, "sessions_revoked": revoked}


@router.get("/sessions")
def list_sessions(request: Request, users: UserStore = Depends(users_dependency)) -> dict:
    try:
        user = require_user(request, users)
        rows = users.list_sessions(str(user["user_id"]), session_token(request))
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {
        "sessions": [
            {
                "session_id": str(row["session_id"]),
                "created_at": row["created_at"].isoformat(),
                "last_seen_at": row["last_seen_at"].isoformat(),
                "expires_at": row["expires_at"].isoformat(),
                "user_agent": row.get("user_agent"),
                "ip": row.get("ip"),
                "remember": bool(row.get("remember")),
                "current": bool(row["current"]),
            }
            for row in rows
        ]
    }


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str, request: Request, users: UserStore = Depends(users_dependency)
) -> dict:
    try:
        user = require_user(request, users)
        if not users.delete_session_by_id(str(user["user_id"]), session_id):
            raise HTTPException(status_code=404, detail={"error_type": "session_not_found"})
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {"session_id": session_id, "revoked": True}


@router.post("/logout-all")
def logout_all(
    request: Request,
    response: Response,
    users: UserStore = Depends(users_dependency),
) -> dict:
    """Close every other session; this one keeps working."""
    try:
        user = require_user(request, users)
        revoked = users.delete_sessions_for_user(
            str(user["user_id"]), keep_token=session_token(request)
        )
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {"ok": True, "sessions_revoked": revoked}


@router.post("/google/unlink")
def unlink_google(request: Request, users: UserStore = Depends(users_dependency)) -> dict:
    try:
        user = require_user(request, users)
        if not user.get("google_sub"):
            raise HTTPException(
                status_code=422,
                detail={"error_type": "not_linked", "message": "Esta cuenta no usa Google."},
            )
        if not users.unlink_google(str(user["user_id"])):
            raise HTTPException(
                status_code=422,
                detail={
                    "error_type": "needs_password",
                    "message": "Define una contraseña antes de desvincular Google.",
                },
            )
        audit(users, user, "google_unlinked", target_type="user", target_id=str(user["user_id"]))
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {"ok": True}


@router.get("/audit")
def audit_log(
    request: Request, limit: int = 100, users: UserStore = Depends(users_dependency)
) -> dict:
    try:
        admin = require_admin(request, users)
        rows = users.list_audit(str(admin["workspace_id"]), limit=limit)
    except UsersDbUnavailable as exc:
        raise db_unavailable() from exc
    return {
        "entries": [
            {
                "audit_id": row["audit_id"],
                "actor_id": str(row["actor_id"]) if row.get("actor_id") else None,
                "actor_name": row.get("actor_name"),
                "action": row["action"],
                "target_type": row.get("target_type"),
                "target_id": row.get("target_id"),
                "detail": row.get("detail") or {},
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]
    }


_ = SESSION_COOKIE
