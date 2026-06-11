"""Grid detector tests on the demo fixture."""

from klave_engine.detection.grid_detector import detect_grid
from klave_engine.detection.results import DetectionType
from klave_engine.detection.text_patterns import TextPatternConfig, classify_text


def test_text_pattern_classifier() -> None:
    config = TextPatternConfig()
    assert any(m.category == "column_tag" for m in classify_text("C17", config))
    assert any(m.category == "beam_tag" for m in classify_text("B1", config))
    assert any(m.category == "grid_label" for m in classify_text("A", config))
    detail = next(
        m for m in classify_text("5/S-501", config) if m.category == "detail_reference"
    )
    assert detail.groups == {"detail": "5", "sheet": "S-501"}
    assert not classify_text("hello world", config)


def test_grid_lines_detected_with_labels(demo_entities, demo_index) -> None:
    output = detect_grid(demo_entities, demo_index)
    grid_lines = [d for d in output.detections if d.detection_type == DetectionType.grid_line]
    assert sorted(d.label for d in grid_lines) == ["1", "2", "A", "B"]
    assert all(d.confidence == 0.9 for d in grid_lines)
    axes = {d.label: d.properties["axis"] for d in grid_lines}
    assert axes == {"A": "horizontal", "B": "horizontal", "1": "vertical", "2": "vertical"}


def test_grid_intersections_detected(demo_entities, demo_index) -> None:
    output = detect_grid(demo_entities, demo_index)
    intersections = [
        d for d in output.detections if d.detection_type == DetectionType.grid_intersection
    ]
    assert sorted(d.label for d in intersections) == ["A/1", "A/2", "B/1", "B/2"]
    b1 = next(d for d in intersections if d.label == "B/1")
    assert b1.properties["point"] == (200.0, 600.0)
    assert len(b1.source_entities) == 2


def test_short_lines_are_not_grid_lines(demo_entities, demo_index) -> None:
    output = detect_grid(demo_entities, demo_index)
    grid_entity_ids = {
        entity_id
        for d in output.detections
        for entity_id in d.source_entities
    }
    wall_and_beam = [e for e in demo_entities if e.layer in ("S-WALL", "S-BEAM")]
    assert all(e.entity_id not in grid_entity_ids for e in wall_and_beam)


def test_grid_detections_carry_evidence(demo_entities, demo_index) -> None:
    output = detect_grid(demo_entities, demo_index)
    for detection in output.detections:
        assert detection.evidence.entity_ids
        assert detection.evidence.method
        assert detection.evidence.notes


def test_unlabeled_grid_lines_get_auto_labels(tmp_path) -> None:
    """Regression: intersections of unlabeled grid lines read H1/V1, not ?/?
    (found on a real drawing whose grid bubbles sit outside the label radius)."""
    import ezdxf
    from klave_engine.dxf.parser import DxfParser
    from klave_engine.geometry.spatial_index import SpatialIndex

    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((0, 100), (1000, 100), dxfattribs={"layer": "S-GRID"})
    msp.add_line((300, 0), (300, 400), dxfattribs={"layer": "S-GRID"})
    path = tmp_path / "nolabels.dxf"
    doc.saveas(str(path))

    entities = DxfParser().parse_file(path).entities
    output = detect_grid(entities, SpatialIndex(entities))
    lines = [d for d in output.detections if d.detection_type == DetectionType.grid_line]
    intersections = [
        d for d in output.detections if d.detection_type == DetectionType.grid_intersection
    ]
    assert sorted(d.label for d in lines) == ["H1", "V1"]
    assert [d.label for d in intersections] == ["H1/V1"]
    assert "?" not in intersections[0].label
