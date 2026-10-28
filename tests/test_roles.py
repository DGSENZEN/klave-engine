"""Quién puede cambiar qué: el catálogo es del administrador del taller; los
alias y los mapeos de variantes se agregan en revisión y se cambian o se
quitan con un administrador. Ver docs/superpowers/specs/2026-10-23-role-enforcement-design.md."""

import pytest
from fastapi import HTTPException
from klave_engine.ejemplo import SAMPLE_PREFIX
from starlette.requests import Request

from apps.api.auth import access

EJEMPLO = f"{SAMPLE_PREFIX}_ws-a_ana"


class Usuarios:
    """La base de usuarios en memoria: Admin administra el taller; en el proyecto
    de prueba Olga es propietaria, Ana editora y Beto lector."""

    last_known_has_users = True

    def __init__(self, pid: str = "obra"):
        self.pid = pid
        self.usuarios = {
            quien: {"user_id": quien, "name": quien.capitalize(), "status": "active",
                    "role": "admin" if quien == "admin" else "member", "workspace_id": "ws-a"}
            for quien in ("admin", "olga", "ana", "beto")
        }  # fmt: skip
        self.roles = {"olga": "owner", "ana": "editor", "beto": "viewer"}
        self.auditoria: list[dict] = []

    def has_users(self):
        return True

    def get_session_user(self, token):
        user = self.usuarios.get(token or "")
        return dict(user) if user else None

    def project_workspace_id(self, project_id):
        return "ws-a"

    def default_workspace(self):
        return {"workspace_id": "ws-a"}

    def project_role(self, project_id, user_id):
        # Same grants on the real obra and on the example obra (the sandbox).
        return self.roles.get(user_id) if project_id in (self.pid, EJEMPLO) else None

    def record_audit(self, **entry):
        self.auditoria.append(entry)


def peticion(user: dict | None) -> Request:
    return Request({"type": "http", "headers": [], "state": {"user": user}})


@pytest.fixture
def usuarios(monkeypatch):
    store = Usuarios()
    monkeypatch.setattr(access, "get_user_store", lambda _url: store)
    return store


def test_require_taller_admin_open_mode_passes():
    access.require_taller_admin(peticion(None))


def test_require_taller_admin_member_403(usuarios):
    with pytest.raises(HTTPException) as exc:
        access.require_taller_admin(peticion(usuarios.usuarios["ana"]))
    assert exc.value.status_code == 403
    assert exc.value.detail["error_type"] == "admin_required"
    assert exc.value.detail["message"] == access.CATALOG_ADMIN_MESSAGE


def test_require_taller_admin_admin_passes(usuarios):
    access.require_taller_admin(peticion(usuarios.usuarios["admin"]))


def test_is_taller_admin(usuarios):
    assert access.is_taller_admin(peticion(usuarios.usuarios["admin"])) is True
    assert access.is_taller_admin(peticion(usuarios.usuarios["olga"])) is False
    assert access.is_taller_admin(peticion(None)) is False


def test_viewer_project_role_matches_tablero(usuarios):
    assert access.viewer_project_role(peticion(usuarios.usuarios["admin"]), "obra") == "admin"
    assert access.viewer_project_role(peticion(usuarios.usuarios["ana"]), "obra") == "editor"
    assert access.viewer_project_role(peticion(usuarios.usuarios["beto"]), "otra") is None
    assert access.viewer_project_role(peticion(None), "obra") is None


# ---------------------------------------------------------------- catálogo --

# One write per category of decision 1 (and the two validations, which persist
# their verdict). The rule answers before the body is read, so bodies are empty.
CATALOGO_ESCRITURAS = [
    ("post", "/catalog/insumos"),
    ("put", "/catalog/insumos/MAT-001"),
    ("put", "/catalog/apus/EST-001"),
    ("put", "/catalog/rendimientos/EST-001"),
    ("post", "/catalog/concepts"),
    ("put", "/catalog/concepts/EST-001"),
    ("post", "/catalog/concepts/EST-001/generar"),
    ("post", "/catalog/concepts/EST-001/validar"),
    ("post", "/catalog/matrices/validar"),
    ("post", "/catalog/concepts/EST-001/adopt"),
    ("delete", "/catalog/concepts/EST-001/price"),
    ("post", "/catalog/sources/custom"),
    ("post", "/catalog/import-prices"),
    ("put", "/catalog/labor"),
    ("put", "/catalog/equipment/EQ-001"),
    ("put", "/catalog/indices"),
    ("post", "/catalog/plantillas"),
    ("post", "/catalog/parametrics"),
    ("post", "/catalog/inventory-mappings"),
]


