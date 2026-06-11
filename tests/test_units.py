"""Drawing unit detection tests."""

from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.dxf.units import detect_units
from klave_engine.graph.evidence import EvidencePacket


def _text_entity(index: int, height: float) -> NormalizedEntity:
    return NormalizedEntity(
        entity_id=f"ent_{index:06d}",
        entity_type=EntityType.text,
        source_file="x.dxf",
        layer="TEXTOS",
        bbox=(0.0, 0.0, 1.0, 1.0),
        raw_handle="A1",
        text="C-1",
        properties={"height": height},
        evidence=EvidencePacket(source="x.dxf", method="test"),
    )


def test_header_meters_wins() -> None:
    units = detect_units(6, [])
    assert units.unit == "m"
    assert units.source == "dxf_header"
    assert units.to_meters() == 1.0


def test_header_millimeters() -> None:
    units = detect_units(4, [])
    assert units.unit == "mm"
    assert units.to_meters() == 0.001


def test_heuristic_meters_from_text_heights() -> None:
    entities = [_text_entity(i, 0.10) for i in range(20)]
    units = detect_units(None, entities)
    assert units.unit == "m"
    assert units.source == "text_height_heuristic"
    assert units.confidence < 0.9


def test_heuristic_millimeters_from_text_heights() -> None:
    entities = [_text_entity(i, 100.0) for i in range(20)]
    units = detect_units(None, entities)
    assert units.unit == "mm"


def test_inconclusive_heights_stay_unknown() -> None:
    entities = [_text_entity(i, 5.0) for i in range(20)]
    units = detect_units(None, entities)
    assert units.unit == "drawing_units"
    assert not units.known
    assert units.to_meters() is None


def test_too_few_texts_stay_unknown() -> None:
    assert detect_units(None, [_text_entity(0, 0.1)]).unit == "drawing_units"
