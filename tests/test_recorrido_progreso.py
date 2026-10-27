"""El progreso del recorrido, por persona: una bitácora que sólo crece (es el
embudo de dónde se atora la gente) y de la que se lee el último estado de
cada paso desde el último «reiniciar»."""

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient  # noqa: E402

from apps.api.auth.common import users_dependency  # noqa: E402
from apps.api.auth.middleware import SESSION_COOKIE  # noqa: E402
from apps.api.auth.store import UserStore  # noqa: E402

ADMIN_URL = "postgresql://klave_users:klave@127.0.0.1:5433/klave_users"
TEST_URL = "postgresql://klave_users:klave@127.0.0.1:5433/klave_users_test"


def _users_db_running() -> bool:
    try:
        with psycopg.connect(ADMIN_URL, connect_timeout=2):
            return True
    except (psycopg.OperationalError, OSError):
        return False


needs_db = pytest.mark.skipif(
    not _users_db_running(), reason="users-db is not running (make users-db-up)"
)


@pytest.fixture
def store():
    with psycopg.connect(ADMIN_URL, autocommit=True, connect_timeout=3) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'klave_users_test'"
        ).fetchone()
        if not exists:
            conn.execute("CREATE DATABASE klave_users_test")
    instance = UserStore(TEST_URL)
    with instance._connect() as conn:
        conn.execute("TRUNCATE recorrido_eventos, project_access, sessions, users CASCADE")
    instance._has_users_cache = None
    instance.last_known_has_users = None
    yield instance


@needs_db
def test_latest_state_wins(store):
    user = store.create_user(email="a@t.mx", name="Ana", password="secreta-123")
    uid = str(user["user_id"])
    store.record_recorrido(uid, "planos.decidir", "saltado")
    store.record_recorrido(uid, "planos.decidir", "hecho")
    assert store.recorrido_progreso(uid) == {"planos.decidir": "hecho"}


@needs_db
def test_no_encontrado_does_not_count_as_progress(store):
    uid = str(store.create_user(email="a@t.mx", name="Ana", password="secreta-123")["user_id"])
    store.record_recorrido(uid, "visor.inspector", "no_encontrado")
    assert store.recorrido_progreso(uid) == {}


@needs_db
def test_reiniciar_hides_older_rows_but_keeps_them(store):
    uid = str(store.create_user(email="a@t.mx", name="Ana", password="secreta-123")["user_id"])
    store.record_recorrido(uid, "arranque.crear", "hecho")
    store.reiniciar_recorrido(uid)
    assert store.recorrido_progreso(uid) == {}
    store.record_recorrido(uid, "arranque.hola", "hecho")
    assert store.recorrido_progreso(uid) == {"arranque.hola": "hecho"}
    with store._connect() as conn:
        count = conn.execute(
            "SELECT count(*) AS n FROM recorrido_eventos WHERE user_id = %s", (uid,)
        ).fetchone()["n"]
    assert count == 3


class _Users:
    """Un UserStore en memoria para probar las rutas sin Postgres."""

    def __init__(self):
        self.user = {"user_id": "u-1", "workspace_id": "w-1", "role": "member",
                     "status": "active", "email": "a@t.mx", "name": "Ana"}
        self.rows: list[tuple[str, str, str]] = []

    def get_session_user(self, token):
        return self.user if token == "ok" else None

    def record_recorrido(self, user_id, paso_id, estado):
        self.rows.append((user_id, paso_id, estado))

    def reiniciar_recorrido(self, user_id):
        self.rows.append((user_id, "", "reiniciado"))

    def recorrido_progreso(self, user_id):
        out: dict[str, str] = {}
        for uid, paso, estado in self.rows:
            if uid != user_id:
                continue
            if estado == "reiniciado":
                out = {}
            elif estado in ("hecho", "saltado"):
                out[paso] = estado
        return out


@pytest.fixture
def client(data_dir):
    from apps.api.main import create_app

    app = create_app()
    users = _Users()
    app.dependency_overrides[users_dependency] = lambda: users
    yield TestClient(app), users


def test_routes_require_a_session(client):
    http, _ = client
    assert http.get("/auth/me/recorrido").status_code == 401
    paso = {"paso_id": "x", "estado": "hecho"}
    assert http.put("/auth/me/recorrido", json=paso).status_code == 401
    assert http.delete("/auth/me/recorrido").status_code == 401


def test_put_get_and_delete_round_trip(client):
    http, users = client
    http.cookies.set(SESSION_COOKIE, "ok")
    assert http.put(
        "/auth/me/recorrido", json={"paso_id": "planos.decidir", "estado": "hecho"}
    ).status_code == 200
    assert http.get("/auth/me/recorrido").json() == {"pasos": {"planos.decidir": "hecho"}}
    assert http.delete("/auth/me/recorrido").json() == {"ok": True}
    assert http.get("/auth/me/recorrido").json() == {"pasos": {}}
    assert users.rows[-1] == ("u-1", "", "reiniciado")


def test_put_rejects_unknown_states_and_long_ids(client):
    http, _ = client
    http.cookies.set(SESSION_COOKIE, "ok")
    assert http.put(
        "/auth/me/recorrido", json={"paso_id": "x", "estado": "reiniciado"}
    ).status_code == 422
    assert http.put(
        "/auth/me/recorrido", json={"paso_id": "x" * 81, "estado": "hecho"}
    ).status_code == 422
