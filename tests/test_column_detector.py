"""Column and footing detector tests on the demo fixture."""

from klave_engine.detection.column_detector import detect_columns
from klave_engine.detection.footing_detector import detect_footings
from klave_engine.detection.grid_detector import detect_grid
from klave_engine.detection.results import DetectionType


def _columns(demo_entities, demo_index):
    grid = detect_grid(demo_entities, demo_index)
    return detect_columns(demo_entities, demo_index, grid)


def test_column_tags_detected(demo_entities, demo_index) -> None:
    output = _columns(demo_entities, demo_index)
    labels = sorted(d.label for d in output.detections)
    assert labels == ["C1", "C1", "C2"]


def test_column_near_grid_has_high_confidence(demo_entities, demo_index) -> None:
    output = _columns(demo_entities, demo_index)
    on_grid = [d for d in output.detections if d.properties["has_nearby_grid"]]
    off_grid = [d for d in output.detections if not d.properties["has_nearby_grid"]]
    assert len(on_grid) == 2
    assert len(off_grid) == 1
    # Grid proximity is evidence: on-grid columns score higher than the off-grid one.
    assert all(d.confidence >= 0.9 for d in on_grid)
    assert off_grid[0].confidence < min(d.confidence for d in on_grid)
    assert {d.properties["nearest_grid"] for d in on_grid} == {"B/1", "A/2"}


def test_footings_detected_with_area_and_column(demo_entities, demo_index) -> None:
    columns = _columns(demo_entities, demo_index)
    output = detect_footings(demo_entities, demo_index, columns)
    footings = [d for d in output.detections if d.detection_type == DetectionType.footing]
    assert len(footings) == 2
    for footing in footings:
        assert footing.properties["estimated_area"] == 3600.0
        assert footing.properties["nearby_column_tag"] in ("C1", "C2")
        assert footing.confidence >= 0.85  # foundation layer + near column


def test_slab_is_not_a_footing(demo_entities, demo_index) -> None:
    columns = _columns(demo_entities, demo_index)
    output = detect_footings(demo_entities, demo_index, columns)
    for footing in output.detections:
        assert footing.properties["estimated_area"] < 50000.0
