"""Vanos: a door gap is part of the wall, not the end of it; wall faces lose
their measured openings, or the assumed share when nothing was read."""

from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import CostingAssumptions
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.detection.wall_detector import WallDetectorConfig, detect_walls
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.dxf.units import DrawingUnits
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.graph.evidence import EvidencePacket

from tests.precios import LIBRO


def _line(eid, p0, p1, layer="A-MURO"):
    bbox = (min(p0[0], p1[0]), min(p0[1], p1[1]), max(p0[0], p1[0]), max(p0[1], p1[1]))
    return NormalizedEntity(
        entity_id=eid, entity_type=EntityType.line, layer=layer, source_file="a.dxf",
        points=[p0, p1], bbox=bbox, raw_handle=eid,
        evidence=EvidencePacket(
            source="a.dxf", method="test", entity_ids=[eid], bbox=bbox, confidence=1.0
        ),
    )


def test_a_door_gap_stays_inside_one_wall_with_its_width():
    # Two 4 m runs of a 0.15 m wall with a 0.9 m door between them (metres).
    entities = [
        _line("a1", (0.0, 0.0), (4.0, 0.0)), _line("a2", (0.0, 0.15), (4.0, 0.15)),
        _line("b1", (4.9, 0.0), (8.9, 0.0)), _line("b2", (4.9, 0.15), (8.9, 0.15)),
    ]
    config = WallDetectorConfig(min_length=1.5, max_thickness=0.45, min_thickness=0.05,
                                merge_gap=0.30, opening_gap_max=1.30)
    out = detect_walls(entities, SpatialIndex(entities), config)
    assert len(out.detections) == 1
    wall = out.detections[0]
    assert abs(wall.properties["estimated_length"] - 8.9) < 1e-6
    assert wall.properties["openings"] == [0.9]
    assert any("1 vanos" in n for n in wall.evidence.notes)
    # Without the opening allowance the old split survives.
    split = config.model_copy(update={"opening_gap_max": 0.0})
    old = detect_walls(entities, SpatialIndex(entities), split)
    assert len(old.detections) == 2


def _wall_det(det_id, length, openings):
    det = make_detection(
        det_id, DetectionType.wall, det_id, (0, 0, length, 0.15), 0.9, [], "m", [],
        {"estimated_length": length, "estimated_thickness": 0.15, "wall_kind": "block",
         "openings": openings, "opening_length": sum(openings)},
    )
    det.family = classify_family(det).value
    return det


def _lines(dets, a):
    catalog = [c for c in build_default_catalog(a) if c.code in {"EST-004", "ACA-001"}]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", dets, units, catalog, build_all_apus(catalog, LIBRO), assumptions=a
    )
    return {ln.concept_code: ln for ln in boq.lines}


def test_measured_openings_replace_the_assumed_share():
    a = CostingAssumptions()
    lines = _lines([_wall_det("w1", 10.0, [0.9, 1.2])], a)
    muro = lines["EST-004"]
    # 10 m × 2.7 m = 27 m² − 2.1 m × 2.1 m = 22.59 m²
    assert abs(muro.quantity - (27.0 - 2.1 * 2.1)) < 1e-6
    assert any("2 puertas/ventanas leídas" in n for n in muro.assumptions)
    assert not any("supuesto" in n and "Vanos" in n for n in muro.assumptions)
    aplanado = lines["ACA-001"]  # both faces
    assert abs(aplanado.quantity - (54.0 - 2.1 * 2.1 * 2)) < 1e-6


def test_without_read_openings_the_share_is_assumed_and_said():
    a = CostingAssumptions()
    muro = _lines([_wall_det("w1", 10.0, [])], a)["EST-004"]
    assert abs(muro.quantity - 27.0 * 0.82) < 1e-6
    assert any("Vanos −18 % supuesto" in n for n in muro.assumptions)
    off = _lines([_wall_det("w1", 10.0, [])], CostingAssumptions(opening_share_pct=0))["EST-004"]
    assert abs(off.quantity - 27.0) < 1e-6
