"""Workspace accounts on the dedicated users PostgreSQL instance.

Users, sessions, and per-project permissions live in their own database
(compose service ``users-db``), separate from the cost-data platform's
PostgreSQL. The workspace has two modes:

- **open**: no accounts exist yet — the tool behaves like the original
  local-first single-workspace app (name-only identity, no enforcement).
- **protected**: the first account (always admin, auto-approved) flips the
  workspace to enforced sessions, per-project roles, and the admin
  confirmation loop for every later registration.

Passwords use scrypt (stdlib); sessions are random tokens stored hashed.
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

logger = get_logger(__name__)

SESSION_TTL = timedelta(days=30)
PROJECT_ROLES = ("viewer", "editor", "owner")
ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}

_SCHEMA = """
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
    approved_by UUID
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS project_access (
    project_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('viewer', 'editor', 'owner')),
    granted_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, user_id)
);
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


class UserStore:
    """Per-operation connections; low-traffic workspace usage."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._lock = threading.Lock()
        self._schema_ready = False
        self._down_until = 0.0
        self._has_users_cache: tuple[float, bool] | None = None
        # Fail-closed signal: once this process has seen accounts, a database
        # outage must not silently reopen the workspace.
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
                    self._schema_ready = True
                    log_stage(logger, "users_db_ready")
        return conn

    def available(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1")
            return True
        except UsersDbUnavailable:
            return False

    def has_users(self) -> bool:
        """Whether the workspace is in protected mode. Briefly cached."""
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

    # -------------------------------------------------------------- users

    def create_user(
        self,
        *,
        email: str,
        name: str,
        password: str | None = None,
        google_sub: str | None = None,
        picture: str | None = None,
    ) -> dict[str, Any]:
        """First account bootstraps the admin; later ones await approval."""
        email = email.strip().lower()
        with self._connect() as conn:
            first = not self.has_users()
            row = conn.execute(
                "INSERT INTO users (email, name, password_hash, google_sub, picture, "
                "role, status, approved_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING *",
                (
                    email,
                    name.strip(),
                    hash_password(password) if password else None,
                    google_sub,
                    picture,
                    "admin" if first else "member",
                    "active" if first else "pending",
                    datetime.now(UTC) if first else None,
                ),
            ).fetchone()
        self._invalidate_has_users()
        log_stage(
            logger, "user_created", email=email,
            role=row["role"], status=row["status"],  # type: ignore[index]
        )
        return dict(row)  # type: ignore[arg-type]

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
                "UPDATE users SET google_sub = %s, picture = COALESCE(%s, picture) "
                "WHERE user_id = %s",
                (sub, picture, user_id),
            )

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, email, name, picture, role, status, created_at, "
                "approved_at FROM users ORDER BY created_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def set_status(self, user_id: str, status: str, approved_by: str | None) -> bool:
        if status not in ("active", "disabled"):
            raise ValueError("invalid status")
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE users SET status = %s, approved_at = COALESCE(approved_at, %s), "
                "approved_by = COALESCE(approved_by, %s) WHERE user_id = %s",
                (status, datetime.now(UTC), approved_by, user_id),
            )
        return result.rowcount > 0

    def set_role(self, user_id: str, role: str) -> bool:
        if role not in ("admin", "member"):
            raise ValueError("invalid role")
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE users SET role = %s WHERE user_id = %s", (role, user_id)
            )
        return result.rowcount > 0

    # ----------------------------------------------------------- sessions

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) "
                "VALUES (%s, %s, %s)",
                (_token_hash(token), user_id, datetime.now(UTC) + SESSION_TTL),
            )
        return token

    def get_session_user(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.user_id = s.user_id "
                "WHERE s.token_hash = %s AND s.expires_at > now()",
                (_token_hash(token),),
            ).fetchone()
        return dict(row) if row else None

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token),))

    # ----------------------------------------------------- project access

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


_STORE: UserStore | None = None
_STORE_LOCK = threading.Lock()


def get_user_store(database_url: str) -> UserStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None or _STORE.database_url != database_url:
            _STORE = UserStore(database_url)
        return _STORE
