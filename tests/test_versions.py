"""Presupuesto versions: snapshots with the human decisions, line diffs, and
the index that survives a deletion."""

from klave_engine.costing.models import CostingConfig, CostingOverrides
from klave_engine.costing.report import generate_cost_report
from klave_engine.costing.reviews import ManualAdjustment, ProjectReviews
from klave_engine.costing.versions import (
    delete_version,
    diff_reports,
    list_versions,
    load_version,
    save_version,
)
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


def _report(adjustments=None):
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    return generate_cost_report(
        "p", [_wall("w1", 10.0), _wall("w2", 5.0)], units, CostingConfig(), None, None,
        adjustments=adjustments,
    )


def test_versions_are_saved_listed_and_loaded_with_their_decisions(tmp_path):
    reviews = ProjectReviews(adjustments=[
        ManualAdjustment(adjustment_id="a1", concept_code="EST-004", quantity_set=30.0,
                         note="muro extra", actor="Ana"),
    ])
    report = _report(reviews.adjustments)
    first = save_version(tmp_path, report, reviews, CostingOverrides(version=2),
                         label="Entrega 1", note="para el cliente", actor="Ana", run_id="run_a")
    second = save_version(tmp_path, report, reviews, CostingOverrides(), label="")
    listed = list_versions(tmp_path)
    assert [v.number for v in listed] == [1, 2]
    assert listed[0].label == "Entrega 1" and listed[1].label == "Versión 2"
    assert first.adjustments == 1 and first.overrides_version == 2 and first.run_id == "run_a"
    loaded = load_version(tmp_path, first.version_id)
    assert loaded is not None
    assert loaded.reviews.adjustments[0].quantity_set == 30.0
    assert loaded.report.boq.direct_cost_total == report.boq.direct_cost_total
    assert load_version(tmp_path, "../index") is None
    assert delete_version(tmp_path, second.version_id)
    assert [v.number for v in list_versions(tmp_path)] == [1]
    assert not delete_version(tmp_path, second.version_id)


def test_diff_tells_what_moved_and_why_much():
    before = _report()
    after = _report([
        ManualAdjustment(adjustment_id="a1", concept_code="EST-004", quantity_set=30.0),
        ManualAdjustment(adjustment_id="a2", concept_code="EST-003", quantity_delta=40.0),
    ])
    diff = diff_reports(before, after, before_label="v1", after_label="actual")
    by_code = {c.concept_code: c for c in diff.lines}
    walls = by_code["EST-004"]
    assert walls.status == "changed" and walls.quantity_after == 30.0
    assert walls.quantity_before == before.boq.lines[0].quantity
    assert by_code["EST-003"].status == "added" and by_code["EST-003"].quantity_before is None
    assert diff.changed == 1 and diff.added == 1 and diff.removed == 0
    assert diff.direct_cost_after > diff.direct_cost_before
    assert abs(
        sum(c.amount_after - c.amount_before for c in diff.lines)
        - (diff.direct_cost_after - diff.direct_cost_before)
    ) < 0.05