@pytest.fixture
def api(data_dir, monkeypatch):
    """La app completa con la base de usuarios en memoria."""
    from fastapi.testclient import TestClient

    from apps.api.auth import middleware
    from apps.api.main import create_app

    store = Usuarios()
    from apps.api import tenancy

    monkeypatch.setattr(middleware, "get_user_store", lambda _url: store)
    monkeypatch.setattr(access, "get_user_store", lambda _url: store)
    monkeypatch.setattr(tenancy, "get_user_store", lambda _url: store)
    client = TestClient(create_app())

    def como(quien):
        client.cookies.clear()
        if quien:
            client.cookies.set(middleware.SESSION_COOKIE, quien)
        return client

    return como, store


def _catalogo_del_taller():
    from klave_engine.common.config import get_settings

    from apps.api.tenancy import workspace_store

    catalog = workspace_store(get_settings(), "ws-a")
    return (
        catalog.load_concepts(include_inactive=True),
        catalog.load_price_book(),
        catalog.load_concept_aliases(),
    )


@pytest.mark.parametrize(("metodo", "ruta"), CATALOGO_ESCRITURAS)
def test_member_cannot_write_catalog(api, metodo, ruta):
    como, _ = api
    antes = _catalogo_del_taller()
    r = getattr(como("ana"), metodo)(ruta)
    assert r.status_code == 403, (ruta, r.status_code, r.text)
    assert r.json()["detail"]["error_type"] == "admin_required"
    assert _catalogo_del_taller() == antes


@pytest.mark.parametrize(("metodo", "ruta"), CATALOGO_ESCRITURAS)
def test_admin_passes_the_catalog_rule(api, metodo, ruta):
    como, _ = api
    r = getattr(como("admin"), metodo)(ruta)
    assert r.status_code not in (401, 403), (ruta, r.status_code, r.text)


def test_preview_is_open_to_members(api):
    como, _ = api
    r = como("ana").post("/catalog/labor/preview")
    assert r.status_code not in (401, 403), r.text


def test_open_mode_writes_catalog(data_dir):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    r = TestClient(create_app()).put("/catalog/indices")
    assert r.status_code not in (401, 403), r.text


def test_users_db_down_does_not_open_catalog(api, monkeypatch):
    from apps.api.auth.store import UsersDbUnavailable

    como, store = api

    def caida(*_a, **_k):
        raise UsersDbUnavailable("caída")

    antes = _catalogo_del_taller()
    with monkeypatch.context() as caido:
        caido.setattr(store, "has_users", caida)
        r = como("ana").put("/catalog/indices", json={})
    assert r.status_code == 503
    assert _catalogo_del_taller() == antes


# ------------------------------------------------------------------- alias --


def _alias(codigo, destino, proyecto="obra"):
    return {"concept_code": codigo, "kind": "concept", "target_code": destino,
            "project_id": proyecto}  # fmt: skip


def _alias_actual(codigo, proyecto=None):
    from klave_engine.common.config import get_settings

    from apps.api.tenancy import store_for_project, workspace_store

    settings = get_settings()
    catalog = (
        store_for_project(settings, proyecto) if proyecto else workspace_store(settings, "ws-a")
    )
    fila = catalog.load_concept_aliases().get(codigo)
    return fila and fila["target_code"]


def test_editor_adds_new_alias(api):
    como, store = api
    r = como("ana").post("/catalog/aliases", json=_alias("CIM-001", "CIM-002"))
    assert r.status_code == 201, r.text
    assert _alias_actual("CIM-001") == "CIM-002"
    assert [e["action"] for e in store.auditoria] == ["alias_added"]


