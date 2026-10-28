"""La obra de ejemplo no escribe en los datos del taller: su catálogo es suyo,
no deja etiquetas para el lector, no guarda índices y no se lee con IA."""

from klave_engine.common.config import get_settings
from klave_engine.costing import catalog_store as catalog_store_module
from klave_engine.costing.catalog_store import drop_catalog_store, get_catalog_store
from klave_engine.costing.etiquetas import LABELS_FILENAME, append_labels
from klave_engine.costing.recompute import apply_taller_history

from apps.api.tenancy import store_for_project


def test_sample_project_gets_its_own_catalog(data_dir):
    settings = get_settings()
    office = store_for_project(settings, "marina")
    sample = store_for_project(settings, "obra_de_ejemplo_local")
    assert sample.db_path != office.db_path
    assert sample.db_path.name == "obra_de_ejemplo_local.db"


def test_labels_are_not_written_for_samples(tmp_path):
    control = tmp_path / "uploads" / "obra_de_ejemplo_local" / "processed"
    assert append_labels(control, [{"x": 1}]) == 0
    assert not (control / LABELS_FILENAME).exists()


def test_labels_still_written_for_real_projects(tmp_path):
    control = tmp_path / "uploads" / "marina" / "processed"
    assert append_labels(control, [{"x": 1}]) == 1


class _Indicadores:
    """Lo mínimo de un CostReport para apply_taller_history."""

    def __init__(self):
        from types import SimpleNamespace

        self.indicators = [SimpleNamespace(key="x", value=1.0)]
        self.boq = SimpleNamespace(units_reliable=True)


def test_taller_history_skips_samples(data_dir, monkeypatch):
    store = get_catalog_store(data_dir, workspace_id="t")
    saved = []
    monkeypatch.setattr(store, "save_project_indices", lambda pid, v: saved.append(pid))
    monkeypatch.setattr(store, "load_project_indices", lambda pid: [])
    monkeypatch.setattr(
        "klave_engine.costing.indicadores.con_historia", lambda indicadores, historia: indicadores
    )
    monkeypatch.setattr("klave_engine.costing.indicadores.valores_de", lambda indicadores: {})
    apply_taller_history(_Indicadores(), store, "obra_de_ejemplo_local")
    apply_taller_history(_Indicadores(), store, "marina")
    assert saved == ["marina"]


def test_ai_read_refuses_samples(data_dir):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    response = TestClient(create_app()).post("/projects/obra_de_ejemplo_local/ai-read")
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["error_type"] == "sample_project"


def test_drop_catalog_store_removes_file_and_cache(data_dir):
    store = get_catalog_store(data_dir, workspace_id="obra_de_ejemplo_local")
    store.list_insumos()
    assert store.db_path.exists()
    drop_catalog_store(data_dir, "obra_de_ejemplo_local")
    assert not store.db_path.exists()
    assert store.db_path.resolve() not in catalog_store_module._STORES
    fresh = get_catalog_store(data_dir, workspace_id="obra_de_ejemplo_local")
    assert fresh is not store


def test_variant_picker_lists_the_project_catalog_concepts(data_dir, monkeypatch):
    """El selector de «Tu catálogo» lee del mismo catálogo donde se guarda el
    mapeo: en la obra de ejemplo, el suyo (con las claves del taller ficticio)."""
    from fastapi.testclient import TestClient

    from apps.api import jobs as jobs_module
    from apps.api.main import create_app
    from apps.api.routes import projects as projects_module
    from apps.api.routes import variantes as variantes_module

    fake = jobs_module.Job(project_id="x", job_id="j", run_id="r")
    monkeypatch.setattr(projects_module.JOB_STORE, "enqueue", lambda *_a, **_k: (fake, True))
    monkeypatch.setattr(variantes_module, "_report", lambda *_a: _SinRenglones())
    client = TestClient(create_app())
    project_id = client.post("/projects/demo", json={}).json()["project_id"]
    body = client.get(f"/projects/{project_id}/variantes").json()
    codes = {c["code"] for c in body["conceptos"]}
    assert {"E-COL-3040", "E-COL-4040", "E-TRB-3050", "E-TRB-3060"} <= codes
    assert all(set(c) == {"code", "description", "unit"} for c in body["conceptos"])


class _SinRenglones:
    class boq:  # noqa: N801 — imita report.boq
        lines: list = []


def _cliente_con_obra(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api import jobs as jobs_module
    from apps.api.main import create_app
    from apps.api.routes import projects as projects_module

    fake = jobs_module.Job(project_id="x", job_id="j", run_id="r")
    monkeypatch.setattr(projects_module.JOB_STORE, "enqueue", lambda *_a, **_k: (fake, True))
    client = TestClient(create_app())
    return client, client.post("/projects/demo", json={}).json()["project_id"]


def test_an_alias_made_on_the_sample_stays_in_its_catalog(data_dir, monkeypatch):
    """«Elegir de mi catálogo» en la obra de ejemplo no escribe en el taller."""
    client, project_id = _cliente_con_obra(monkeypatch)
    response = client.post("/catalog/aliases", json={
        "concept_code": "EST-001", "kind": "concept", "target_code": "E-COL-4040",
        "project_id": project_id,
    })
    assert response.status_code == 201, response.text
    office = get_catalog_store(data_dir)
    sample = store_for_project(get_settings(), project_id)
    assert "EST-001" not in office.load_concept_aliases()
    assert "EST-001" in sample.load_concept_aliases()


def test_the_sample_mapping_offers_no_office_references(data_dir, monkeypatch):
    from apps.api.routes import variantes as variantes_module

    client, project_id = _cliente_con_obra(monkeypatch)
    monkeypatch.setattr(variantes_module, "_report", lambda *_a: _SinRenglones())
    assert client.get(f"/projects/{project_id}/variantes").json()["referencias"] is False
