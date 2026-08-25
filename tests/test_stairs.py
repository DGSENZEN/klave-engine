"""Escaleras: the ESCALERA text on its tread pattern becomes an inclined
slab with steps; the text alone only warns."""

from klave_engine.common.ids import IdGenerator
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import CostingAssumptions
from klave_engine.detection.results import DetectionType
from klave_engine.detection.stair_detector import StairDetectorConfig, detect_stairs
from klave_engine.detection.taxonomy import classify_family, enrich_detections
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.dxf.units import DrawingUnits
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.graph.evidence import EvidencePacket

from tests.precios import LIBRO


def _line(eid, p0, p1, layer="A-ESCALERA"):
    bbox = (min(p0[0], p1[0]), min(p0[1], p1[1]), max(p0[0], p1[0]), max(p0[1], p1[1]))
    return NormalizedEntity(
        entity_id=eid, entity_type=EntityType.line, layer=layer, source_file="a.dxf",
        points=[p0, p1], bbox=bbox, raw_handle=eid,
        evidence=EvidencePacket(source="a.dxf", method="t", entity_ids=[eid], bbox=bbox,
                                confidence=1.0),
    )


def _text(eid, value, x, y):
    bbox = (x, y, x + 1.0, y + 0.25)
    return NormalizedEntity(
        entity_id=eid, entity_type=EntityType.text, layer="A-TEXTO", source_file="a.dxf",
        text=value, bbox=bbox, raw_handle=eid,
        evidence=EvidencePacket(source="a.dxf", method="t", entity_ids=[eid], bbox=bbox,
                                confidence=1.0),
    )


def _stair_entities():
    # Twelve treads 1.2 m wide, 0.28 m apart (a straight flight), text inside.
    treads = [
        _line(f"t{i}", (0.0, i * 0.28), (1.2, i * 0.28)) for i in range(12)
    ]
    return treads + [_text("s1", "ESCALERA", 0.2, 1.4)]


def test_treads_near_the_text_become_a_stair():
    entities = _stair_entities()
    out = detect_stairs(entities, SpatialIndex(entities), StairDetectorConfig(),
                        IdGenerator("s"))
    [stair] = out.detections
    assert stair.detection_type == DetectionType.stair
    assert stair.properties["tread_count"] == 12
    assert abs(stair.properties["stair_width"] - 1.2) < 1e-6
    assert abs(stair.properties["run_length"] - 0.28 * 11) < 1e-6
    assert abs(stair.properties["estimated_area"] - 1.2 * 0.28 * 11) < 1e-3
    assert classify_family(stair).value == "escalera"
    enrich_detections([stair], 1.0)
    assert stair.display_label.startswith("ESC")


def test_the_word_alone_only_warns():
    entities = [_text("s1", "ESCALERA", 0.0, 0.0)]
    out = detect_stairs(entities, SpatialIndex(entities), StairDetectorConfig(),
                        IdGenerator("s"))
    assert out.detections == []
    assert any("sin patrón de huellas" in w for w in out.warnings)


def test_stairs_are_priced_as_inclined_slab():
    entities = _stair_entities()
    out = detect_stairs(entities, SpatialIndex(entities), StairDetectorConfig(),
                        IdGenerator("s"))
    for d in out.detections:
        d.family = classify_family(d).value
    a = CostingAssumptions()
    catalog = [c for c in build_default_catalog(a) if c.code == "EST-015"]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", out.detections, units, catalog, build_all_apus(catalog, LIBRO), assumptions=a
    )
    [line] = boq.lines
    assert line.concept_code == "EST-015" and line.unit == "M2"
    assert abs(line.quantity - 1.2 * 0.28 * 11 * 1.15) < 1e-3
    assert line.amount > 0 and not line.unpriced
