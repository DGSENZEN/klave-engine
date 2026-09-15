"""El diario de ajustes: subir precios en lote y sustituir un insumo en las
matrices dejan un asiento que se deshace exacto; los básicos se recalculan
después de cada uno."""

import pytest
from klave_engine.common import config as config_module
from klave_engine.costing.catalog_store import CatalogStore, get_catalog_store


@pytest.fixture
def store(data_dir) -> CatalogStore:
    s = get_catalog_store(data_dir)
    s.upsert_insumo("MAT-CEM", description="Cemento gris", unit="TON", resource_type="material",
                    unit_cost=4000.0, source="Cotización 2026", source_type="cotizacion")
    s.upsert_insumo("MAT-CEM2", description="Cemento CPC 30R", unit="TON",
                    resource_type="material", unit_cost=4200.0)
    s.upsert_insumo("MAT-ARENA", description="Arena", unit="M3", resource_type="material",
                    unit_cost=250.0)
    s.upsert_insumo("MO-ALB", description="Albañil", unit="JOR", resource_type="mano_de_obra",
                    unit_cost=700.0)
    s.upsert_insumo("BAS-MORT", description="Mortero 1:4", unit="M3", resource_type="material",
                    unit_cost=1.0, kind="basico")
    s.set_basico_components("BAS-MORT", [("MAT-CEM", 0.3), ("MAT-ARENA", 1.1)])
    s.create_concept(
        code="APL-TEST", description="Aplanado", unit="M2", phase="Acabados",
        production_rate_per_day=15.0,
        components=[("BAS-MORT", 0.025), ("MO-ALB", 0.1), ("MAT-CEM", 0.002)],
    )
    return s


def test_mass_adjustment_is_journaled_and_undone_exactly(store):
    result = store.adjust_prices(["MAT-CEM", "MAT-ARENA"], 4.0, vigencia="2026-10", actor="Diego")
    assert result["adjusted"] == 2 and result["adjustment_id"]
    rows = {i["code"]: i for i in store.list_insumos()}
    assert rows["MAT-CEM"]["unit_cost"] == pytest.approx(4160.0)
    assert rows["MAT-CEM"]["vigencia"] == "2026-10"
    assert rows["MAT-CEM"]["origin"] == "taller" and "ajuste +4 %" in rows["MAT-CEM"]["origin_ref"]
    # El básico que usa el cemento se recalculó.
    assert rows["BAS-MORT"]["unit_cost"] == pytest.approx(0.3 * 4160 + 1.1 * 260)
    journal = store.list_adjustments()
    assert journal[0]["kind"] == "ajuste" and journal[0]["actor"] == "Diego"
    assert journal[0]["rows"] == 2 and journal[0]["params"]["pct"] == 4.0
    undone = store.undo_adjustment(result["adjustment_id"])
    assert undone["restored"] == 2
    rows = {i["code"]: i for i in store.list_insumos()}
    assert rows["MAT-CEM"]["unit_cost"] == 4000.0 and rows["MAT-CEM"]["vigencia"] == ""
    assert rows["MAT-CEM"]["origin_ref"] == ""
    assert rows["BAS-MORT"]["unit_cost"] == pytest.approx(0.3 * 4000 + 1.1 * 250)
    assert store.list_adjustments()[0]["undone_at"]
    with pytest.raises(ValueError, match="ya se deshizo"):
        store.undo_adjustment(result["adjustment_id"])


def test_adjustment_by_filter_and_bad_input(store):
    result = store.adjust_prices(None, -10.0, resource_type="mano_de_obra", actor="Diego")
    assert result["adjusted"] >= 1
    assert next(i for i in store.list_insumos() if i["code"] == "MO-ALB")["unit_cost"] == 630.0
    with pytest.raises(ValueError, match="porcentaje"):
        store.adjust_prices(["MAT-CEM"], -100.0)
    with pytest.raises(ValueError, match="Ningún insumo"):
        store.adjust_prices(["NO-EXISTE"], 3.0)


def test_replace_resource_moves_components_merges_and_undoes(store):
    result = store.replace_resource("MAT-CEM", "MAT-CEM2", actor="Diego")
    assert sorted(result["affected"]) == ["APL-TEST", "BAS-MORT"]
    templates = store.load_templates()
    apl = dict(templates["APL-TEST"])
    assert apl["MAT-CEM2"] == 0.002 and "MAT-CEM" not in apl
    assert dict(templates["BAS-MORT"])["MAT-CEM2"] == 0.3
    mortero = next(i for i in store.list_insumos() if i["code"] == "BAS-MORT")
    assert mortero["unit_cost"] == pytest.approx(0.3 * 4200 + 1.1 * 250)
    # Sustituir hacia un insumo que ya está en la matriz suma las cantidades.
    store.set_apu_components("APL-TEST", [("MAT-CEM2", 0.002), ("MAT-CEM", 0.003), ("MO-ALB", 0.1)])
    merged = store.replace_resource("MAT-CEM", "MAT-CEM2", concept_codes=["APL-TEST"])
    assert merged["affected"] == ["APL-TEST"]
    assert dict(store.load_templates()["APL-TEST"])["MAT-CEM2"] == pytest.approx(0.005)
    undone = store.undo_adjustment(merged["adjustment_id"])
    assert undone["restored"] == 1
    after = dict(store.load_templates()["APL-TEST"])
    assert after["MAT-CEM2"] == 0.002 and after["MAT-CEM"] == 0.003
    with pytest.raises(ValueError, match="mismo insumo"):
        store.replace_resource("MAT-CEM", "MAT-CEM")
    with pytest.raises(ValueError, match="no existe"):
        store.replace_resource("MAT-CEM", "NO-EXISTE")


def _api(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    config_module.get_settings.cache_clear()
    return TestClient(create_app())


def test_adjustment_endpoints(store, monkeypatch):
    client = _api(monkeypatch)
    uses = client.get("/catalog/insumos/MAT-CEM/uso").json()
    assert uses["concepts"][0]["code"] == "APL-TEST" and uses["basicos"][0]["code"] == "BAS-MORT"
    adjusted = client.post(
        "/catalog/insumos/ajuste", json={"codes": ["MAT-CEM"], "pct": 5, "vigencia": "2026-10"},
        headers={"X-Actor": "Diego"},
    )
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()["adjusted"] == 1
    journal = client.get("/catalog/insumos/ajustes").json()["adjustments"]
    assert journal[0]["kind"] == "ajuste"
    replaced = client.post(
        "/catalog/insumos/MAT-CEM/sustituir", json={"replacement": "MAT-CEM2"},
        headers={"X-Actor": "Diego"},
    )
    assert replaced.status_code == 200, replaced.text
    assert sorted(replaced.json()["affected"]) == ["APL-TEST", "BAS-MORT"]
    undone = client.delete(f"/catalog/insumos/ajustes/{replaced.json()['adjustment_id']}")
    assert undone.status_code == 200 and undone.json()["restored"] == 2
    bad = client.post("/catalog/insumos/ajuste", json={"codes": ["MAT-CEM"], "pct": -100})
    assert bad.status_code == 422
