"""The programa is handed to a client citing RLOPSRM art. 224. These are the
things that must be true of it before that is defensible."""

from klave_engine.costing.models import CostingConfig, ScheduleLink
from klave_engine.costing.report import generate_cost_report
from klave_engine.costing.schedule import _dedupe_links
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.dxf.units import DrawingUnits

from tests.precios import LIBRO


def _structural_report():
    """A column and a beam: enough to produce concrete, its steel and its
    formwork, which is where every ordering bug in this file lives."""
    detections = []
    for index in range(6):
        column = make_detection(
            f"c{index}", DetectionType.column_tag, f"C-{index}",
            (index, 0, index + 0.3, 0.3), 0.9, [], "m", [],
            {"section_cm": "30x30"},
        )
        column.family = classify_family(column).value
        detections.append(column)
    for index in range(4):
        beam = make_detection(
            f"b{index}", DetectionType.beam_tag, f"T-{index}",
            (0, index, 5.0, index + 0.3), 0.9, [], "m", [],
            {"estimated_span_length": 5.0, "section_cm": "30x60"},
        )
        beam.family = classify_family(beam).value
        detections.append(beam)
    units = DrawingUnits(unit="m", source="dxf_header", confidence=0.9)
    return generate_cost_report(
        "p", detections, units, CostingConfig(), None, None, price_book=LIBRO
    )


def test_no_activity_lists_the_same_predecessor_twice():
    """The step anchor and the crew tail are often the same concept, and both
    branches used to append their own link — 13 of 30 activities on Marina."""
    report = _structural_report()

    for activity in report.schedule.activities:
        seen = [(link.predecessor, link.kind) for link in activity.predecessors]
        assert len(seen) == len(set(seen)), f"{activity.concept_code} repite {seen}"


def test_dedupe_links_keeps_the_larger_lag_on_a_collision():
    """Two SS links to the same predecessor are two constraints on one edge;
    both apply at once, so the true bound is their max and the smaller lag
    must not survive. A fixture-based test cannot exercise this: the step
    anchor and the crew tail always compute the same lag from the same
    activity's duration_days when they collide, so only a hand-built pair
    with genuinely different lags reaches the branch that chooses."""
    links = [
        ScheduleLink(predecessor="EST-001", kind="SS", lag_days=3),
        ScheduleLink(predecessor="EST-001", kind="SS", lag_days=7),
    ]

    result = _dedupe_links(links)

    assert result == [ScheduleLink(predecessor="EST-001", kind="SS", lag_days=7)]


def test_dedupe_links_does_not_collapse_a_differing_kind():
    """The key is (predecessor, kind): an FS and an SS to the same
    predecessor are different constraints and both must survive."""
    links = [
        ScheduleLink(predecessor="EST-001", kind="SS", lag_days=3),
        ScheduleLink(predecessor="EST-001", kind="FS", lag_days=0),
    ]

    result = _dedupe_links(links)

    assert {(link.predecessor, link.kind, link.lag_days) for link in result} == {
        ("EST-001", "SS", 3),
        ("EST-001", "FS", 0),
    }
