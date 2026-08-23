"""Pilotes: counted by the planta, measured by the length the plano declares."""

from klave_engine.costing.models import CostingConfig
from klave_engine.costing.report import generate_cost_report
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.schedules import parse_pile_length
from klave_engine.dxf.units import DrawingUnits


def _pile(det_id, mark):
    return make_detection(
        det_id, DetectionType.pile, mark, (0, 0, 0.6, 0.6), 0.85, [], "m", [],
        {"diameter": 0.6},
    )


def test_pile_length_is_read_from_the_notes():
    assert parse_pile_length(["PILOTES DE 12.00 M DE LONGITUD, COLADOS EN SITIO"]) == 12.0
    assert parse_pile_length(["LONGITUD DE PILOTE: 15 M"]) == 15.0
    assert parse_pile_length(["PILA Ø80 L=18.50 MTS"]) == 18.5
    assert parse_pile_length(["PILOTES SEGÚN ESTUDIO DE MECÁNICA DE SUELOS"]) is None
    assert parse_pile_length(["PILOTES DE 120 M"]) is None  # not a length


def _report(dets, specs):
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    return generate_cost_report(
        "p", dets, units, CostingConfig(), None, None, schedule_specs=specs
    )


def test_without_a_length_the_count_stays_visible_and_unpriced():
    report = _report([_pile("p1", "P-1"), _pile("p2", "P-2")], {"by_mark": {}, "by_family": {}})
    lines = {ln.concept_code: ln for ln in report.boq.lines}
    assert "CIM-011" not in lines
    count = lines["CIM-010"]
    assert count.quantity == 2 and count.unpriced and count.amount == 0.0
    assert any("sin longitud declarada" in n for n in count.assumptions)


def test_with_a_declared_length_the_piles_become_priced_metres():
    specs = {"by_mark": {"P-2": {"mark": "P-2", "family": "pilote", "length_m": 15.0,
                                  "source": "ia", "source_text": "IA", "confidence": 0.5}},
             "by_family": {}, "pile_length_m": 12.0}
    report = _report([_pile("p1", "P-1"), _pile("p2", "P-2")], specs)
    lines = {ln.concept_code: ln for ln in report.boq.lines}
    assert "CIM-010" not in lines  # every pile has a length: the count retires
    meters = lines["CIM-011"]
    assert meters.quantity == 27.0 and meters.unit == "M" and not meters.unpriced
    assert meters.amount > 0 and meters.unit_price > 0
    assert any("1 de 12 m" in n and "1 de 15 m" in n for n in meters.assumptions)
    assert report.boq.direct_cost_total == meters.amount
