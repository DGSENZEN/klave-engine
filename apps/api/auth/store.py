"""Workspace accounts on the dedicated users PostgreSQL instance.

Users, sessions, invitations, recovery tokens, per-project permissions, and
the audit log live in their own database (compose service ``users-db``),
separate from the cost-data platform's PostgreSQL.

Every row is scoped to a **workspace** (a taller). A deployment starts with
one default workspace; more can be created from the CLI and share the same
server. An email belongs to exactly one workspace.

The deployment has two modes:

- **open**: no accounts exist yet — the tool behaves like the original
  local-first single-workspace app (name-only identity, no enforcement).
- **protected**: the first account (always admin, auto-approved) flips the
  deployment to enforced sessions, per-project roles, and the admin
  confirmation loop (or invitations) for every later account.

Passwords use scrypt (stdlib); sessions, invitations, and recovery tokens are
random and stored hashed.
"""

import hashlib
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from klave_engine.common.logging import get_logger, log_stage
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

logger = get_logger(__name__)

SESSION_TTL_DEFAULT = timedelta(hours=24)
SESSION_TTL_REMEMBER = timedelta(days=30)
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)
INVITATION_TTL = timedelta(days=7)
RESET_TTL = timedelta(hours=1)
ADMIN_RECOVERY_TTL = timedelta(hours=24)
VERIFY_TTL = timedelta(days=3)

