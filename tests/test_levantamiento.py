"""A mapped symbol or layer becomes a presupuesto line with its provenance;
an unmapped one stays a count; a concept without price never gets a line."""

import pytest
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.levantamiento import apply_inventory
from klave_engine.costing.models import BillOfQuantities, CostingAssumptions

from tests.precios import LIBRO

INVENTORY = {
    "unit": "m",
    "sheets": [
        {
            "sheet": "05 SANITARIO.dxf", "discipline": "sanitaria",
            "blocks": [
                {"block_name": "DESCSAN1", "layer": "00-SANITARIA", "count": 16,
                 "by_view": {"IS-100 · PB": 10, "IS-200 · PA": 6}},
                {"block_name": "subida-bajada", "layer": "00-SANITARIA", "count": 14,
                 "by_view": {}},
            ],
            "runs": [
                {"layer": "00-SANITARIA", "length_m": 128.27, "length_du": 128.27,
                 "segments": 83, "by_view": {}},
                {"layer": "SIN-UNIDAD", "length_m": None, "length_du": 40.0, "segments": 3,
                 "by_view": {}},
            ],
            "specs": [], "notes": [],
        }
    ],
    "notes": [],
}


@pytest.fixture
def store(data_dir):
    return get_catalog_store(data_dir)


def test_mapping_rules_are_stored_and_unique_per_pattern(store):
    row = store.add_inventory_mapping(kind="block", pattern="DESCSAN1", concept_code="CIM-003")
    assert row["id"] and row["factor"] == 1.0
    again = store.add_inventory_mapping(
        kind="block", pattern="DESCSAN1", concept_code="CIM-004", factor=2.0
    )
    assert again["concept_code"] == "CIM-004" and len(store.list_inventory_mappings()) == 1
    with pytest.raises(ValueError):
        store.add_inventory_mapping(kind="block", pattern="X", concept_code="NOPE-1")
    assert store.delete_inventory_mapping(again["id"]) is True
    assert store.list_inventory_mappings() == []


def test_mapped_counts_become_lines_with_provenance():
    assumptions = CostingAssumptions()
    catalog = build_default_catalog(assumptions)
    apus = build_all_apus(catalog, LIBRO)
    boq = BillOfQuantities(project_id="p")
    mappings = [
        # 16 descargas × 1 → PRE-001 (any priced concept serves the test)
        {"kind": "block", "pattern": "descsan1", "concept_code": "PRE-001", "factor": 1.0},
        # 128.27 m of drain → CIM-001 at 0.5 m³ per metre
        {"kind": "layer", "pattern": "00-SANITARIA", "concept_code": "CIM-001", "factor": 0.5},
        # a layer without metres cannot be quantified
        {"kind": "layer", "pattern": "SIN-UNIDAD", "concept_code": "CIM-001", "factor": 1.0},
        # unknown concept → warning, no line
        {"kind": "block", "pattern": "subida-bajada", "concept_code": "ZZZ-9", "factor": 1.0},
    ]
    applied = apply_inventory(boq, catalog, apus, INVENTORY, mappings)
    assert applied == 2
    lines = {line.concept_code: line for line in boq.lines}
    assert lines["PRE-001"].quantity == 16 and lines["PRE-001"].source_detection_count == 16
    assert lines["PRE-001"].by_view == {"IS-100 · PB": 10, "IS-200 · PA": 6}
    assert "Levantamiento: 16.00 símbolos «descsan1»" in lines["PRE-001"].assumptions[0]
    assert lines["CIM-001"].quantity == pytest.approx(128.27 * 0.5)
    assert lines["CIM-001"].amount == pytest.approx(
        lines["CIM-001"].quantity * lines["CIM-001"].unit_price, abs=0.02
    )
    assert boq.direct_cost_total == pytest.approx(
        lines["PRE-001"].amount + lines["CIM-001"].amount, abs=0.02
    )
    assert any("ZZZ-9" in w for w in boq.warnings)
    assert any("SIN-UNIDAD" in w for w in boq.warnings)