def test_editor_cannot_repoint_alias(api):
    como, store = api
    assert como("admin").post("/catalog/aliases", json=_alias("CIM-001", "CIM-002")).status_code == 201
    r = como("ana").post("/catalog/aliases", json=_alias("CIM-001", "CIM-007"))
    assert r.status_code == 403, r.text
    detail = r.json()["detail"]
    assert detail["error_type"] == "admin_required"
    assert detail["cambios"][0]["concept_code"] == "CIM-001"
    assert detail["cambios"][0]["actual"]["target_code"] == "CIM-002"
    assert _alias_actual("CIM-001") == "CIM-002"


def test_editor_resends_same_alias_is_noop(api):
    como, store = api
    assert como("ana").post("/catalog/aliases", json=_alias("CIM-001", "CIM-002")).status_code == 201
    store.auditoria.clear()
    r = como("ana").post("/catalog/aliases", json=_alias("CIM-001", "CIM-002"))
    assert r.status_code == 201, r.text
    assert store.auditoria == []


def test_bulk_mixed_is_all_or_nothing(api):
    como, _ = api
    assert como("admin").post("/catalog/aliases", json=_alias("CIM-001", "CIM-002")).status_code == 201
    body = {"project_id": "obra", "items": [
        _alias("CIM-004", "CIM-002"), _alias("CIM-007", "CIM-002"), _alias("CIM-001", "CIM-007"),
    ]}  # fmt: skip
    r = como("ana").post("/catalog/aliases/bulk", json=body)
    assert r.status_code == 403, r.text
    assert [c["concept_code"] for c in r.json()["detail"]["cambios"]] == ["CIM-001"]
    assert _alias_actual("CIM-004") is None and _alias_actual("CIM-007") is None
    assert _alias_actual("CIM-001") == "CIM-002"


def test_editor_cannot_clear_taller_alias(api):
    como, _ = api
    assert como("admin").post("/catalog/aliases", json=_alias("CIM-001", "CIM-002")).status_code == 201
    r = como("ana").delete("/catalog/aliases/CIM-001", params={"project_id": "obra"})
    assert r.status_code == 403
    assert r.json()["detail"]["error_type"] == "admin_required"
    assert _alias_actual("CIM-001") == "CIM-002"


def test_admin_repoints_and_clears(api):
    como, store = api
    assert como("admin").post("/catalog/aliases", json=_alias("CIM-001", "CIM-002")).status_code == 201
    assert como("admin").post("/catalog/aliases", json=_alias("CIM-001", "CIM-007")).status_code == 201
    assert _alias_actual("CIM-001") == "CIM-007"
    r = como("admin").delete("/catalog/aliases/CIM-001", params={"project_id": "obra"})
    assert r.status_code == 200, r.text
    assert _alias_actual("CIM-001") is None
    assert [e["action"] for e in store.auditoria] == ["alias_added", "alias_changed", "alias_cleared"]


def test_example_obra_editor_can_repoint_and_clear(api):
    como, store = api
    ana = como("ana")
    assert ana.post("/catalog/aliases", json=_alias("CIM-001", "CIM-002", EJEMPLO)).status_code == 201
    assert ana.post("/catalog/aliases", json=_alias("CIM-001", "CIM-007", EJEMPLO)).status_code == 201
    assert _alias_actual("CIM-001", EJEMPLO) == "CIM-007"
    r = ana.delete("/catalog/aliases/CIM-001", params={"project_id": EJEMPLO})
    assert r.status_code == 200, r.text
    assert _alias_actual("CIM-001") is None  # the office never saw it
    assert store.auditoria == []


def test_each_taller_alias_write_audits_once(api):
    como, store = api
    body = {"project_id": "obra", "items": [_alias("CIM-004", "CIM-002"), _alias("CIM-007", "CIM-002")]}
    assert como("ana").post("/catalog/aliases/bulk", json=body).status_code == 201
    assert sorted(e["target_id"] for e in store.auditoria) == ["CIM-004", "CIM-007"]
    assert all(e["action"] == "alias_added" for e in store.auditoria)
    assert store.auditoria[0]["detail"]["project_id"] == "obra"
