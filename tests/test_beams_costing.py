"""Trabes priced by their declared section; contratrabes are cimentación;
a note about holes is not a contratrabe section."""

from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import CostingAssumptions
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.schedules import build_schedule_inventory
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.dxf.entities import EntityType, EvidencePacket, NormalizedEntity
from klave_engine.dxf.units import DrawingUnits


def _beam(det_id, mark, family, span, **props):
    det = make_detection(
        det_id, DetectionType.beam_tag, mark, (0, 0, 1, 1), 0.9, [], "m", [],
        {"estimated_span_length": span, **props},
    )
    det.family = family
    return det


def test_trabes_use_declared_sections_and_contratrabes_go_to_cimentacion():
    dets = [
        _beam("t1", "T-1", "trabe", 4.0, section_cm="30x80"),  # 0.24 m² from the plano
        _beam("t2", "T-2", "trabe", 5.0, section_area_du2=40.0),  # a 40 m² "marker": implausible
        _beam("c1", "CTA-1", "contratrabe", 6.0),  # assumed contratrabe section
    ]
    assumptions = CostingAssumptions()
    catalog = [c for c in build_default_catalog(assumptions) if c.code in {"EST-002", "CIM-008"}]
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    boq = generate_bill_of_quantities(
        "t", dets, units, catalog, build_all_apus(catalog), assumptions=assumptions
    )
    lines = {line.concept_code: line for line in boq.lines}
    expected_trabes = 4.0 * 0.24 + 5.0 * assumptions.beam_section_m2
    assert abs(lines["EST-002"].quantity - expected_trabes) < 1e-6
    assert lines["EST-002"].source_detection_count == 2
    assert abs(lines["CIM-008"].quantity - 6.0 * assumptions.contratrabe_section_m2) < 1e-6


def _text(entity_id, text, x, y, height=0.1):
    bbox = (x, y, x + 0.5 * len(text) * height, y + height)
    return NormalizedEntity(
        entity_id=entity_id, entity_type=EntityType.text, source_file="a.dxf", layer="TEXTO",
        bbox=bbox, text=text, properties={"height": height}, raw_handle=entity_id,
        evidence=EvidencePacket(
            source="a.dxf", method="test", entity_ids=[entity_id], bbox=bbox, confidence=1.0,
        ),
    )


def test_hole_note_is_not_a_contratrabe_section():
    texts = [
        _text("n1", "NOTA: 1.-EL REFUERZO PARA HUECOS DE HASTA 15X20CMS 2.-COLOCAR EL PASO A LA "
              "MITAD DEL PERALTE DE LA CONTRATRABE", 0, 0),
        _text("n2", "CADENA DE ENRASE 15x25 4#3 E#2@15", 0, 5),
    ]
    inventory = build_schedule_inventory(texts, TextPatternConfig())
    families = {s.family: s for s in inventory.by_family.values()}
    assert "contratrabe" not in families or families["contratrabe"].section_cm is None
    assert families["dala"].section_cm == (15, 25)


def test_section_drawn_under_the_mark_in_a_detail_frame():
    """T1-4 written above a 30×60 cm rectangle inside a detail frame."""
    from klave_engine.dxf.entities import EvidencePacket as _EP

    rect = NormalizedEntity(
        entity_id="r1", entity_type=EntityType.polyline, source_file="a.dxf", layer="EST-DET",
        bbox=(10.0, 10.0, 10.3, 10.6), points=[(10, 10), (10.3, 10), (10.3, 10.6), (10, 10.6)],
        raw_handle="r1", properties={"closed": True},
        evidence=_EP(source="a.dxf", method="t", entity_ids=["r1"], bbox=(10, 10, 10.3, 10.6),
                     confidence=1.0),
    )
    # The estribo drawn 3 cm inside is what makes the rectangle a section.
    stirrup = rect.model_copy(update={
        "entity_id": "s1", "bbox": (10.03, 10.03, 10.27, 10.57),
        "points": [(10.03, 10.03), (10.27, 10.03), (10.27, 10.57), (10.03, 10.57)],
    })
    mark = _text("m1", "T1-4", 10.05, 10.75)
    plan_mark = _text("m2", "T1-5", 50.05, 10.75)  # same geometry outside any detail frame
    plan_rect = rect.model_copy(update={"entity_id": "r2", "bbox": (50.0, 10.0, 50.3, 10.6),
                                        "points": [(50, 10), (50.3, 10), (50.3, 10.6), (50, 10.6)]})
    inventory = build_schedule_inventory(
        [rect, stirrup, mark, plan_mark, plan_rect], TextPatternConfig(), unit_to_m=1.0,
        detail_boxes=[(0.0, 0.0, 40.0, 30.0)],
    )
    assert inventory.by_mark["T1-4"].section_cm == (30, 60)
    assert inventory.by_mark["T1-4"].source == "detalle"
    assert "T1-5" not in inventory.by_mark


def test_section_callouts_along_an_elevation_belong_to_its_title():
    """CTA-16 titles an elevation; 'SECCIÓN 1 / 30X80' and 'SECCIÓN 2 / 30X60'
    are called out at its far end. The largest section is kept."""
    texts = [
        _text("m1", "CTA-16", 2.0, 20.0, 0.12),
        _text("l1", "SECCIÓN 1", 21.0, 15.0, 0.1),
        _text("s1", "30X80", 21.0, 14.8, 0.1),
        _text("l2", "SECCIÓN 2", 23.0, 15.0, 0.1),
        _text("s2", "30X60", 23.0, 14.8, 0.1),
        _text("m2", "CTA-3", 2.0, 30.0, 0.12),  # another title, further above
        _text("s3", "40X40", 35.0, 2.0, 0.1),  # bare, no SECCIÓN label: ignored
    ]
    inventory = build_schedule_inventory(
        texts, TextPatternConfig(), unit_to_m=1.0, detail_boxes=[(0.0, 0.0, 44.0, 29.4)]
    )
    spec = inventory.by_mark["CTA-16"]
    assert spec.section_cm == (30, 80) and spec.source == "detalle"
    assert "sección 1 30x80, sección 2 30x60" in spec.source_text
    assert "CTA-3" not in inventory.by_mark
