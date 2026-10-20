"""Bounded dependency probes; no migration, customer data, or sensitive output."""

import tempfile
from pathlib import Path

import psycopg
from klave_engine import __version__
from klave_engine.common.config import Settings
from klave_engine.common.logging import get_logger

logger = get_logger("klave.readiness")
TABLES = [
    "workspaces", "users", "sessions", "project_access", "project_workspace",
    "invitations", "auth_tokens", "audit_log",
]


def _storage_ok(data_dir: Path) -> bool:
    probe = None
    try:
        directory = data_dir / ".health"
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink():
            return False
        with tempfile.NamedTemporaryFile(dir=directory, prefix="ready-", delete=False) as handle:
            probe = Path(handle.name)
            handle.write(b"ready")
            handle.flush()
            handle.seek(0)
            if handle.read() != b"ready":
                return False
        probe.unlink()
        probe = None
        return True
    except OSError:
        return False
    finally:
        if probe is not None:
            try:
                probe.unlink()
            except OSError:
                logger.warning("Readiness storage probe cleanup failed")


def check_readiness(settings: Settings) -> dict:
    database = False
    try:
        with psycopg.connect(
            settings.users_database_url, connect_timeout=2, autocommit=True,
            options="-c statement_timeout=2000",
        ) as conn:
            rows = conn.execute(
                "SELECT name, to_regclass(name)::text FROM unnest(%s::text[]) AS name",
                (TABLES,),
            ).fetchall()
            database = bool(rows) and all(row[1] is not None for row in rows)
            if database:
                conn.execute(
                    "SELECT workspace_id, email_verified_at, pending_email FROM users LIMIT 0"
                )
                conn.execute("SELECT session_id, last_seen_at, remember FROM sessions LIMIT 0")
    except psycopg.Error:
        database = False
        logger.warning("Readiness database probe unavailable")
    storage = _storage_ok(settings.data_dir)
    return {
        "status": "ready" if database and storage else "unavailable",
        "version": __version__,
        "checks": {
            "database": "ok" if database else "unavailable",
            "storage": "ok" if storage else "unavailable",
        },
    }
