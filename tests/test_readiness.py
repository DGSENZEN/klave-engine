"""Readiness probes dependencies without migrating or exposing their details."""

import importlib
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from klave_engine.common.config import Settings


def module():
    try:
        return importlib.import_module("apps.api.readiness")
    except ModuleNotFoundError:
        pytest.fail("dependency readiness is not implemented")


class Connection:
    def __init__(self, missing=False):
        self.missing = missing
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, statement, params=None):
        self.statements.append(statement)
        return self

    def fetchall(self):
        return [("users", None if self.missing else "users")]


def test_ready_with_initialized_database_and_empty_writable_volume(tmp_path, monkeypatch):
    ready = module()
    conn = Connection()
    monkeypatch.setattr(ready.psycopg, "connect", lambda *a, **kw: conn)
    result = ready.check_readiness(Settings(data_dir=tmp_path))
    assert result["status"] == "ready"
    assert result["checks"] == {"database": "ok", "storage": "ok"}
    assert list((tmp_path / ".health").iterdir()) == []


def test_missing_schema_is_unavailable_without_ddl(tmp_path, monkeypatch):
    ready = module()
    conn = Connection(missing=True)
    monkeypatch.setattr(ready.psycopg, "connect", lambda *a, **kw: conn)
    result = ready.check_readiness(Settings(data_dir=tmp_path))
    assert result["checks"]["database"] == "unavailable"
    assert not any("CREATE" in sql or "ALTER" in sql for sql in conn.statements)


def test_storage_failure_is_unavailable(tmp_path, monkeypatch):
    ready = module()
    monkeypatch.setattr(ready.psycopg, "connect", lambda *a, **kw: Connection())
    obstruction = tmp_path / "not-a-directory"
    obstruction.write_text("preserve")
    result = ready.check_readiness(Settings(data_dir=obstruction))
    assert result["checks"]["storage"] == "unavailable"
    assert obstruction.read_text() == "preserve"


def test_concurrent_probes_leave_no_files(tmp_path, monkeypatch):
    ready = module()
    monkeypatch.setattr(ready.psycopg, "connect", lambda *a, **kw: Connection())
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda _: ready.check_readiness(Settings(data_dir=tmp_path)), range(16)
        ))
    assert all(result["status"] == "ready" for result in results)
    assert list((tmp_path / ".health").iterdir()) == []


def test_database_outage_keeps_liveness_and_anonymous_readiness(data_dir):
    from apps.api.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "unavailable"
    assert "postgresql" not in response.text
    assert str(data_dir) not in response.text


def test_readiness_does_not_exempt_other_paths(data_dir, monkeypatch):
    from apps.api import main
    from apps.api.auth import middleware

    class Store:
        def has_users(self):
            return True

        def get_session_user(self, token):
            return None

    monkeypatch.setattr(middleware, "get_user_store", lambda _: Store())
    with TestClient(main.create_app()) as client:
        assert "checks" in client.get("/ready").json()
        assert client.get("/ready/anything").status_code == 401
        assert client.post("/ready").status_code == 401
