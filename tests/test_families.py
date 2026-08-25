"""Dalas/cerramientos, muros de concreto and pilotes: counted, priced where
the catálogo prices them, never invented."""

import ezdxf
from klave_engine.common.ids import IdGenerator
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import CostingAssumptions
from klave_engine.detection.pile_detector import PileDetectorConfig, detect_piles
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.dxf.parser import DxfParser
from klave_engine.dxf.units import DrawingUnits
from klave_engine.geometry.spatial_index import SpatialIndex

from tests.precios import LIBRO


def _beam(det_id, mark, span, **props):
    det = make_detection(
        det_id, DetectionType.beam_tag, mark, (0, 0, 1, 1), 0.9, [], "m", [],
        {"estimated_span_length": span, **props},
    )
    det.family = classify_family(det).value
    return det


def _wall(det_id, length, thickness, kind):
    det = make_detection(
        det_id, DetectionType.wall, det_id, (0, 0, length, thickness), 0.9, [], "m", [],
        {"estimated_length": length, "estimated_thickness": thickness, "wall_kind": kind},
    )
    det.family = classify_family(det).value
    return det


def test_dalas_concrete_walls_and_block_walls_go_to_their_own_concepts():
    a = CostingAssumptions(opening_share_pct=0)  # families, not vanos
    dets = [
        _beam("t", "T-1", 4.0, section_cm="25x50"),
        _beam("ce", "CE-1", 6.0),  # cadena de enrase: dala
        _beam("cr", "CR-2", 3.0, section_cm="15x30"),  # cerramiento, declared
        _wall("w1", 10.0, 0.15, "block"),
        _wall("w2", 5.0, 0.20, "concreto"),
    ]
    assert dets[1].family == "dala" and dets[2].family == "cerramiento"
    assert dets[4].family == "muro_concreto"
    catalog = [c for c in build_default_catalog(a) if c.code in
               {"EST-002", "EST-005", "EST-004", "EST-014"}]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", dets, units, catalog, build_all_apus(catalog, LIBRO), assumptions=a
    )
    lines = {line.concept_code: line for line in boq.lines}
    assert abs(lines["EST-002"].quantity - 4.0 * 0.125) < 1e-6
    assert abs(lines["EST-005"].quantity - 9.0) < 1e-6 and lines["EST-005"].unit == "M"
    assert abs(lines["EST-004"].quantity - 10.0 * a.wall_height_m) < 1e-6  # block only
    assert abs(lines["EST-014"].quantity - 5.0 * 0.20 * a.wall_height_m) < 1e-6


def test_piles_are_counted_and_left_unpriced_until_the_catalogo_prices_them(tmp_path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for i, mark in enumerate(("P-1", "P-1")):
        msp.add_circle((2 + i * 3, 2), 0.25, dxfattribs={"layer": "EST-PILOTES"})
        msp.add_text(mark, height=0.12).set_placement((2 + i * 3 + 0.3, 2.3))
    # An octagon drawn as a closed polyline is a pile too (Marina's convention).
    msp.add_lwpolyline(
        [(8.25, 2.1), (8.4, 2.25), (8.4, 2.45), (8.25, 2.6), (8.05, 2.6), (7.9, 2.45),
         (7.9, 2.25), (8.05, 2.1)], close=True, dxfattribs={"layer": "EST-PILOTES"},
    )
    msp.add_text("P-4", height=0.12).set_placement((8.5, 2.6))
    msp.add_text("P-9", height=0.12).set_placement((30, 30))  # no circle: not a pile
    path = tmp_path / "cim.dxf"
    doc.saveas(path)
    entities = DxfParser().parse_file(path).entities
    out = detect_piles(entities, SpatialIndex(entities), PileDetectorConfig(), IdGenerator("p"))
    assert [d.label for d in out.detections] == ["P-1", "P-1", "P-4"]
    assert abs(out.detections[0].properties["diameter"] - 0.5) < 1e-6
    assert abs(out.detections[2].properties["diameter"] - 0.5) < 1e-6
    a = CostingAssumptions()
    catalog = [c for c in build_default_catalog(a) if c.code == "CIM-010"]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", out.detections, units, catalog, build_all_apus(catalog, LIBRO), assumptions=a
    )
    # No matrix: the count is on the presupuesto, visibly unpriced — never $0 quietly.
    [line] = boq.lines
    assert line.unpriced and line.unit_price == 0.0 and line.amount == 0.0 and line.quantity == 3
    assert boq.direct_cost_total == 0.0
    assert any("CIM-010" in w and "3.00 PZA" in w and "sin costo" in w for w in boq.warnings)


def test_strip_footings_and_zapata_marks_are_read():
    from klave_engine.detection.footing_detector import FootingDetectorConfig, detect_footings
    from klave_engine.dxf.entities import EntityType, NormalizedEntity
    from klave_engine.geometry.spatial_index import SpatialIndex
    from klave_engine.graph.evidence import EvidencePacket

    def poly(eid, x0, y0, x1, y1, layer="EST-CIMENTACION"):
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        return NormalizedEntity(
            entity_id=eid, entity_type=EntityType.polyline, layer=layer, source_file="a.dxf",
            points=pts, bbox=(x0, y0, x1, y1), raw_handle=eid,
            properties={"closed": True},
            evidence=EvidencePacket(source="a.dxf", method="t", entity_ids=[eid],
                                    bbox=(x0, y0, x1, y1), confidence=1.0),
        )

    def text(eid, value, x, y):
        return NormalizedEntity(
            entity_id=eid, entity_type=EntityType.text, layer="EST-CIMENTACION",
            source_file="a.dxf", text=value, bbox=(x, y, x + 0.5, y + 0.2), raw_handle=eid,
            evidence=EvidencePacket(source="a.dxf", method="t", entity_ids=[eid],
                                    bbox=(x, y, x + 0.5, y + 0.2), confidence=1.0),
        )

    entities = [
        poly("z1", 0, 0, 1.5, 1.5),            # zapata aislada 1.5×1.5
        poly("zc", 3, 0, 3.6, 18.0),           # corrida 0.6×18 = 10.8 m², aspect 30
        poly("big", 6, 0, 14, 40),             # 8×40: too wide for a strip, too big for a zapata
        text("t1", "Z-1", 0.5, 0.6),
        text("t2", "ZC-2", 3.1, 9.0),
    ]
    config = FootingDetectorConfig(
        min_area=0.3, max_area=30.25, strip_max_width=1.5, strip_min_aspect=4.0,
        mark_search_radius=1.2, semantic_authority_min=1, column_search_radius=2.0,
    )
    out = detect_footings(entities, SpatialIndex(entities), None, config)
    by_mark = {d.properties.get("mark"): d for d in out.detections}
    assert set(by_mark) == {"Z-1", "ZC-2"}
    corrida = by_mark["ZC-2"]
    assert corrida.properties["footing_kind"] == "corrida"
    assert abs(corrida.properties["strip_length"] - 18.0) < 1e-6
    assert abs(corrida.properties["estimated_area"] - 10.8) < 1e-6
    from klave_engine.detection.taxonomy import enrich_detections

    enrich_detections(out.detections, None)
    assert by_mark["Z-1"].mark == "Z-1" and "Z-1" in by_mark["Z-1"].display_label
