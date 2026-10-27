"""La obra de ejemplo: el primer botón que ve un taller vacío tiene que abrir
una obra, no un error. Se crea una vez por persona y se procesa como trabajo."""

from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from klave_engine.common import config as config_module
from klave_engine.common.config import get_settings
from klave_engine.ejemplo import sample_project_id

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
    assert info["project_name"] == "Obra de ejemplo"
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


# --- Recorrido guiado: una obra de ejemplo por persona, privada ------------------


def _request_user(workspace, user_id, role="member"):
    return Request({
        "type": "http", "headers": [], "client": ("127.0.0.1", 1),
        "state": {"user": {"user_id": user_id, "workspace_id": workspace, "role": role}},
    })


def _patch_users(monkeypatch, users):
    for module in (projects_module, access, tenancy):
        monkeypatch.setattr(module, "get_user_store", lambda _url: users)


def test_two_people_in_one_workspace_get_two_samples(data_dir, monkeypatch):
    settings = get_settings()
    store = ProjectStore(settings)
    users = _Users()
    _patch_users(monkeypatch, users)
    _fake_enqueue(monkeypatch)
    ana = projects_module.create_demo_project(
        _request_user("ws-1", "u-ana"), store=store, settings=settings
    )
    beto = projects_module.create_demo_project(
        _request_user("ws-1", "u-beto"), store=store, settings=settings
    )
    assert ana["project_id"] != beto["project_id"]
    assert ana["project_id"] == sample_project_id("ws-1", "u-ana")


def test_fresh_sample_is_the_teaching_obra_with_teaching_prices(data_dir, monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    _fake_enqueue(monkeypatch)
    client = TestClient(create_app())
    body = client.post("/projects/demo", json={}).json()
    project_id = body["project_id"]
    assert project_id == "obra_de_ejemplo_local"
    info = client.get(f"/projects/{project_id}").json()
    assert info["project_name"] == "Obra de ejemplo"
    drawings = sorted(p.name for p in (data_dir / "uploads" / project_id / "drawings").iterdir())
    assert drawings == ["S-101 Cimentacion.dxf", "S-201 Estructura.dxf"]
    catalog = tenancy.store_for_project(get_settings(), project_id)
    priced = {row["code"] for row in catalog.list_insumos() if row.get("unit_cost")}
    assert {"MAT-CONC250", "MAT-ACERO", "MO-CUAD-FIE"} <= priced


def test_a_processed_sample_is_not_processed_again(data_dir, monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    calls = _fake_enqueue(monkeypatch)
    client = TestClient(create_app())
    client.post("/projects/demo", json={})
    monkeypatch.setattr(
        projects_module.JOB_STORE, "get",
        lambda *_a, **_k: jobs_module.Job(
            project_id="x", job_id="j", run_id="r", state="processed"
        ),
    )
    monkeypatch.setattr(projects_module, "_ya_procesada", lambda *_a: True)
    again = client.post("/projects/demo", json={}).json()
    assert again["fresh"] is False and again["job_id"] is None
    assert len(calls) == 1


def test_sample_is_private_even_to_admins(data_dir, monkeypatch):
    settings = get_settings()
    store = ProjectStore(settings)
    users = _Users()
    users.project_workspace_map = lambda: {}
    users.project_ids_for_user = lambda _uid: set()
    _patch_users(monkeypatch, users)
    own = sample_project_id("ws-a", "u-admin")
    other = sample_project_id("ws-a", "u-ana")
    keep = projects_module.visible_project_filter(_request_user("ws-a", "u-admin", "admin"), store)
    assert keep(own) is True
    assert keep(other) is False


def test_open_mode_sees_its_sample(data_dir):
    store = ProjectStore(get_settings())
    request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1), "state": {}})
    assert projects_module.visible_project_filter(request, store)("obra_de_ejemplo_local")


