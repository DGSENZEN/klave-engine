"""Diagnostic visibility uses the authenticated workspace before sampling."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from klave_engine.common.bitacora import ErrorRegistrado, anotar_error, errores_recientes

from apps.api.auth.store import UsersDbUnavailable


class DiagnosticUsers:
    last_known_has_users = True
    protected = True
    unavailable = False

    def has_users(self):
        if self.unavailable:
            raise UsersDbUnavailable("offline")
        return self.protected

    def get_session_user(self, token):
        if token not in ("a", "b", "member", "missing"):
            return None
        return dict(
            user_id=token,
            workspace_id="" if token == "missing" else ("ws-b" if token == "b" else "ws-a"),
            role="member" if token == "member" else "admin",
            name="Synthetic",
            status="active",
        )


@pytest.fixture
def diagnostic_client(data_dir, monkeypatch):
    from apps.api.auth import middleware
    from apps.api.main import create_app

    users = DiagnosticUsers()
    monkeypatch.setattr(middleware, "get_user_store", lambda *_: users)
    return TestClient(create_app()), users


def seed(data_dir, workspace, message="own", seconds=0):
    anotar_error(
        data_dir,
        ErrorRegistrado(
            ts=(datetime.now(UTC) + timedelta(seconds=seconds)).isoformat(),
            request_id="ref-1",
            ruta="/synthetic",
            metodo="GET",
            tipo="SyntheticError",
            mensaje=message,
            workspace=workspace,
        ),
    )


def test_workspace_filter_precedes_limit(data_dir):
    seed(data_dir, "ws-a")
    for _ in range(201):
        seed(data_dir, "ws-b", "FOREIGN", seconds=1)
    seed(data_dir, "", "SYSTEM", seconds=1)
    assert [f["mensaje"] for f in errores_recientes(data_dir, workspace="ws-a")] == ["own"]


def test_admin_sees_only_own_errors(diagnostic_client, data_dir):
    client, _ = diagnostic_client
    for workspace, message in [("ws-a", "own"), ("ws-b", "FOREIGN"), ("", "SYSTEM")]:
        seed(data_dir, workspace, message)
    for token, expected in [("a", "own"), ("b", "FOREIGN")]:
        client.cookies.set("klave_session", token)
        response = client.get("/workspace/errores?workspace=ws-b")
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["grupos"][0]["mensaje"] == expected
        assert str(data_dir) not in response.text
        assert "SYSTEM" not in response.text


@pytest.mark.parametrize("token,status", [(None, 401), ("member", 403), ("missing", 403)])
def test_member_and_anonymous_denied(diagnostic_client, token, status):
    client, _ = diagnostic_client
    if token:
        client.cookies.set("klave_session", token)
    assert client.get("/workspace/errores").status_code == status


def test_production_db_failure_does_not_open_diagnostics(diagnostic_client):
    client, users = diagnostic_client
    from klave_engine.common.config import get_settings

    get_settings().env = "production"
    users.last_known_has_users = False
    users.unavailable = True
    assert client.get("/workspace/errores").status_code == 503


def test_open_development_retains_local_view(diagnostic_client, data_dir):
    client, users = diagnostic_client
    users.protected = False
    seed(data_dir, "ws-a")
    seed(data_dir, "ws-b")
    assert client.get("/workspace/errores").json()["total"] == 2


def test_authenticated_support_reference_follows_request_to_worker(
    diagnostic_client, data_dir, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor

    from klave_engine.common.config import get_settings
    from klave_engine.common.io import read_json

    from apps.api import jobs, tenancy
    from apps.api.dependencies import ProjectStore
    from apps.api.routes import projects

    client, users = diagnostic_client
    users.project_workspace_id = lambda _: "ws-a"
    settings = get_settings()
    root = data_dir / "uploads" / "synthetic-project"
    root.mkdir(parents=True)
    ProjectStore(settings).register("synthetic-project", root)
    monkeypatch.setattr(tenancy, "store_for_project", lambda *_: None)

    def failing_pipeline(*args, **kwargs):
        raise RuntimeError("controlled synthetic processing failure")

    monkeypatch.setattr(jobs, "run_full_pipeline", failing_pipeline)
    with ThreadPoolExecutor(max_workers=1) as executor:
        scheduler = jobs.JobStore(_executor=executor)
        monkeypatch.setattr(projects, "JOB_STORE", scheduler)
        client.cookies.set("klave_session", "a")
        response = client.post(
            "/projects/synthetic-project/process",
            headers={
                "x-request-id": "support-reference",
                "x-actor": "FORGED",
                "x-workspace-id": "ws-b",
            },
        )
        assert response.status_code == 202, response.text
        assert response.headers["x-request-id"] == "support-reference"
    record = read_json(root / settings.processed_dir_name / "latest_job.json")
    context = record["diagnostic_context"]
    assert (context["request_id"], context["workspace_id"], context["user_id"]) == (
        "support-reference",
        "ws-a",
        "a",
    )
    assert record["state"] == "failed"
    own = client.get("/workspace/errores").json()
    assert own["total"] == 1 and own["grupos"][0]["request_id"] == "support-reference"
    rows = errores_recientes(data_dir, workspace="ws-a")
    assert rows[0]["job_id"] == record["job_id"] and rows[0]["run_id"] == record["run_id"]
    client.cookies.set("klave_session", "b")
    assert client.get("/workspace/errores").json()["total"] == 0
    assert "diagnostic_context" not in response.json()
