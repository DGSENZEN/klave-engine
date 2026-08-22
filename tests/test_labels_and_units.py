"""Stable review keys from marks, and the engineer's unit outranking detection."""

from klave_engine.common.config import get_settings
from klave_engine.costing.reviews import load_reviews, save_reviews
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import enrich_detections
from klave_engine.evals.fixtures import write_demo_project
from klave_engine.pipeline import run_full_pipeline


def _det(i, dtype, label, x):
    return make_detection(f"d{i}", dtype, label, (x, 0, x + 1, 1), 0.9, [], "m", [])


def test_display_labels_follow_marks():
    dets = [
        _det(1, DetectionType.column_tag, "K-1", 0),
        _det(2, DetectionType.column_tag, "K-1", 5),
        _det(3, DetectionType.column_tag, "C-2", 9),
        _det(4, DetectionType.wall, "W1", 0),
        _det(5, DetectionType.wall, "W2", 3),
        _det(6, DetectionType.grid_line, "B", 0),
    ]
    dets[5].evidence.notes.append("Grid label 'B' found near line endpoint")
    enrich_detections(dets, 1.0)
    labels = {d.detection_id: d.display_label for d in dets}
    assert labels["d1"] == "CAS-K-1-01" and labels["d2"] == "CAS-K-1-02"
    assert labels["d3"] == "COL-C-2"
    assert labels["d4"] == "MUR-01" and labels["d5"] == "MUR-02"  # unmarked: numbered
    assert labels["d6"] == "EJE-B"
    # Adding an unrelated castillo leaves every other key untouched.
    more = dets + [_det(7, DetectionType.column_tag, "K-3", 20)]
    enrich_detections(more, 1.0)
    assert {d.detection_id: d.display_label for d in more if d.detection_id != "d7"} == labels


def test_confirmed_unit_overrides_detection(data_dir, tmp_path):
    settings = get_settings()
    root = tmp_path / "demo"
    write_demo_project(root)
    first = run_full_pipeline(root, settings)
    assert first.units is not None and first.units.source != "confirmed"
    control_dir = root / settings.processed_dir_name
    reviews = load_reviews(control_dir)
    reviews.verification.units_override = "cm"
    save_reviews(control_dir, reviews)
    second = run_full_pipeline(root, settings)
    assert second.units is not None
    assert second.units.unit == "cm" and second.units.source == "confirmed"
    assert second.units.confidence == 1.0
    assert any("Detección previa" in note for note in second.units.notes)
