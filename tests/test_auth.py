"""Workspace accounts against the dedicated PostgreSQL instance.

Runs against a throwaway ``klave_users_test`` database on the same compose
instance; every test is skipped cleanly when the container isn't running
(``make users-db-up``).
"""

import pytest

psycopg = pytest.importorskip("psycopg")

from klave_engine.common import config as config_module  # noqa: E402

import apps.api.auth.store as store_module  # noqa: E402
from apps.api.auth.store import UserStore, verify_password  # noqa: E402

ADMIN_URL = "postgresql://klave_users:klave@127.0.0.1:5433/klave_users"
TEST_URL = "postgresql://klave_users:klave@127.0.0.1:5433/klave_users_test"


def _users_db_running() -> bool:
    try:
        with psycopg.connect(ADMIN_URL, connect_timeout=2):
            return True
    except (psycopg.OperationalError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _users_db_running(), reason="users-db is not running (make users-db-up)"
)


@pytest.fixture
def store():
    # Timeouts everywhere: a dying Docker daemon must skip tests, not hang them.
    with psycopg.connect(ADMIN_URL, autocommit=True, connect_timeout=3) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'klave_users_test'"
        ).fetchone()
        if not exists:
            conn.execute("CREATE DATABASE klave_users_test")
    instance = UserStore(TEST_URL)
    with instance._connect() as conn:
        conn.execute("TRUNCATE project_access, sessions, users CASCADE")
    instance._has_users_cache = None
    instance.last_known_has_users = None
    yield instance


def test_first_account_bootstraps_admin(store):
    first = store.create_user(email="Admin@Taller.MX", name="Admin", password="secreta-123")
    assert first["role"] == "admin" and first["status"] == "active"
    assert first["email"] == "admin@taller.mx"  # normalized
    second = store.create_user(email="ana@taller.mx", name="Ana", password="otra-secreta")
    assert second["role"] == "member" and second["status"] == "pending"


def test_password_hashing_is_scrypt_and_verifies(store):
    user = store.create_user(email="a@b.mx", name="A", password="mi contraseña ñ")
    stored = store.get_by_email("a@b.mx")["password_hash"]
    assert "$" in stored and "mi contraseña" not in stored
    assert verify_password("mi contraseña ñ", stored)
    assert not verify_password("otra", stored)
    assert not verify_password("x", None)
    assert user["status"] == "active"


def test_sessions_round_trip_and_revoke(store):
    user = store.create_user(email="a@b.mx", name="A", password="secreta-123")
    token = store.create_session(str(user["user_id"]))
    assert store.get_session_user(token)["email"] == "a@b.mx"
    assert store.get_session_user("token-falso") is None
    store.delete_session(token)
    assert store.get_session_user(token) is None


def test_project_roles_and_listing(store):
    admin = store.create_user(email="a@b.mx", name="A", password="secreta-123")
    ana = store.create_user(email="ana@b.mx", name="Ana", password="secreta-456")
    store.set_status(str(ana["user_id"]), "active", str(admin["user_id"]))
    store.grant_access("proj_1", str(ana["user_id"]), "viewer", str(admin["user_id"]))
    assert store.project_role("proj_1", str(ana["user_id"])) == "viewer"
    assert store.project_ids_for_user(str(ana["user_id"])) == {"proj_1"}
    # Re-granting upgrades in place.
    store.grant_access("proj_1", str(ana["user_id"]), "editor", str(admin["user_id"]))
    assert store.project_role("proj_1", str(ana["user_id"])) == "editor"
    assert store.revoke_access("proj_1", str(ana["user_id"]))
    assert store.project_role("proj_1", str(ana["user_id"])) is None


def test_protected_mode_flip_and_middleware(store, data_dir, monkeypatch):
    """The API opens with no accounts, then enforces sessions and roles."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", TEST_URL)
    config_module.get_settings.cache_clear()
    monkeypatch.setattr(store_module, "_STORE", None)

    from apps.api.main import create_app

    app = create_app()
    # One client per identity: TestClient persists cookies per instance.
    admin_client = TestClient(app)
    anonymous_client = TestClient(app)
    pending_client = TestClient(app)

    assert admin_client.get("/auth/session").json()["mode"] == "open"
    assert anonymous_client.get("/projects").status_code == 200  # open mode passes

    created = admin_client.post(
        "/auth/register",
        json={"email": "jefe@taller.mx", "name": "Jefa", "password": "secreta-123"},
    )
    assert created.status_code == 201
    assert created.json()["role"] == "admin"

    # Cache TTL: force the fresh protected state to be visible immediately.
    store_module._STORE._has_users_cache = None

    assert anonymous_client.get("/projects").status_code == 401
    assert admin_client.get("/projects").status_code == 200

    pending = pending_client.post(
        "/auth/register",
        json={"email": "nuevo@taller.mx", "name": "Nuevo", "password": "secreta-456"},
    )
    assert pending.json()["status"] == "pending"
    login = pending_client.post(
        "/auth/login", json={"email": "nuevo@taller.mx", "password": "secreta-456"}
    )
    assert login.status_code == 200
    blocked = pending_client.get("/projects")
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["error_type"] == "pending_approval"