PROJECT_ROLES = ("viewer", "editor", "owner")
ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}
TOKEN_PURPOSES = ("reset", "verify")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT,
    google_sub TEXT UNIQUE,
    picture TEXT,
    role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'active', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    approved_by UUID,
    workspace_id UUID REFERENCES workspaces(workspace_id),
    email_verified_at TIMESTAMPTZ,
    pending_email TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    session_id UUID NOT NULL DEFAULT gen_random_uuid(),
    user_agent TEXT,
    ip TEXT,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    remember BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS project_access (
    project_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('viewer', 'editor', 'owner')),
    granted_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, user_id)
);
CREATE TABLE IF NOT EXISTS project_workspace (
    project_id TEXT PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(workspace_id)
);
CREATE TABLE IF NOT EXISTS invitations (
    invite_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(workspace_id),
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
    project_grants JSONB NOT NULL DEFAULT '[]'::jsonb,
    token_hash TEXT NOT NULL UNIQUE,
    invited_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    accepted_user_id UUID,
    revoked_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    purpose TEXT NOT NULL CHECK (purpose IN ('reset', 'verify')),
    payload TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    workspace_id UUID REFERENCES workspaces(workspace_id),
    actor_id UUID,
    actor_name TEXT,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# Idempotent upgrades for databases created before the workspace schema.
_MIGRATIONS = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(workspace_id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS pending_email TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS session_id UUID NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS user_agent TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS ip TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS remember BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id);
CREATE INDEX IF NOT EXISTS audit_workspace_idx ON audit_log (workspace_id, audit_id DESC);
CREATE INDEX IF NOT EXISTS invitations_workspace_idx ON invitations (workspace_id, created_at DESC);
"""


class UsersDbUnavailable(Exception):
    """The users database cannot be reached."""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"{salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or "$" not in stored:
        return False
    salt_hex, key_hex = stored.split("$", 1)
    try:
        expected = bytes.fromhex(key_hex)
        key = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32
        )
    except ValueError:
        return False
    return secrets.compare_digest(key, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


class UserStore:
    """Per-operation connections; low-traffic workspace usage."""

    def __init__(
        self,
        database_url: str,
        default_workspace: tuple[str, str] = ("taller", "Taller"),
    ) -> None:
        self.database_url = database_url
        self.default_workspace_slug, self.default_workspace_name = default_workspace
        self._lock = threading.Lock()
        self._schema_ready = False
        self._down_until = 0.0
        self._has_users_cache: tuple[float, bool] | None = None
        self._default_workspace: dict[str, Any] | None = None
        # Fail-closed signal: once this process has seen accounts, a database
        # outage must not silently reopen the deployment.
        self.last_known_has_users: bool | None = None

    # ------------------------------------------------------------ plumbing

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        if time.monotonic() < self._down_until:
            raise UsersDbUnavailable()
        try:
            conn = psycopg.connect(
                self.database_url, autocommit=True, row_factory=dict_row,
                connect_timeout=3,
            )
        except psycopg.OperationalError as exc:
            # Negative-cache the outage so every request doesn't pay a
            # connection timeout while the container is down.
            self._down_until = time.monotonic() + 10.0
            raise UsersDbUnavailable() from exc
        self._down_until = 0.0
        if not self._schema_ready:
            with self._lock:
                if not self._schema_ready:
                    conn.execute(_SCHEMA)
                    conn.execute(_MIGRATIONS)
                    self._bootstrap_workspace(conn)
                    self._schema_ready = True
                    log_stage(logger, "users_db_ready")
        return conn

    def _bootstrap_workspace(self, conn: psycopg.Connection[dict[str, Any]]) -> None:
        """Ensure the default workspace exists and pre-workspace rows join it."""
        row = conn.execute(
            "INSERT INTO workspaces (slug, name) VALUES (%s, %s) "
            "ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug RETURNING *",
            (self.default_workspace_slug, self.default_workspace_name),
        ).fetchone()
        assert row is not None
        self._default_workspace = dict(row)
        workspace_id = row["workspace_id"]
        conn.execute(
            "UPDATE users SET workspace_id = %s WHERE workspace_id IS NULL", (workspace_id,)
        )
        conn.execute(
            "INSERT INTO project_workspace (project_id, workspace_id) "
            "SELECT DISTINCT project_id, %s FROM project_access "
            "ON CONFLICT (project_id) DO NOTHING",
            (workspace_id,),
        )

    def available(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1")
            return True
        except UsersDbUnavailable:
            return False

    def has_users(self) -> bool:
        """Whether the deployment is in protected mode. Briefly cached."""
        cached = self._has_users_cache
        now = time.monotonic()
        if cached and now - cached[0] < 5.0:
            return cached[1]
        with self._connect() as conn:
            row = conn.execute("SELECT EXISTS (SELECT 1 FROM users) AS present").fetchone()
        result = bool(row and row["present"])
        self._has_users_cache = (now, result)
        self.last_known_has_users = result
        return result

    def _invalidate_has_users(self) -> None:
        self._has_users_cache = None

    # --------------------------------------------------------- workspaces

    def default_workspace(self) -> dict[str, Any]:
        if self._default_workspace is None:
            with self._connect():
                pass
        assert self._default_workspace is not None
        return self._default_workspace

    def create_workspace(self, slug: str, name: str) -> dict[str, Any]:
        slug = slug.strip().lower()
        if not slug or not name.strip():
            raise ValueError("slug y nombre son obligatorios")
        with self._connect() as conn:
            try:
                row = conn.execute(
                    "INSERT INTO workspaces (slug, name) VALUES (%s, %s) RETURNING *",
                    (slug, name.strip()),
                ).fetchone()
            except psycopg.errors.UniqueViolation as exc:
                raise ValueError(f"ya existe un taller con la clave {slug}") from exc
        log_stage(logger, "workspace_created", slug=slug)
        return dict(row)  # type: ignore[arg-type]

    def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspaces WHERE workspace_id = %s", (workspace_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_workspace_by_slug(self, slug: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspaces WHERE slug = %s", (slug.strip().lower(),)
            ).fetchone()
        return dict(row) if row else None

    def rename_workspace(self, workspace_id: str, name: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE workspaces SET name = %s WHERE workspace_id = %s RETURNING *",
                (name.strip(), workspace_id),
            ).fetchone()
        if row is None:
            raise ValueError("no existe el taller")
        if self._default_workspace and str(self._default_workspace["workspace_id"]) == str(
            workspace_id
        ):
            self._default_workspace = dict(row)
        return dict(row)

    def list_workspaces(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT w.*, (SELECT count(*) FROM users u WHERE u.workspace_id = w.workspace_id) "
                "AS user_count FROM workspaces w ORDER BY created_at"
            ).fetchall()
        return [dict(row) for row in rows]

    # -------------------------------------------------------------- users

    def create_user(
        self,
        *,
        email: str,
        name: str,
        password: str | None = None,
        google_sub: str | None = None,
        picture: str | None = None,
        workspace_id: str | None = None,
        role: str | None = None,
        status: str | None = None,
        email_verified: bool = False,
    ) -> dict[str, Any]:
        """First account of a workspace bootstraps its admin; later ones await
        approval unless role/status are given explicitly (invitations)."""
        email = email.strip().lower()
        workspace_id = workspace_id or str(self.default_workspace()["workspace_id"])
        with self._connect() as conn:
            first_row = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM users WHERE workspace_id = %s) AS present",
                (workspace_id,),
            ).fetchone()
            first = not (first_row and first_row["present"])
            resolved_role = role or ("admin" if first else "member")
            resolved_status = status or ("active" if first else "pending")
            now = _now()
            row = conn.execute(
                "INSERT INTO users (email, name, password_hash, google_sub, picture, "
                "role, status, approved_at, workspace_id, email_verified_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (
                    email,
                    name.strip(),
                    hash_password(password) if password else None,
                    google_sub,
                    picture,
                    resolved_role,
                    resolved_status,
                    now if resolved_status == "active" else None,
                    workspace_id,
                    now if email_verified else None,
                ),
            ).fetchone()
        self._invalidate_has_users()
        log_stage(
            logger, "user_created", email=email,
            role=row["role"], status=row["status"],  # type: ignore[index]
        )
        return dict(row)  # type: ignore[arg-type]

    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = %s", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = %s", (email.strip().lower(),)
            ).fetchone()
        return dict(row) if row else None

    def get_by_google_sub(self, sub: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE google_sub = %s", (sub,)
            ).fetchone()
        return dict(row) if row else None

    def link_google(self, user_id: str, sub: str, picture: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET google_sub = %s, picture = COALESCE(%s, picture), "
                "email_verified_at = COALESCE(email_verified_at, now()) WHERE user_id = %s",
                (sub, picture, user_id),
            )

    def unlink_google(self, user_id: str) -> bool:
        """Only linked accounts that can still sign in with a password may unlink."""
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE users SET google_sub = NULL WHERE user_id = %s "
                "AND password_hash IS NOT NULL AND google_sub IS NOT NULL",
                (user_id,),
            )
        return result.rowcount > 0

    def update_profile(self, user_id: str, *, name: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE users SET name = %s WHERE user_id = %s RETURNING *",
                (name.strip(), user_id),
            ).fetchone()
        return dict(row) if row else None

    def mark_email_verified(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET email_verified_at = COALESCE(email_verified_at, now()) "
                "WHERE user_id = %s",
                (user_id,),
            )

    def set_pending_email(self, user_id: str, email: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET pending_email = %s WHERE user_id = %s",
                (email.strip().lower() if email else None, user_id),
            )

    def apply_pending_email(self, user_id: str, email: str) -> bool:
        """Swap the address once its verification token is consumed."""
        email = email.strip().lower()
        with self._connect() as conn:
            try:
                result = conn.execute(
                    "UPDATE users SET email = %s, pending_email = NULL, "
                    "email_verified_at = now() WHERE user_id = %s",
                    (email, user_id),
                )
            except psycopg.errors.UniqueViolation:
                return False
        return result.rowcount > 0

    def list_users(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, email, name, picture, role, status, created_at, "
                "approved_at, email_verified_at, google_sub IS NOT NULL AS has_google, "
                "password_hash IS NOT NULL AS has_password FROM users "
                "WHERE workspace_id = %s ORDER BY created_at",
                (workspace_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_active_admins(self, workspace_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT count(*) AS n FROM users WHERE workspace_id = %s "
                "AND role = 'admin' AND status = 'active'",
                (workspace_id,),
            ).fetchone()
        return int(row["n"]) if row else 0

    def is_last_active_admin(self, user: dict[str, Any]) -> bool:
        return (
            user["role"] == "admin"
            and user["status"] == "active"
            and self.count_active_admins(str(user["workspace_id"])) <= 1
        )

    def set_status(self, user_id: str, status: str, approved_by: str | None) -> bool:
        if status not in ("active", "disabled"):
            raise ValueError("invalid status")
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE users SET status = %s, approved_at = COALESCE(approved_at, %s), "
                "approved_by = COALESCE(approved_by, %s) WHERE user_id = %s",
                (status, _now(), approved_by, user_id),
            )
            if status == "disabled":
                conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        return result.rowcount > 0

    def set_role(self, user_id: str, role: str) -> bool:
        if role not in ("admin", "member"):
            raise ValueError("invalid role")
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE users SET role = %s WHERE user_id = %s", (role, user_id)
            )
        return result.rowcount > 0

    def set_password(self, user_id: str, password: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = %s WHERE user_id = %s",
                (hash_password(password), user_id),
            )

    # ----------------------------------------------------------- sessions

    def create_session(
        self,
        user_id: str,
        *,
        remember: bool = False,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> str:
        token = secrets.token_urlsafe(32)
        ttl = SESSION_TTL_REMEMBER if remember else SESSION_TTL_DEFAULT
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at, user_agent, ip, "
                "remember) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    _token_hash(token), user_id, _now() + ttl,
                    (user_agent or "")[:300] or None, ip, remember,
                ),
            )
        return token

    def get_session_user(self, token: str | None) -> dict[str, Any] | None:
        """Resolve a session and slide its expiry (at most every few minutes)."""
        if not token:
            return None
        token_hash = _token_hash(token)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT u.*, s.last_seen_at AS session_last_seen, s.remember AS session_remember "
                "FROM sessions s JOIN users u ON u.user_id = s.user_id "
                "WHERE s.token_hash = %s AND s.expires_at > now()",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            if _now() - row["session_last_seen"] > SESSION_TOUCH_INTERVAL:
                ttl = SESSION_TTL_REMEMBER if row["session_remember"] else SESSION_TTL_DEFAULT
                conn.execute(
                    "UPDATE sessions SET last_seen_at = now(), expires_at = %s "
                    "WHERE token_hash = %s",
                    (_now() + ttl, token_hash),
                )
        user = dict(row)
        user.pop("session_last_seen", None)
        user.pop("session_remember", None)
        return user

    def list_sessions(self, user_id: str, current_token: str | None) -> list[dict[str, Any]]:
        current_hash = _token_hash(current_token) if current_token else None
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT session_id, created_at, last_seen_at, expires_at, user_agent, ip, "
                "remember, token_hash = %s AS current FROM sessions "
                "WHERE user_id = %s AND expires_at > now() ORDER BY last_seen_at DESC",
                (current_hash, user_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token),))

    def delete_session_by_id(self, user_id: str, session_id: str) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM sessions WHERE user_id = %s AND session_id = %s",
                (user_id, session_id),
            )
        return result.rowcount > 0

    def delete_sessions_for_user(self, user_id: str, *, keep_token: str | None = None) -> int:
        with self._connect() as conn:
            if keep_token:
                result = conn.execute(
                    "DELETE FROM sessions WHERE user_id = %s AND token_hash <> %s",
                    (user_id, _token_hash(keep_token)),
                )
            else:
                result = conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        return result.rowcount

    # ------------------------------------------------------- auth tokens

    def issue_token(
        self, user_id: str, purpose: str, ttl: timedelta, payload: str | None = None
    ) -> str:
        if purpose not in TOKEN_PURPOSES:
            raise ValueError("invalid token purpose")
        token = secrets.token_urlsafe(32)
        with self._connect() as conn:
            # One live token per purpose: issuing a new one voids the previous.
            conn.execute(
                "UPDATE auth_tokens SET used_at = now() WHERE user_id = %s AND purpose = %s "
                "AND used_at IS NULL",
                (user_id, purpose),
            )
            conn.execute(
                "INSERT INTO auth_tokens (token_hash, user_id, purpose, payload, expires_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (_token_hash(token), user_id, purpose, payload, _now() + ttl),
            )
        return token

    def peek_token(self, token: str, purpose: str) -> dict[str, Any] | None:
        """The token's row joined with its user, if still valid."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT t.token_hash, t.user_id, t.purpose, t.payload, t.expires_at, "
                "u.email, u.name FROM auth_tokens t JOIN users u ON u.user_id = t.user_id "
                "WHERE t.token_hash = %s AND t.purpose = %s AND t.used_at IS NULL "
                "AND t.expires_at > now()",
                (_token_hash(token), purpose),
            ).fetchone()
        return dict(row) if row else None

    def consume_token(self, token: str, purpose: str) -> dict[str, Any] | None:
        row = self.peek_token(token, purpose)
        if row is None:
            return None
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE auth_tokens SET used_at = now() WHERE token_hash = %s AND used_at IS NULL",
                (row["token_hash"],),
            )
        return row if result.rowcount > 0 else None

    # -------------------------------------------------------- invitations

    def create_invitation(
        self,
        *,
        workspace_id: str,
        email: str,
        role: str,
        project_grants: list[dict[str, str]],
        invited_by: str | None,
    ) -> tuple[dict[str, Any], str]:
        if role not in ("admin", "member"):
            raise ValueError("invalid role")
        for grant in project_grants:
            if grant.get("role") not in PROJECT_ROLES or not grant.get("project_id"):
                raise ValueError("invalid project grant")
        token = secrets.token_urlsafe(32)
        email = email.strip().lower()
        with self._connect() as conn:
            # A fresh invitation supersedes any open one for the same address.
            conn.execute(
                "UPDATE invitations SET revoked_at = now() WHERE workspace_id = %s "
                "AND email = %s AND accepted_at IS NULL AND revoked_at IS NULL",
                (workspace_id, email),
            )
            row = conn.execute(
                "INSERT INTO invitations (workspace_id, email, role, project_grants, "
                "token_hash, invited_by, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "RETURNING *",
                (
                    workspace_id, email, role, Jsonb(project_grants),
                    _token_hash(token), invited_by, _now() + INVITATION_TTL,
                ),
            ).fetchone()
        log_stage(logger, "invitation_created", email=email, role=role)
        return dict(row), token  # type: ignore[arg-type]

    def get_invitation_by_token(self, token: str) -> dict[str, Any] | None:
        """The invitation plus a ``state``: open, accepted, revoked, expired."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT i.*, w.name AS workspace_name, w.slug AS workspace_slug, "
                "u.name AS inviter_name FROM invitations i "
                "JOIN workspaces w ON w.workspace_id = i.workspace_id "
                "LEFT JOIN users u ON u.user_id = i.invited_by WHERE i.token_hash = %s",
                (_token_hash(token),),
            ).fetchone()
        if row is None:
            return None
        invite = dict(row)
        invite["state"] = self._invitation_state(invite)
        return invite

    @staticmethod
    def _invitation_state(invite: dict[str, Any]) -> str:
        if invite.get("accepted_at"):
            return "accepted"
        if invite.get("revoked_at"):
            return "revoked"
        if invite["expires_at"] <= _now():
            return "expired"
        return "open"

    def list_invitations(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT i.*, u.name AS inviter_name FROM invitations i "
                "LEFT JOIN users u ON u.user_id = i.invited_by "
                "WHERE i.workspace_id = %s ORDER BY i.created_at DESC LIMIT 200",
                (workspace_id,),
            ).fetchall()
        result = []
        for row in rows:
            invite = dict(row)
            invite["state"] = self._invitation_state(invite)
            result.append(invite)
        return result

    def get_invitation(self, invite_id: str, workspace_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM invitations WHERE invite_id = %s AND workspace_id = %s",
                (invite_id, workspace_id),
            ).fetchone()
        if row is None:
            return None
        invite = dict(row)
        invite["state"] = self._invitation_state(invite)
        return invite

    def revoke_invitation(self, invite_id: str, workspace_id: str) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE invitations SET revoked_at = now() WHERE invite_id = %s "
                "AND workspace_id = %s AND accepted_at IS NULL AND revoked_at IS NULL",
                (invite_id, workspace_id),
            )
        return result.rowcount > 0

    def refresh_invitation(self, invite_id: str, workspace_id: str) -> str | None:
        """New token and expiry for an open or expired invitation (never a revoked one)."""
        token = secrets.token_urlsafe(32)
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE invitations SET token_hash = %s, expires_at = %s "
                "WHERE invite_id = %s AND workspace_id = %s AND accepted_at IS NULL "
                "AND revoked_at IS NULL",
                (_token_hash(token), _now() + INVITATION_TTL, invite_id, workspace_id),
            )
        return token if result.rowcount > 0 else None

    def accept_invitation(
        self,
        invite: dict[str, Any],
        *,
        name: str,
        password: str | None = None,
        google_sub: str | None = None,
        picture: str | None = None,
    ) -> dict[str, Any]:
        """Create the invited account: active, verified, with its grants —
        all in one transaction so a half-accepted invitation cannot exist."""
        if not password and not google_sub:
            raise ValueError("se requiere contraseña o cuenta de Google")
        now = _now()
        with self._connect() as conn, conn.transaction():
            # Re-read under lock: the caller's copy may be stale, and two
            # concurrent accepts must not both create the account.
            current = conn.execute(
                "SELECT * FROM invitations WHERE invite_id = %s FOR UPDATE",
                (invite["invite_id"],),
            ).fetchone()
            if current is None or self._invitation_state(dict(current)) != "open":
                raise ValueError("la invitación ya no está abierta")
            if conn.execute(
                "SELECT 1 FROM users WHERE email = %s", (invite["email"],)
            ).fetchone():
                raise ValueError("ese correo ya tiene cuenta")
            row = conn.execute(
                "INSERT INTO users (email, name, password_hash, google_sub, picture, role, "
                "status, approved_at, approved_by, workspace_id, email_verified_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'active', %s, %s, %s, %s) RETURNING *",
                (
                    invite["email"], name.strip(),
                    hash_password(password) if password else None,
                    google_sub, picture, invite["role"], now, invite.get("invited_by"),
                    invite["workspace_id"], now,
                ),
            ).fetchone()
            assert row is not None
            for grant in invite.get("project_grants") or []:
                conn.execute(
                    "INSERT INTO project_access (project_id, user_id, role, granted_by) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (project_id, user_id) "
                    "DO UPDATE SET role = EXCLUDED.role",
                    (grant["project_id"], row["user_id"], grant["role"], invite.get("invited_by")),
                )
            conn.execute(
                "UPDATE invitations SET accepted_at = %s, accepted_user_id = %s "
                "WHERE invite_id = %s",
                (now, row["user_id"], invite["invite_id"]),
            )
        self._invalidate_has_users()
        log_stage(logger, "invitation_accepted", email=invite["email"], role=invite["role"])
        return dict(row)

    # ----------------------------------------------------- project access

    def register_project(self, project_id: str, workspace_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO project_workspace (project_id, workspace_id) VALUES (%s, %s) "
                "ON CONFLICT (project_id) DO NOTHING",
                (project_id, workspace_id),
            )

    def project_workspace_id(self, project_id: str) -> str:
        """Projects created before workspaces belong to the default one."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT workspace_id FROM project_workspace WHERE project_id = %s",
                (project_id,),
            ).fetchone()
        if row:
            return str(row["workspace_id"])
        return str(self.default_workspace()["workspace_id"])

    def project_workspace_map(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT project_id, workspace_id FROM project_workspace").fetchall()
        return {row["project_id"]: str(row["workspace_id"]) for row in rows}

    def grant_access(
        self, project_id: str, user_id: str, role: str, granted_by: str | None
    ) -> None:
        if role not in PROJECT_ROLES:
            raise ValueError("invalid project role")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO project_access (project_id, user_id, role, granted_by) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (project_id, user_id) "
                "DO UPDATE SET role = EXCLUDED.role",
                (project_id, user_id, role, granted_by),
            )

    def revoke_access(self, project_id: str, user_id: str) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM project_access WHERE project_id = %s AND user_id = %s",
                (project_id, user_id),
            )
        return result.rowcount > 0

    def project_role(self, project_id: str, user_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT role FROM project_access WHERE project_id = %s AND user_id = %s",
                (project_id, user_id),
            ).fetchone()
        return row["role"] if row else None

    def project_members(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT a.role AS project_role, a.created_at AS granted_at, u.user_id, "
                "u.email, u.name, u.picture, u.status "
                "FROM project_access a JOIN users u ON u.user_id = a.user_id "
                "WHERE a.project_id = %s ORDER BY a.created_at",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def project_ids_for_user(self, user_id: str) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT project_id FROM project_access WHERE user_id = %s", (user_id,)
            ).fetchall()
        return {row["project_id"] for row in rows}

    # -------------------------------------------------------------- audit

    def record_audit(
        self,
        *,
        workspace_id: str | None,
        actor: dict[str, Any] | None,
        action: str,
        target_type: str | None = None,
        target_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (workspace_id, actor_id, actor_name, action, "
                "target_type, target_id, detail) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    workspace_id,
                    str(actor["user_id"]) if actor else None,
                    actor["name"] if actor else None,
                    action, target_type, target_id, Jsonb(detail or {}),
                ),
            )

    def list_audit(self, workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE workspace_id = %s "
                "ORDER BY audit_id DESC LIMIT %s",
                (workspace_id, max(1, min(limit, 500))),
            ).fetchall()
        return [dict(row) for row in rows]


_STORE: UserStore | None = None
_STORE_LOCK = threading.Lock()


def get_user_store(database_url: str) -> UserStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None or _STORE.database_url != database_url:
            from klave_engine.common.config import get_settings

            settings = get_settings()
            _STORE = UserStore(
                database_url,
                default_workspace=(settings.workspace_slug, settings.workspace_name),
            )
        return _STORE
