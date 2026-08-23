"""Review at scale: the revision table lists what feeds the money, doubts
first, with the human verdict beside each row."""

from klave_engine.costing.models import CostingConfig
from klave_engine.costing.report import generate_cost_report
from klave_engine.costing.reviews import DetectionReview, ProjectReviews
from klave_engine.costing.revision import build_revision_table
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.taxonomy import classify_family
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.dxf.units import DrawingUnits


def _wall(det_id, length, conf=0.9, label=""):
    det = make_detection(
        det_id, DetectionType.wall, det_id, (0, 0, length, 0.15), conf, [], "m", [],
        {"estimated_length": length, "estimated_thickness": 0.15, "wall_kind": "block"},
    )
    det.family = classify_family(det).value
    det.display_label = label
    return det


def _grid(det_id):
    return make_detection(
        det_id, DetectionType.grid_line, "A", (0, 0, 10, 0), 0.95, [], "m", [], {}
    )


def test_rows_cover_money_elements_with_doubts_first_and_verdicts():
    dets = [_wall("w1", 10.0, label="MUR-01"), _wall("w2", 5.0, conf=0.5, label="MUR-02"),
            _wall("w3", 4.0, label="MUR-03"), _grid("g1")]
    seg = SheetSegmentation(
        views=[ViewRegion(view_id="f1", title="ES-100 · PLANTA BAJA", kind=ViewKind.plan,
                          level_key="planta_baja", anchor=(0, 0))],
        assignment={"w1": "f1", "w2": "f1", "w3": "f1"}, is_segmented=False,
    )
    reviews = ProjectReviews(
        detections={"MUR-03": DetectionReview(status="excluded", note="es un pretil", actor="Ana")}
    )
    units = DrawingUnits(unit="m", source="declared", confidence=1.0)
    report = generate_cost_report(
        "p", [d for d in dets if d.display_label != "MUR-03"], units, CostingConfig(), seg, None,
    )
    table = build_revision_table(report, dets, seg, reviews)
    keys = [r.key for r in table.rows]
    assert "g1" not in keys  # grid lines carry no money
    assert keys[0] == "MUR-02" and table.rows[0].doubts == ["confianza 50%"]
    row = {r.key: r for r in table.rows}
    assert row["MUR-01"].concept_code == "EST-004" and row["MUR-01"].measure.startswith("10.00 m")
    assert row["MUR-01"].view_title == "ES-100 · PLANTA BAJA"
    excluded = row["MUR-03"]
    assert excluded.status == "excluded" and excluded.actor == "Ana" and excluded.doubts == []
    assert table.total == 3 and table.with_doubts == 1 and table.excluded == 1
    assert table.concepts[0]["code"] == "" or table.concepts[-1]["code"] == "EST-004"
