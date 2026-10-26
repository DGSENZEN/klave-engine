"""La obra de ejemplo: el primer botón que ve un taller vacío tiene que abrir
una obra, no un error. Se crea una vez por workspace y se procesa como trabajo."""

import pytest
from fastapi import HTTPException, Request
from klave_engine.common import config as config_module
from klave_engine.common.config import get_settings

from apps.api import jobs as jobs_module
from apps.api import tenancy
from apps.api.auth import access
from apps.api.auth.middleware import _required_project_role
from apps.api.auth.store import UsersDbUnavailable
from apps.api.dependencies import ProjectStore
from apps.api.routes import projects as projects_module


def _fake_enqueue(monkeypatch):
    calls = []
    fake = jobs_module.Job(project_id="x", job_id="j", run_id="r")

    def enqueue(project_id, *_a, **kwargs):
        calls.append((project_id, kwargs.get("context")))
        return fake, True

    monkeypatch.setattr(projects_module.JOB_STORE, "enqueue", enqueue)
    return calls


def test_sample_obra_is_created_once_and_processed_as_a_job(data_dir, monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    calls = _fake_enqueue(monkeypatch)
    client = TestClient(create_app())

    first = client.post("/projects/demo", json={})
    assert first.status_code == 202, first.text
    body = first.json()
    assert body["fresh"] is True and body["job_id"] == "j"
    project_id = body["project_id"]
    assert project_id.startswith("obra_de_ejemplo_")
    info = client.get(f"/projects/{project_id}").json()
    assert info["project_name"] == "Obra de ejemplo (sintética)"
    assert calls and calls[0][0] == project_id and calls[0][1] is not None

    again = client.post("/projects/demo", json={})
    assert again.status_code == 202
    assert again.json()["project_id"] == project_id and again.json()["fresh"] is False


def test_middleware_does_not_read_demo_as_a_project_id():
    assert _required_project_role(["projects", "demo"], "POST") is None
    assert _required_project_role(["projects", "upload"], "POST") is None


class _Users:
    def __init__(self):
        self.grants = {}
        self.workspaces = {}

    def has_users(self):
        return True

    def default_workspace(self):
        return {"workspace_id": "ws-a"}

    def grant_access(self, project_id, user_id, role, granted_by):
        self.grants[project_id, user_id] = role

    def register_project(self, project_id, workspace_id):
        self.workspaces[project_id] = workspace_id


def _request(workspace):
    return Request({
        "type": "http", "headers": [], "client": ("127.0.0.1", 1),
        "state": {"user": {"user_id": f"u-{workspace}", "workspace_id": workspace,
                           "role": "admin"}},
    })


def test_each_workspace_gets_its_own_sample_obra(data_dir, monkeypatch):
    settings = get_settings()
    store = ProjectStore(settings)
    users = _Users()
    for module in (projects_module, access, tenancy):
        monkeypatch.setattr(module, "get_user_store", lambda _url: users)
    _fake_enqueue(monkeypatch)

    a = projects_module.create_demo_project(
        _request("ws-aaaaaaaa-1"), store=store, settings=settings
    )
    b = projects_module.create_demo_project(
        _request("ws-aaaaaaaa-2"), store=store, settings=settings
    )
    # Same first eight characters, different workspaces: never one obra for both.
    assert a["project_id"] != b["project_id"]
    assert users.workspaces[a["project_id"]] == "ws-aaaaaaaa-1"
    assert users.grants[a["project_id"], "u-ws-aaaaaaaa-1"] == "owner"


def test_sample_obra_is_not_published_when_ownership_cannot_be_saved(data_dir, monkeypatch):
    settings = get_settings()
    store = ProjectStore(settings)
    users = _Users()
    for module in (projects_module, access, tenancy):
        monkeypatch.setattr(module, "get_user_store", lambda _url: users)
    _fake_enqueue(monkeypatch)

    def unavailable(*_args):
        raise UsersDbUnavailable("users database disconnected")

    monkeypatch.setattr(users, "register_project", unavailable)
    with pytest.raises(HTTPException) as caught:
        projects_module.create_demo_project(_request("ws-b"), store=store, settings=settings)
    assert caught.value.status_code == 503
    assert store.list_projects() == {}
