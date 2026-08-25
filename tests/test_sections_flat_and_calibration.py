"""Declared sections count on every sheet (A3), rejected readings are
reported instead of swallowed (A5), and the assumed column section comes
from columns — never from the most frequent NxM of the whole sheet (A10)."""

from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import CostingAssumptions
from klave_engine.costing.report import _calibrate_assumptions
from klave_engine.detection.dimensions import DimensionInventory
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.dxf.units import DrawingUnits

from tests.precios import LIBRO


def _column(det_id, mark, section=None):
    props = {"section_cm": section} if section else {}
    det = make_detection(
        det_id, DetectionType.column_tag, mark, (0, 0, 1, 1), 0.9, [], "m", [], props
    )
    det.family = classify_family(det).value
    return det


def _boq(dets, a=None):
    a = a or CostingAssumptions()
    catalog = [c for c in build_default_catalog(a) if c.code == "EST-001"]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    return generate_bill_of_quantities(
        "t", dets, units, catalog, build_all_apus(catalog, LIBRO), segmentation=None, assumptions=a
    )


def test_flat_sheet_uses_the_declared_sections_not_the_default():
    a = CostingAssumptions()
    dets = [_column("k1", "K-1", "15x20"), _column("k2", "K-1", "15x20"), _column("c1", "C-1")]
    line = {ln.concept_code: ln for ln in _boq(dets, a).lines}["EST-001"]
    expected = (2 * 0.03 + a.column_section_m2) * a.column_height_m
    assert abs(line.quantity - expected) < 1e-6
    assert any("2 declaradas" in n for n in line.assumptions)
    assert any("si no hay marcador" in n for n in line.assumptions)  # C-1 still uses it
    all_declared = _boq([_column("k1", "K-1", "15x20"), _column("c1", "C-1", "30x40")], a)
    line = {ln.concept_code: ln for ln in all_declared.lines}["EST-001"]
    assert abs(line.quantity - (0.03 + 0.12) * a.column_height_m) < 1e-6
    assert not any("si no hay marcador" in n for n in line.assumptions)


def test_out_of_range_sections_are_reported_with_the_value_read():
    a = CostingAssumptions()
    dets = [_column("k1", "K-1", "15x20"), _column("k2", "K-9", "300x300")]  # a zapata's cotas
    line = {ln.concept_code: ln for ln in _boq(dets, a).lines}["EST-001"]
    assert abs(line.quantity - (0.03 + a.castillo_section_m2) * a.column_height_m) < 1e-6
    rejected = next(n for n in line.assumptions if "fuera de rango" in n)
    assert "K-9 90000 cm²" in rejected


def test_large_building_columns_are_accepted_now():
    a = CostingAssumptions()
    dets = [_column("c1", "C-1", "120x120")]
    line = {ln.concept_code: ln for ln in _boq(dets, a).lines}["EST-001"]
    assert abs(line.quantity - 1.44 * a.column_height_m) < 1e-6


def test_column_section_calibrates_from_columns_not_from_the_sheets_text():
    base = CostingAssumptions()
    # The sheet's most frequent NxM is a 150x150 zapata; the columns say 30x40.
    dims = DimensionInventory(typical_section_cm=(150, 150), typical_section_m2=2.25)
    dets = [_column("c1", "C-1", "30x40"), _column("c2", "C-2", "30x40"), _column("c3", "C-3")]
    calibrated, notes = _calibrate_assumptions(base, dims, dets)
    assert abs(calibrated.column_section_m2 - 0.12) < 1e-9
    assert any("30x40" in n and "2 columnas" in n for n in notes)
    assert not any("150x150" in n for n in notes)
    # One declaring column is not a pattern: the assumption stays.
    alone, notes = _calibrate_assumptions(base, dims, [_column("c1", "C-1", "30x40")])
    assert alone.column_section_m2 == base.column_section_m2 and not notes
