"""Workspace catalog: seeding, edits, imports, and the APU equations."""

import pytest
from klave_engine.costing.apu import build_apu
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.catalog_store import SEED_SOURCE, get_catalog_store
from klave_engine.costing.insumos import APU_TEMPLATES, RESOURCES
from klave_engine.costing.models import CostingAssumptions


@pytest.fixture
def store(data_dir):
    return get_catalog_store(data_dir)


def test_seeds_reference_data_once(store):
    book = store.load_price_book()
    # Core seven-concept resources plus the widened v2 reference basket.
    assert set(RESOURCES) <= set(book)
    assert all(row["source"] == SEED_SOURCE for row in store.list_insumos())
    assert all(row["source_type"] == "referencia" for row in store.list_insumos())
    assert set(APU_TEMPLATES) <= set(store.load_templates())
    # Every built-in concept exists in the concepts table with a rule key;
    # v2 manual concepts exist without one.
    concepts = {row["code"]: row for row in store.load_concepts()}
    for builtin in build_default_catalog(CostingAssumptions()):
        expected = builtin.code if builtin.rule is not None else None
        assert concepts[builtin.code]["rule_key"] == expected
    assert concepts["CIM-003"]["rule_key"] is None  # plantilla: derived, not detected
    rendimientos = store.load_rendimientos()
    assert {c.code for c in build_default_catalog(CostingAssumptions())} <= set(rendimientos)


def test_price_update_keeps_structure_and_provenance(store):
    store.upsert_insumo("MAT-CONC250", unit_cost=2790.0, source="Cotización X")
    book = store.load_price_book()
    assert book["MAT-CONC250"].unit_cost == 2790.0
    row = next(r for r in store.list_insumos() if r["code"] == "MAT-CONC250")
    assert row["source"] == "Cotización X"
    # Other fields survive the partial update.
    assert book["MAT-CONC250"].unit == "M3"


def test_create_requires_full_fields(store):
    with pytest.raises(ValueError):
        store.upsert_insumo("MAT-NUEVO", unit_cost=100.0)
    store.upsert_insumo(
        "MAT-NUEVO",
        description="Material nuevo",
        unit="PZA",
        resource_type="material",
        unit_cost=100.0,
        source="Prueba",
    )
    assert "MAT-NUEVO" in store.load_price_book()


def test_apu_matrix_validation(store):
    with pytest.raises(ValueError):
        store.set_apu_components("EST-001", [])
    with pytest.raises(ValueError):
        store.set_apu_components("EST-001", [("NO-EXISTE", 1.0)])
    with pytest.raises(ValueError):
        store.set_apu_components("EST-001", [("MO-PEON", -1.0)])
    store.set_apu_components("EST-001", [("MO-PEON", 0.5), ("EQ-HERRAMIENTA", 1.0)])
    assert store.load_templates()["EST-001"] == [("EQ-HERRAMIENTA", 1.0), ("MO-PEON", 0.5)]


def test_import_prices_updates_only_existing(store):
    result = store.import_prices(
        [
            {"code": "MO-PEON", "unit_cost": "700"},
            {"code": "NO-EXISTE", "unit_cost": "1"},
            {"code": "MAT-ACERO", "unit_cost": "abc"},
            {"code": "MAT-CIMBRA", "unit_cost": "-5"},
        ],
        source="CSV agosto",
    )
    assert result["updated"] == 1
    assert set(result["skipped"]) == {"NO-EXISTE", "MAT-ACERO", "MAT-CIMBRA"}
    assert store.load_price_book()["MO-PEON"].unit_cost == 700.0


def test_labor_percentage_equation(store):
    """%MO lines cost = fraction × labor subtotal — the herramienta equation."""
    store.set_apu_components(
        "PRE-001",
        [("MO-PEON", 1.0), ("EQ-HERRAMIENTA", 1.0)],
    )
    book = store.load_price_book()
    concept = next(
        c for c in build_default_catalog(CostingAssumptions()) if c.code == "PRE-001"
    )
    apu = build_apu(concept, resources=book, templates=store.load_templates())
    labor = book["MO-PEON"].unit_cost
    tool_fraction = book["EQ-HERRAMIENTA"].unit_cost  # 0.03 of labor
    assert apu.direct_unit_cost == pytest.approx(labor + labor * tool_fraction)