def test_overview_counters_ignore_samples_and_onboarding_is_gone(data_dir, monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    _fake_enqueue(monkeypatch)
    client = TestClient(create_app())
    client.post("/projects/demo", json={})
    body = client.get("/workspace/overview").json()
    assert "onboarding" not in body
    assert [p["project_id"] for p in body["projects"]] == ["obra_de_ejemplo_local"]
    attention = body["attention"]
    assert attention["processing"] == 0 and attention["unverified"] == 0
    assert attention["failed"] == 0 and attention["stale_runs"] == 0


# --- Reiniciar la obra y cargar su Rev B -------------------------------------------


def _cliente_con_obra(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    calls = _fake_enqueue(monkeypatch)
    client = TestClient(create_app())
    project_id = client.post("/projects/demo", json={}).json()["project_id"]
    return client, project_id, calls


def _hojas(root):
    return {p.name: p.read_bytes() for p in sorted((root / "drawings").glob("*.dxf"))}


def _referencia(tmp_path, revision):
    from klave_engine.ejemplo.obra import build_obra_ejemplo

    ref = tmp_path / f"ref_{revision}"
    build_obra_ejemplo(ref, "A")
    if revision == "B":
        build_obra_ejemplo(ref, "B")
    return {k: len(v) for k, v in _hojas(ref).items()}


def test_reset_restores_rev_a_and_clears_reviews(data_dir, monkeypatch, tmp_path):
    client, project_id, calls = _cliente_con_obra(monkeypatch)
    root = data_dir / "uploads" / project_id
    from klave_engine.ejemplo.obra import build_obra_ejemplo

    build_obra_ejemplo(root, "B")
    (root / "processed" / "reviews.json").write_text("{}")
    catalog = tenancy.store_for_project(get_settings(), project_id)
    catalog.upsert_insumo("MAT-ACERO", unit_cost=1.0)

    response = client.post(f"/projects/{project_id}/demo/reiniciar")
    assert response.status_code == 202, response.text
    assert response.json()["project_id"] == project_id
    assert {k: len(v) for k, v in _hojas(root).items()} == _referencia(tmp_path, "A")
    assert not (root / "processed" / "reviews.json").exists()
    fresh = tenancy.store_for_project(get_settings(), project_id)
    acero = next(r for r in fresh.list_insumos() if r["code"] == "MAT-ACERO")
    assert acero["unit_cost"] == 24500.0
    assert len(calls) == 2


def test_reset_refused_while_processing(data_dir, monkeypatch):
    client, project_id, _ = _cliente_con_obra(monkeypatch)
    root = data_dir / "uploads" / project_id
    antes = _hojas(root)
    monkeypatch.setattr(
        projects_module.JOB_STORE, "get",
        lambda *_a, **_k: jobs_module.Job(
            project_id=project_id, job_id="j", run_id="r", state="running"
        ),
    )
    for ruta in ("reiniciar", "revision-b"):
        response = client.post(f"/projects/{project_id}/demo/{ruta}")
        assert response.status_code == 409
        assert response.json()["detail"]["error_type"] == "sample_busy"
    assert _hojas(root) == antes


def test_rev_b_rewrites_sheets_and_enqueues(data_dir, monkeypatch, tmp_path):
    client, project_id, calls = _cliente_con_obra(monkeypatch)
    response = client.post(f"/projects/{project_id}/demo/revision-b")
    assert response.status_code == 202, response.text
    root = data_dir / "uploads" / project_id
    assert {k: len(v) for k, v in _hojas(root).items()} == _referencia(tmp_path, "B")
    assert len(calls) == 2


def test_demo_routes_refuse_real_projects(data_dir, monkeypatch):
    client, _, _ = _cliente_con_obra(monkeypatch)
    assert client.post("/projects/marina/demo/reiniciar").status_code == 404
    assert client.post("/projects/marina/demo/revision-b").status_code == 404


def test_demo_routes_need_the_owner():
    assert _required_project_role(["projects", "obra_x", "demo", "reiniciar"], "POST") == "owner"
    assert _required_project_role(["projects", "obra_x", "demo", "revision-b"], "POST") == "owner"


def test_reset_route_restarts_the_tour_progress(data_dir, monkeypatch):
    settings = get_settings()
    store = ProjectStore(settings)
    users = _Users()
    reinicios = []
    users.reiniciar_recorrido = reinicios.append
    _patch_users(monkeypatch, users)
    _fake_enqueue(monkeypatch)
    request = _request_user("ws-1", "u-ana")
    project_id = projects_module.create_demo_project(request, store=store, settings=settings)[
        "project_id"
    ]
    projects_module.reiniciar_obra_de_ejemplo(project_id, request, store=store, settings=settings)
    assert reinicios == ["u-ana"]


# --- Revisión final: la obra de ejemplo se reconoce por su id exacto ---------------


def test_an_upload_named_like_the_sample_never_gets_the_sample_prefix(data_dir, monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    _fake_enqueue(monkeypatch)
    client = TestClient(create_app())
    dxf = (Path(__file__).resolve().parents[1] / "apps/web/e2e/fixtures/structural-meters.dxf")
    response = client.post(
        "/projects/upload",
        files=[("files", ("plano.dxf", dxf.read_bytes(), "application/dxf"))],
        data={"project_name": "Obra de ejemplo – Torre 2"},
    )
    assert response.status_code in (200, 201, 202), response.text
    project_id = response.json()["project_id"]
    assert not project_id.startswith("obra_de_ejemplo")


def test_reset_and_rev_b_only_touch_the_callers_own_sample(data_dir, monkeypatch):
    settings = get_settings()
    store = ProjectStore(settings)
    users = _Users()
    users.reiniciar_recorrido = lambda _uid: None
    _patch_users(monkeypatch, users)
    _fake_enqueue(monkeypatch)
    ana = _request_user("ws-1", "u-ana")
    beto = _request_user("ws-1", "u-beto", role="admin")
    project_id = projects_module.create_demo_project(ana, store=store, settings=settings)[
        "project_id"
    ]
    for route in (projects_module.reiniciar_obra_de_ejemplo, projects_module.cargar_revision_b):
        with pytest.raises(HTTPException) as caught:
            route(project_id, beto, store=store, settings=settings)
        assert caught.value.status_code == 404
    # A real project whose id happens to carry the prefix is never treated as a sample.
    root = data_dir / "uploads" / "obra_de_ejemplo_torre_2_ab12cd"
    (root / "drawings").mkdir(parents=True)
    (root / "drawings" / "x.dxf").write_text("0\nEOF\n")
    store.register("obra_de_ejemplo_torre_2_ab12cd", root)
    with pytest.raises(HTTPException) as caught:
        projects_module.reiniciar_obra_de_ejemplo(
            "obra_de_ejemplo_torre_2_ab12cd", ana, store=store, settings=settings
        )
    assert caught.value.status_code == 404
    assert (root / "drawings" / "x.dxf").exists()


def test_creating_the_sample_while_it_processes_does_not_touch_its_files(data_dir, monkeypatch):
    client, project_id, calls = _cliente_con_obra(monkeypatch)
    from klave_engine.ingestion.manifest import manifest_path

    root = data_dir / "uploads" / project_id
    path = manifest_path(root, get_settings().processed_dir_name)
    manifest = path.read_bytes()
    monkeypatch.setattr(
        projects_module.JOB_STORE, "get",
        lambda *_a, **_k: jobs_module.Job(
            project_id=project_id, job_id="j-vivo", run_id="r", state="running"
        ),
    )
    body = client.post("/projects/demo", json={}).json()
    assert body["job_id"] == "j-vivo" and body["fresh"] is False
    assert path.read_bytes() == manifest
    assert len(calls) == 1
