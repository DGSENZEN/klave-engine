"""Correction loop: exclusion keys, adjustment math, and total consistency."""

import pytest

from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    CostingAssumptions,
    QuantityKind,
)
from klave_engine.costing.report import _apply_adjustments
from klave_engine.costing.reviews import (
    DetectionReview,
    ManualAdjustment,
    ProjectReviews,
    filter_excluded,
    review_key,
)
from klave_engine.detection.results import Detection, DetectionType
from klave_engine.graph.evidence import EvidencePacket


def _detection(detection_id: str, display_label: str = "") -> Detection:
    return Detection(
        detection_id=detection_id,
        detection_type=DetectionType.column_tag,
        label="C1",
        bbox=(0.0, 0.0, 1.0, 1.0),
        confidence=0.9,
        evidence=EvidencePacket(source="S-101.dxf", method="test"),
        display_label=display_label,
    )


def test_review_key_prefers_display_label():
    assert review_key(_detection("det_1", "CAS-05")) == "CAS-05"
    assert review_key(_detection("det_2")) == "det_2"


def test_filter_excluded_by_stable_key():
    detections = [_detection("det_1", "CAS-01"), _detection("det_2", "CAS-02")]
    reviews = ProjectReviews(
        detections={"CAS-02": DetectionReview(status="excluded", actor="Diego")}
    )
    remaining = filter_excluded(detections, reviews)
    assert [review_key(d) for d in remaining] == ["CAS-01"]
    # Confirmations never remove anything.
    reviews.detections["CAS-01"] = DetectionReview(status="confirmed")
    assert len(filter_excluded(detections, reviews)) == 1


def _boq_with_line(quantity: float = 10.0) -> tuple[BillOfQuantities, list, dict]:
    catalog = build_default_catalog(CostingAssumptions())
    apus = build_all_apus(catalog)
    concept = next(c for c in catalog if c.code == "EST-004")
    line = BoqLine(
        concept_code=concept.code,
        description=concept.description,
        unit=concept.unit,
        quantity=quantity,
        unit_price=apus[concept.code].direct_unit_cost,
        amount=round(quantity * apus[concept.code].direct_unit_cost, 2),
        phase=concept.phase,
        raw_quantity=quantity,
        raw_kind=QuantityKind.LENGTH,
        source_detection_count=3,
        confidence=0.8,
    )
    boq = BillOfQuantities(
        project_id="p",
        lines=[line],
        direct_cost_total=line.amount,
        totals_by_phase={concept.phase: line.amount},
    )
    return boq, catalog, apus


def _adjustment(concept: str, delta: float, note: str = "") -> ManualAdjustment:
    return ManualAdjustment(
        adjustment_id="adj_1", concept_code=concept, quantity_delta=delta,
        note=note, actor="Ana",
    )


def test_adjustment_moves_quantity_amount_and_totals():
    boq, catalog, apus = _boq_with_line(10.0)
    unit_price = boq.lines[0].unit_price
    _apply_adjustments(boq, catalog, apus, [_adjustment("EST-004", 5.0, "eje 5")])
    line = boq.lines[0]
    assert line.quantity == 15.0
    assert line.amount == pytest.approx(15.0 * unit_price, abs=0.01)
    assert boq.direct_cost_total == pytest.approx(line.amount, abs=0.01)
    assert boq.totals_by_phase[line.phase] == pytest.approx(line.amount, abs=0.01)
    assert any("Ajuste manual" in note and "Ana" in note for note in line.assumptions)


def test_adjustment_creates_line_for_missing_concept():
    boq, catalog, apus = _boq_with_line(10.0)
    _apply_adjustments(boq, catalog, apus, [_adjustment("EST-003", 40.0, "losa faltante")])
    created = next(line for line in boq.lines if line.concept_code == "EST-003")
    assert created.quantity == 40.0
    assert created.source_detection_count == 0
    assert created.confidence == 1.0
    assert boq.direct_cost_total == pytest.approx(
        sum(line.amount for line in boq.lines), abs=0.01
    )


def test_negative_adjustment_clamps_at_zero_with_warning():
    boq, catalog, apus = _boq_with_line(10.0)
    _apply_adjustments(boq, catalog, apus, [_adjustment("EST-004", -25.0)])
    assert boq.lines[0].quantity == 0.0
    assert boq.lines[0].amount == 0.0
    assert any("limitado a cantidad cero" in w for w in boq.warnings)


def test_unknown_concept_warns_instead_of_dropping_silently():
    boq, catalog, apus = _boq_with_line(10.0)
    before = boq.direct_cost_total
    _apply_adjustments(boq, catalog, apus, [_adjustment("XXX-999", 5.0)])
    assert boq.direct_cost_total == before
    assert any("concepto desconocido XXX-999" in w for w in boq.warnings)


def test_negative_adjustment_on_missing_concept_is_refused():
    boq, catalog, apus = _boq_with_line(10.0)
    _apply_adjustments(boq, catalog, apus, [_adjustment("EST-003", -5.0)])
    assert all(line.concept_code != "EST-003" for line in boq.lines)
    assert any("negativo ignorado" in w for w in boq.warnings)
