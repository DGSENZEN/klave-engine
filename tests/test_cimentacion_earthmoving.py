"""Relleno and acarreo derive from the excavation: the pit in banco, minus
what the concrete keeps, times the swell only for the trucks."""

from klave_engine.costing.models import CostingAssumptions, CostingConfig
from klave_engine.costing.report import generate_cost_report
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.dxf.units import DrawingUnits


def _footing(det_id, x):
    det = make_detection(
        det_id, DetectionType.footing, det_id, (x, 0, x + 2.0, 2.0), 0.9, [], "m", [],
        {"estimated_area": 4.0},
    )
    det.family = classify_family(det).value
    return det


def test_excavation_is_banco_and_fill_haul_follow():
    a = CostingAssumptions()
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    report = generate_cost_report(
        "p", [_footing("z1", 0.0), _footing("z2", 5.0)], units,
        CostingConfig(assumptions=a), None, None,
    )
    lines = {ln.concept_code: ln for ln in report.boq.lines}
    excavation = lines["CIM-001"]
    # 8 m² × 0.50 m of depth, in banco — no swell here.
    assert abs(excavation.quantity - 8.0 * a.excavation_depth_m) < 1e-6
    assert not any("abundamiento" in n and "1.3" in n for n in excavation.assumptions)

    buried = lines["CIM-002"].quantity + lines["CIM-003"].quantity * 0.05
    fill = lines["CIM-004"]
    assert abs(fill.quantity - (excavation.quantity - buried)) < 1e-3
    assert fill.amount > 0 and any("enterrados" in n for n in fill.assumptions)

    haul = lines["CIM-005"]
    assert abs(haul.quantity - excavation.quantity * a.excavation_swell_factor) < 1e-6
    assert any("abundamiento" in n for n in haul.assumptions)
    assert haul.amount > 0
