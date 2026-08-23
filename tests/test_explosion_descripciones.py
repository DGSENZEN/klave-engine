"""Explosión de insumos from the priced lines, and LOPSRM-style long
descriptions that state only what the matrix prices."""

from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.descripciones import long_description
from klave_engine.costing.explosion import explode
from klave_engine.costing.models import Concept, CostingAssumptions, CostingConfig
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


def test_explosion_totals_every_resource_with_its_origins():
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    report = generate_cost_report("p", [_wall("w1", 10.0)], units, CostingConfig(), None, None)
    wall = next(ln for ln in report.boq.lines if ln.concept_code == "EST-004")
    explosion = explode(report)
    block = next(r for r in explosion.resources if r.code == "MAT-BLOCK")
    assert abs(block.quantity - wall.quantity * 1.0) < 1e-6  # 1 block per m² in the template
    assert "EST-004" in block.by_concept and "Estructura" in block.by_phase
    assert explosion.total > 0
    # The explosion equals the presupuesto's direct cost for matrix-priced lines.
    assert abs(explosion.total - report.boq.direct_cost_total) < 1.0
    assert explosion.by_type["material"] > 0 and explosion.by_type["mano_de_obra"] > 0


def test_long_description_names_the_matrix_materials():
    catalog = build_default_catalog(CostingAssumptions())
    concept = next(c for c in catalog if c.code == "EST-004")
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    report = generate_cost_report("p", [_wall("w1", 10.0)], units, CostingConfig(), None, None)
    apu = next(a for a in report.apus if a.concept_code == "EST-004")
    text = long_description(concept, apu)
    assert text.startswith("Suministro y construcción de muros de block")
    assert "incluye: materiales (" in text and "mano de obra" in text
    assert text.endswith("P.U.O.T.")
    cimbra = Concept(
        code="EST-011", description="Cimbra de contacto en losa maciza", unit="M2",
        phase="Estructura", production_rate_per_day=10.0,
    )
    assert long_description(cimbra, None).startswith("Cimbra y descimbra en")
