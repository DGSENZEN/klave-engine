"""Concept aliases: the taller's clave, description and price replace ours on
the presupuesto, remembered workspace-wide with who decided and where."""

import pytest
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.catalog import build_catalog_from_store
from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.models import CostingAssumptions, CostingConfig
from klave_engine.costing.report import generate_cost_report
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.dxf.units import DrawingUnits

from tests.precios import sembrar


@pytest.fixture
def store(data_dir):
    return get_catalog_store(data_dir)


def _wall(det_id, length):
    det = make_detection(
        det_id, DetectionType.wall, det_id, (0, 0, length, 0.15), 0.9, [], "m", [],
        {"estimated_length": length, "estimated_thickness": 0.15, "wall_kind": "block"},
    )
    det.family = classify_family(det).value
    return det


def _report(store):
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    return generate_cost_report(
        "p", [_wall("w1", 10.0)], units, CostingConfig(), None, None,
        price_book=store.load_price_book(), apu_templates=store.load_templates(),
        store_concepts=store.load_concepts(), concept_prices=store.load_concept_prices(),
        concept_aliases=store.load_concept_aliases(),
    )


def test_reference_alias_takes_the_row_clave_description_and_price(store):
    store.import_reference(
        {"key": "propio", "name": "Catálogo propio", "publisher": "Catálogo propio",
         "region": "MX", "vigencia": "2026-01", "kind": "precios_unitarios", "url": ""},
        [{"clave": "MUR-015", "description": "Muro de block 15x20x40 asentado con mortero 1:4",
          "unit": "M2", "price": 612.5, "group_clave": "", "group_description": ""}],
    )
    ref = store.search_reference("block", source_key="propio")[0]
    alias = store.set_concept_alias(
        "EST-004", kind="reference", ref_id=ref["ref_id"], actor="Ana",
        note="es nuestro muro estándar", project_id="lote_04",
    )
    assert alias["clave"] == "MUR-015" and alias["price"] == 612.5 and alias["actor"] == "Ana"
    line = next(ln for ln in _report(store).boq.lines if ln.concept_code == "EST-004")
    assert line.taller_clave == "MUR-015"
    assert line.description.startswith("Muro de block 15x20x40")
    assert line.unit_price == 612.5
    apu = next(a for a in _report(store).apus if a.concept_code == "EST-004")
    assert "MUR-015" in (apu.price_source or "")
    # Clearing restores the engine's own concept and matrix.
    assert store.clear_concept_alias("EST-004")
    line = next(ln for ln in _report(store).boq.lines if ln.concept_code == "EST-004")
    assert line.taller_clave == "" and line.unit_price != 612.5


def test_concept_alias_prices_with_the_taller_matrix(store):
    sembrar(store)
    store.create_concept(
        code="ALB-010", description="Muro de block del taller", unit="M2", phase="Albañilería",
        production_rate_per_day=12.0, components=[("MAT-BLOCK", 12.5), ("MO-CUAD-ALB", 0.12)],
    )
    store.set_concept_alias("EST-004", kind="concept", target_code="ALB-010", actor="Ana")
    report = _report(store)
    line = next(ln for ln in report.boq.lines if ln.concept_code == "EST-004")
    catalog = build_catalog_from_store(store.load_concepts(), CostingAssumptions())
    target = build_all_apus(catalog, store.load_price_book(), templates=store.load_templates())
    assert line.taller_clave == "ALB-010" and line.description == "Muro de block del taller"
    assert line.unit_price == target["ALB-010"].direct_unit_cost
    apu = next(a for a in report.apus if a.concept_code == "EST-004")
    assert apu.price_source and "matriz del taller ALB-010" in apu.price_source
    with pytest.raises(ValueError):
        store.set_concept_alias("EST-004", kind="concept", target_code="NOPE")


def test_a_price_in_another_unit_is_refused_unless_forced(store):
    from klave_engine.costing.catalog_store import UnitMismatch

    store.import_reference(
        {"key": "propio", "name": "Catálogo propio", "publisher": "Catálogo propio",
         "region": "MX", "vigencia": "2026-01", "kind": "precios_unitarios", "url": ""},
        [{"clave": "MUR-ML", "description": "Muro de block por metro lineal",
          "unit": "M", "price": 1500.0, "group_clave": "", "group_description": ""},
         {"clave": "MUR-M2", "description": "Muro de block por metro cuadrado",
          "unit": "m²", "price": 612.5, "group_clave": "", "group_description": ""}],
    )
    by_clave = {r["clave"]: r for r in store.search_reference("muro", source_key="propio")}
    with pytest.raises(UnitMismatch) as excinfo:
        store.set_concept_alias("EST-004", kind="reference", ref_id=by_clave["MUR-ML"]["ref_id"])
    assert excinfo.value.own_unit == "M2" and excinfo.value.other_unit == "M"
    assert "multiplica mal" in str(excinfo.value)
    with pytest.raises(UnitMismatch):
        store.adopt_concept_reference("EST-004", by_clave["MUR-ML"]["ref_id"])
    with pytest.raises(UnitMismatch):
        store.adopt_reference("MAT-BLOCK", by_clave["MUR-ML"]["ref_id"])  # MAT-BLOCK is M2
    # m² and M2 are the same unit; a forced adoption goes through.
    assert store.set_concept_alias(
        "EST-004", kind="reference", ref_id=by_clave["MUR-M2"]["ref_id"]
    )["price"] == 612.5
    forced = store.set_concept_alias(
        "EST-004", kind="reference", ref_id=by_clave["MUR-ML"]["ref_id"], force=True,
        note="el taller cotiza por ml de muro de 2.5 m",
    )
    assert forced["price"] == 1500.0 and forced["unit"] == "M"
