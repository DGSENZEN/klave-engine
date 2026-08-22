"""A concept priced from the taller's catálogo: P.U. adopted with provenance,
matrix set aside, every presupuesto line saying where the price came from."""

import pytest
from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.models import CostingConfig
from klave_engine.costing.report import generate_cost_report
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.dxf.units import DrawingUnits

SOURCE = {
    "key": "propio-mi-catalogo", "name": "Catálogo propio 2026", "publisher": "Catálogo propio",
    "region": "MX", "vigencia": "2026-01", "kind": "precios_unitarios", "url": "",
}
ROWS = [
    {"clave": "1-EST-LOS-011", "description": "Losa de vigueta y bovedilla 20 cm", "unit": "M2",
     "price": 1096.63},
]


@pytest.fixture
def store(data_dir):
    return get_catalog_store(data_dir)


def test_adopted_concept_price_replaces_the_matrix(store):
    store.import_reference(SOURCE, ROWS)
    ref = store.search_reference("vigueta")[0]
    row = store.adopt_concept_reference("EST-012", ref["ref_id"])
    assert row["price_override"] == 1096.63 and row["price_clave"] == "1-EST-LOS-011"
    assert store.load_concept_prices()["EST-012"]["source"] == "Catálogo propio 2026"

    slab = make_detection(
        "s1", DetectionType.slab_region, "TAB1", (0, 0, 6, 5), 0.9, [], "slab_panel", [],
        {"estimated_area": 30.0, "family": "vigueta_bovedilla", "thickness_cm": 20},
    )
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    report = generate_cost_report(
        "p", [slab], units, CostingConfig(),
        price_book=store.load_price_book(), apu_templates=store.load_templates(),
        store_concepts=store.load_concepts(), concept_prices=store.load_concept_prices(),
    )
    line = next(line for line in report.boq.lines if line.concept_code == "EST-012")
    assert line.unit_price == 1096.63 and line.amount == pytest.approx(30 * 1096.63)
    assert any("Catálogo propio 2026 · 1-EST-LOS-011 · vigencia 2026-01" in a
               for a in line.assumptions)
    apu = next(apu for apu in report.apus if apu.concept_code == "EST-012")
    assert apu.lines == [] and apu.price_source and apu.direct_unit_cost == 1096.63

    store.clear_concept_price("EST-012")
    assert store.load_concept_prices() == {}
