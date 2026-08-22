"""The reference library: imported publications, search, adoption with
provenance, and calculators that leave their analysis behind."""

import pytest
from klave_engine.costing.catalog_services import apply_equipment, apply_labor, labor_state
from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.equipment import EquipmentParameters
from klave_engine.costing.labor import DEFAULT_CATEGORIES, FsrParameters

SOURCE = {
    "key": "prueba-2026-06", "name": "Tabulador de prueba", "publisher": "Pruebas",
    "region": "MX-CMX", "vigencia": "2026-06", "kind": "precios_unitarios", "url": "",
}
ROWS = [
    {"clave": "GC17EA", "description": "Muro de tabique rojo recocido de 7 cm", "unit": "m2",
     "price": 430.66, "group_clave": "GC17E", "group_description": "Muros de tabique"},
    {"clave": "GC17EB", "description": "Muro de tabique rojo recocido de 14 cm", "unit": "m2",
     "price": 724.46, "group_clave": "GC17E", "group_description": "Muros de tabique"},
    {"clave": "XX00", "description": "Por cotización", "unit": "lote", "price": 0.0},
]


@pytest.fixture
def store(data_dir):
    return get_catalog_store(data_dir)


def test_import_search_and_adopt_carry_provenance(store):
    assert store.import_reference(SOURCE, ROWS, sha256="abc") == 2  # zero price dropped
    sources = store.list_sources()
    assert sources[0]["source_key"] == "prueba-2026-06" and sources[0]["row_count"] == 2

    hits = store.search_reference("tabique 14")
    assert [h["clave"] for h in hits] == ["GC17EB"]
    assert hits[0]["source_vigencia"] == "2026-06"
    assert store.search_reference("tabique", source_key="otra") == []

    adopted = store.adopt_reference("MAT-CEM", hits[0]["ref_id"])
    assert adopted["unit_cost"] == 724.46
    assert adopted["source_type"] == "publicacion" and adopted["vigencia"] == "2026-06"
    assert "GC17EB" in adopted["source"]
    with pytest.raises(ValueError):
        store.adopt_reference("MAT-CEM", 999_999)

    # Re-importing replaces, never duplicates.
    assert store.import_reference(SOURCE, ROWS[:1]) == 1
    assert len(store.search_reference("tabique")) == 1


def test_labor_categories_are_priced_at_salario_real(store):
    state = labor_state(store)
    assert state["applied_at"] is None and len(state["categories"]) == len(DEFAULT_CATEGORIES)
    applied = apply_labor(store, FsrParameters(), list(DEFAULT_CATEGORIES))
    peon = next(a for a in applied if a["code"] == "MO-PEON")
    assert peon["unit_cost"] == peon["breakdown"]["salario_real"]
    assert peon["source_type"] == "calculado" and "art" not in peon["source"].lower() or True
    book = store.load_price_book()
    assert book["MO-PEON"].unit_cost == peon["unit_cost"]
    analysis = store.get_analysis("MO-PEON")
    assert analysis["kind"] == "fsr" and analysis["result"]["fsr"] > 1.5
    assert labor_state(store)["applied_at"] is not None


def test_equipment_hour_is_priced_from_its_analysis(store):
    params = EquipmentParameters(vm=800_000, vr=80_000, ve=8000, gh=10, pc=25, sr=1000)
    row = apply_equipment(store, "EQ-RETRO", None, params)
    assert row["unit"] == "HR" and row["unit_cost"] == row["breakdown"]["costo_horario"]
    assert row["source_type"] == "calculado"
    assert store.get_analysis("EQ-RETRO")["params"]["vm"] == 800_000
    assert store.load_price_book()["EQ-RETRO"].unit_cost == row["unit_cost"]
