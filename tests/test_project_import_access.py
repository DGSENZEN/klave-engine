"""Importing a server folder must preserve existing project permissions."""

import pytest
from fastapi import HTTPException, Request
from klave_engine.common.config import get_settings
from klave_engine.ingestion.manifest import load_manifest, manifest_path
from klave_engine.ingestion.project_loader import ingest_project

from apps.api import tenancy
from apps.api.auth import access
from apps.api.auth.store import UsersDbUnavailable
from apps.api.dependencies import ProjectStore
from apps.api.routes import projects


class _Users:
    def __init__(self, role):
        self.grants = {("private", "visitor"): role} if role else {}

    def has_users(self):
        return True

    def default_workspace(self):
        return {"workspace_id": "ws-a"}

    def project_workspace_id(self, project_id):
        return "ws-a"

    def project_role(self, project_id, user_id):
        return self.grants.get((project_id, user_id))

    def grant_access(self, project_id, user_id, role, granted_by):
        self.grants[project_id, user_id] = role

    def register_project(self, project_id, workspace_id):
        pass


def _setup(data_dir, monkeypatch, *, role, workspace="ws-a", account_role="member"):
    settings = get_settings()
    root = data_dir / "uploads" / "private"
    (root / "drawings").mkdir(parents=True)
    (root / "drawings" / "S-101.dxf").write_text("0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n")
    ingest_project(root, project_id="private", project_name="Private project")
    store = ProjectStore(settings)
    store.register("private", root)
    users = _Users(role)
    for module in (projects, access, tenancy):
        monkeypatch.setattr(module, "get_user_store", lambda _url: users)
    request = Request({
        "type": "http",
        "state": {"user": {
            "user_id": "visitor", "workspace_id": workspace, "role": account_role,
        }},
    })
    return root, store, users, request


@pytest.mark.parametrize("role", [None, "viewer", "editor"])
@pytest.mark.parametrize("registered", [True, False])
def test_import_cannot_upgrade_an_existing_project_grant(data_dir, monkeypatch, role, registered):
    root, store, users, request = _setup(data_dir, monkeypatch, role=role)
    if not registered:
        store.unregister("private")  # soft deletion keeps the manifest and its identity
    before = manifest_path(root).read_bytes()

    with pytest.raises(HTTPException) as caught:
        projects.create_project(
            projects.CreateProjectRequest(project_name="Taken over", root_path=str(root)),
            request, store=store, settings=store.settings,
        )

    assert caught.value.status_code == 403
    assert manifest_path(root).read_bytes() == before
    assert users.project_role("private", "visitor") == role


@pytest.mark.parametrize("account_role", ["admin", "member"])
def test_import_cannot_cross_workspaces_even_with_a_stale_grant(
    data_dir, monkeypatch, account_role,
):
    root, store, _, request = _setup(
        data_dir, monkeypatch, role="owner", workspace="ws-b", account_role=account_role,
    )
    before = manifest_path(root).read_bytes()
    with pytest.raises(HTTPException) as caught:
        projects.create_project(
            projects.CreateProjectRequest(project_name="Taken over", root_path=str(root)),
            request, store=store, settings=store.settings,
        )
    assert caught.value.status_code == 403
    assert manifest_path(root).read_bytes() == before


@pytest.mark.parametrize("registered", [True, False])
def test_importing_drawings_subfolder_cannot_bypass_project_access(
    data_dir, monkeypatch, registered,
):
    root, store, _, request = _setup(data_dir, monkeypatch, role=None)
    if not registered:
        store.unregister("private")
    with pytest.raises(HTTPException) as caught:
        projects.create_project(
            projects.CreateProjectRequest(
                project_name="Copied", root_path=str(root / "drawings"),
            ),
            request, store=store, settings=store.settings,
        )
    assert caught.value.status_code == 403
    assert not manifest_path(root / "drawings").exists()
    assert list(store.list_projects()) == (["private"] if registered else [])


def test_owner_can_reimport_their_project(data_dir, monkeypatch):
    root, store, users, request = _setup(data_dir, monkeypatch, role="owner")
    result = projects.create_project(
        projects.CreateProjectRequest(project_name="Renamed", root_path=str(root)),
        request, store=store, settings=store.settings,
    )
    assert result["project_id"] == "private"
    assert load_manifest(root).project_name == "Renamed"
    assert users.project_role("private", "visitor") == "owner"


def test_project_roles_never_override_the_workspace_boundary(data_dir, monkeypatch):
    _, _, users, request = _setup(data_dir, monkeypatch, role="owner", workspace="ws-b")
    problem = access.project_access_problem(users, request.state.user, "private", "viewer")
    assert problem is not None and problem[:2] == (403, "forbidden_project")


def test_import_does_not_register_a_project_when_ownership_cannot_be_saved(data_dir, monkeypatch):
    root, store, users, request = _setup(data_dir, monkeypatch, role="owner")
    store.unregister("private")

    def unavailable(*_args):
        raise UsersDbUnavailable("users database disconnected")

    monkeypatch.setattr(users, "register_project", unavailable)
    with pytest.raises(HTTPException) as caught:
        projects.create_project(
            projects.CreateProjectRequest(project_name="Renamed", root_path=str(root)),
            request, store=store, settings=store.settings,
        )
    assert caught.value.status_code == 503
    assert store.list_projects() == {}
