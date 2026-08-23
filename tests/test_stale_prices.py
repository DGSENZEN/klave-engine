"""A presupuesto names the stale insumos it actually prices with."""

from klave_engine.costing.models import CostingConfig
from klave_engine.costing.report import generate_cost_report
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.dxf.units import DrawingUnits


def _wall(det_id, length):
    det = make_detection(
        det_id, DetectionType.wall, det_id, (0, 0, length, 0.15), 0.9, [], "m", [],
        {"estimated_length": length, "estimated_thickness": 0.15, "wall_kind": "block"},
    )
    det.family = classify_family(det).value
    return det


def test_stale_prices_used_by_the_presupuesto_are_named():
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    vigencias = {"MAT-BLOCK": "2024-01", "MAT-MORTERO": "", "MO-CUAD-ALB": "2026-07",
                 "MAT-VIGUETA": "2023-01"}  # vigueta is not used by a wall-only presupuesto
    report = generate_cost_report(
        "p", [_wall("w1", 10.0)], units, CostingConfig(), None, None,
        price_vigencias=vigencias,
    )
    stale = [w for w in report.boq.warnings if "más de 12 meses" in w]
    assert len(stale) == 1
    assert "MAT-BLOCK" in stale[0] and "MAT-MORTERO" in stale[0]
    assert "MAT-VIGUETA" not in stale[0] and "MO-CUAD-ALB" not in stale[0]
    fresh = generate_cost_report(
        "p", [_wall("w1", 10.0)], units, CostingConfig(), None, None,
        price_vigencias={"MAT-BLOCK": "2026-08", "MAT-MORTERO": "2026-08",
                         "MO-CUAD-ALB": "2026-08", "MAT-ACERO": "2026-08",
                         "EQ-HERRAMIENTA": "2026-08"},
    )
    assert not any("más de 12 meses" in w for w in fresh.boq.warnings)
