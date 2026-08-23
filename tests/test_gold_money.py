"""The gold set fences money: quantities per concept within tolerance, the
direct cost within its own, and no concept the gold never saw."""

from klave_engine.costing.models import CostingConfig
from klave_engine.costing.report import generate_cost_report
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.dxf.units import DrawingUnits
from klave_engine.evals.gold import (
    MoneyExpectation,
    QuantityExpectation,
    money_from_report,
    score_money,
)


def _wall(det_id, length):
    det = make_detection(
        det_id, DetectionType.wall, det_id, (0, 0, length, 0.15), 0.9, [], "m", [],
        {"estimated_length": length, "estimated_thickness": 0.15, "wall_kind": "block"},
    )
    det.family = classify_family(det).value
    return det


def _report(length):
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    return generate_cost_report("p", [_wall("w1", length)], units, CostingConfig(), None, None)


def test_captured_money_passes_against_itself_and_fails_when_quantities_move():
    fence = money_from_report(_report(10.0))
    assert fence.direct_cost and fence.direct_cost > 0 and "EST-004" in fence.concepts
    scores, cost_ok, unexpected = score_money(fence, _report(10.0))
    assert all(s.passed for s in scores) and cost_ok and not unexpected
    # 15 % more wall: every wall-driven quantity drifts past the 10 % tolerance.
    scores, cost_ok, unexpected = score_money(fence, _report(11.5))
    wall = next(s for s in scores if s.concept_code == "EST-004")
    assert not wall.passed and wall.deviation_pct and abs(wall.deviation_pct - 15.0) < 0.01
    assert cost_ok is False


def test_human_rows_keep_their_own_tolerance_and_missing_concepts_fail():
    fence = MoneyExpectation(
        concepts={
            "EST-004": QuantityExpectation(quantity=27.0, unit="M2", tolerance_pct=2.0,
                                           source="human", note="cuantificado a mano"),
            "XXX-999": QuantityExpectation(quantity=1.0, unit="PZA"),
        },
        direct_cost=None,
    )
    scores, cost_ok, unexpected = score_money(fence, _report(10.0))
    by = {s.concept_code: s for s in scores}
    assert by["EST-004"].passed and by["EST-004"].source == "human"
    assert by["XXX-999"].actual is None and not by["XXX-999"].passed
    assert cost_ok is None
    assert "ACA-001" in unexpected  # the engine produces lines the gold never listed
