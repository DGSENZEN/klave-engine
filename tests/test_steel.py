"""Acero de refuerzo: kilograms from counted elements and the sheet's armados."""

import math

import pytest
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.catalog import build_catalog_from_store
from klave_engine.costing.catalog_store import get_catalog_store
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    CostingAssumptions,
    QuantityKind,
)
from klave_engine.costing.steel import (
    BAR_KG_PER_M,
    SteelAssumptions,
    apply_steel,
    compute_steel,
    parse_rebar,
    parse_spacing,
)
from klave_engine.detection.results import DetectionType, make_detection

from tests.precios import sembrar


def _line(code, quantity, raw, ids, unit="M3", phase="Estructura"):
    return BoqLine(
        concept_code=code, description=code, unit=unit, quantity=quantity, unit_price=1.0,
        amount=quantity, phase=phase, raw_quantity=raw, raw_kind=QuantityKind.COUNT,
        source_detection_count=len(ids), source_detections=ids, confidence=0.9,
    )


def test_bar_parsing():
    assert parse_rebar("4#3") == (4, "3") and parse_rebar("6 # 4") == (6, "4")
    assert parse_rebar("4#9") is None and parse_rebar(None) is None
    assert parse_spacing("#2@20") == ("2", 0.20) and parse_spacing("E#3@15") == ("3", 0.15)
    assert BAR_KG_PER_M["3"] == 0.560


def test_castillo_kilograms_match_a_hand_calculation():
    k1 = make_detection("c1", DetectionType.column_tag, "K-1", (0, 0, 1, 1), 0.9, [], "m", [])
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-001", 0.135, 1, ["c1"])])
    specs = {"by_mark": {"K-1": {"rebar": "4#3", "stirrups": "#2@20", "section_cm": [15, 20]}}}
    report = compute_steel(boq, [k1], specs, None, 1.0, 3.0, SteelAssumptions())
    line = next(s for s in report.lines if s.concept_code == "ACE-001")
    longitudinal = 4 * (3.0 + 0.40) * 0.560
    perimeter = 2 * ((0.15 - 0.05) + (0.20 - 0.05)) + 0.075
    stirrups = (math.floor(3.0 / 0.20) + 1) * perimeter * 0.248
    assert line.quantity == pytest.approx((longitudinal + stirrups) * 1.05, abs=0.01)
    assert any("K-1: 1 pzas × 4#3 E#2@20" in n for n in line.notes)
    assert not any("supuesto" in n.lower() for n in line.notes)


def test_defaults_are_labeled_and_zapatas_use_drawn_sizes():
    k9 = make_detection("c9", DetectionType.column_tag, "K-9", (0, 0, 1, 1), 0.9, [], "m", [])
    z1 = make_detection(
        "f1", DetectionType.footing, "F1", (0, 0, 1, 1), 0.9, [], "m", [],
        {"estimated_area": 2.0, "dimensioned_width": 1.0, "dimensioned_length": 2.0},
    )
    z2 = make_detection(
        "f2", DetectionType.footing, "F2", (0, 0, 1, 1), 0.9, [], "m", [],
        {"estimated_area": 1.0},
    )
    w = make_detection("w1", DetectionType.wall, "W1", (0, 0, 1, 1), 0.9, [], "m", [])
    s = make_detection("s1", DetectionType.slab_region, "L1", (0, 0, 1, 1), 0.9, [], "m", [])
    boq = BillOfQuantities(
        project_id="p",
        lines=[
            _line("EST-001", 0.1, 1, ["c9"]),
            _line("CIM-002", 1.0, 3.0, ["f1", "f2"], phase="Cimentación"),
            _line("EST-004", 27.0, 10.0, ["w1"], unit="M2"),
            _line("EST-003", 50.0, 50.0, ["s1"], unit="M2"),
        ],
    )
    report = compute_steel(boq, [k9, z1, z2, w, s], None, None, 1.0, 2.5)
    codes = {line.concept_code: line for line in report.lines}
    assert set(codes) == {"ACE-001", "ACE-002", "ACE-003", "ACE-005"}
    assert any("Armado supuesto" in n for n in codes["ACE-001"].notes)
    assert any("1 con cotas del plano" in n for n in codes["ACE-003"].notes)
    # Parrilla #4@20 on a 1×2 footing: 5 bars of 2 m + 10 bars of 1 m (plus hooks).
    along = math.floor((1.0 - 0.05) / 0.20) + 1
    across = math.floor((2.0 - 0.05) / 0.20) + 1
    kg_f1 = (along * (2.0 + 0.075) + across * (1.0 + 0.075)) * 0.994
    assert codes["ACE-003"].quantity > kg_f1 * 1.05  # f2 adds its square share
    assert codes["ACE-005"].quantity == pytest.approx(55.0)
    assert codes["ACE-002"].quantity > 0


def test_trabes_without_armado_are_reported_not_invented():
    t1 = make_detection(
        "b1", DetectionType.beam_tag, "T-7", (0, 0, 1, 1), 0.9, [], "m", [],
        {"estimated_span_length": 4.0},
    )
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-002", 0.45, 4.0, ["b1"])])
    report = compute_steel(boq, [t1], None, None, 1.0, 3.0)
    assert not any(line.concept_code == "ACE-004" for line in report.lines)
    assert report.warnings and "T-7" in report.warnings[0]
    specs = {"by_mark": {"T-7": {"rebar": "6#5", "stirrups": "#3@15", "section_cm": [25, 45]}}}
    report = compute_steel(boq, [t1], specs, None, 1.0, 3.0)
    trabe = next(line for line in report.lines if line.concept_code == "ACE-004")
    assert trabe.quantity > 0 and not report.warnings


def test_apply_steel_prices_lines_from_the_catalog(data_dir):
    store = get_catalog_store(data_dir)
    sembrar(store)
    catalog = build_catalog_from_store(store.load_concepts(), CostingAssumptions())
    apus = build_all_apus(catalog, store.load_price_book(), templates=store.load_templates())
    assert "ACE-001" in apus and apus["ACE-001"].direct_unit_cost > 20  # $/kg
    k1 = make_detection("c1", DetectionType.column_tag, "K-1", (0, 0, 1, 1), 0.9, [], "m", [])
    boq = BillOfQuantities(project_id="p", lines=[_line("EST-001", 0.135, 1, ["c1"])])
    steel = compute_steel(boq, [k1], None, None, 1.0, 3.0)
    assert apply_steel(boq, catalog, apus, steel) == 1
    line = boq.lines[-1]
    assert line.concept_code == "ACE-001" and line.unit == "KG"
    assert line.amount == pytest.approx(line.quantity * apus["ACE-001"].direct_unit_cost, abs=0.01)
    assert boq.direct_cost_total == pytest.approx(sum(row.amount for row in boq.lines), abs=0.01)
