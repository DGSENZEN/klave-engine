"""Gold set: capture folds reviews into labels; the runner guards regressions."""

from klave_engine.common.config import get_settings
from klave_engine.costing.reviews import DetectionReview, load_reviews, save_reviews
from klave_engine.evals.fixtures import write_demo_project
from klave_engine.evals.gold import capture, evaluate_entry, load_entries, save_entry
from klave_engine.pipeline import run_full_pipeline


def test_capture_and_evaluate_round_trip(data_dir, tmp_path):
    settings = get_settings()
    root = tmp_path / "demo"
    write_demo_project(root)
    result = run_full_pipeline(root, settings)
    assert result.detections

    baseline = capture(root, "demo", settings)
    assert baseline.status == "baseline"
    assert baseline.files and all(len(v) == 64 for v in baseline.files.values())
    assert baseline.labels["column_tag"] and baseline.baseline_f1["column_tag"] == 1.0

    # A human excludes one detection and confirms another: the entry becomes
    # partial, the excluded label leaves the expectations, and the engine —
    # which still produces it — now scores below 1 on that type.
    control_dir = root / settings.processed_dir_name
    reviews = load_reviews(control_dir)
    column = next(d for d in result.detections if d.detection_type.value == "column_tag")
    wall = next(d for d in result.detections if d.detection_type.value == "wall")
    reviews.detections[column.display_label or column.label] = DetectionReview(status="excluded")
    reviews.detections[wall.display_label or wall.label] = DetectionReview(status="confirmed")
    save_reviews(control_dir, reviews)

    partial = capture(root, "demo", settings)
    assert partial.status == "partial"
    assert partial.excluded == [column.display_label or column.label]
    assert partial.confirmed == [wall.display_label or wall.label]
    assert len(partial.labels["column_tag"]) == len(baseline.labels["column_tag"]) - 1
    assert partial.baseline_f1["column_tag"] < 1.0

    gold_dir = tmp_path / "gold"
    save_entry(partial, gold_dir)
    assert [e.drawing_id for e in load_entries(gold_dir)] == ["demo"]

    outcome = evaluate_entry(partial, settings)
    assert outcome.available and outcome.fingerprint_matches
    assert outcome.passed  # unchanged engine never scores below its own baseline
    assert outcome.excluded_present == partial.excluded  # the debt is visible
    assert outcome.confirmed_missing == []


def test_missing_source_is_reported_not_failed(data_dir, tmp_path):
    from datetime import UTC, datetime

    from klave_engine.evals.gold import GoldEntry

    entry = GoldEntry(
        drawing_id="ausente", source=str(tmp_path / "nada"), files={},
        status="baseline", captured_at=datetime.now(UTC),
    )
    outcome = evaluate_entry(entry, get_settings())
    assert not outcome.available and outcome.passed and "no disponible" in outcome.message
