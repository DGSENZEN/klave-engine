"""Without a reliable unit the engine measures in drawing units and prices
nothing — on screen and in every export — while the detectors still use
thresholds that fit the drawing's extent."""

import io

from klave_engine.costing.exports import IVA_PCT, SIN_UNIDADES, UNPRICED, build_presupuesto_workbook
from klave_engine.costing.models import CostingConfig
from klave_engine.costing.report import generate_cost_report
from klave_engine.costing.reviews import ProjectReviews
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.suite import DetectorSuiteConfig
from klave_engine.detection.taxonomy import classify_family
from klave_engine.dxf.units import DrawingUnits
from openpyxl import load_workbook

from tests.precios import LIBRO


def _wall(det_id, length):
    det = make_detection(
        det_id, DetectionType.wall, det_id, (0, 0, length, 0.15), 0.9, [], "m", [],
        {"estimated_length": length, "estimated_thickness": 0.15, "wall_kind": "block"},
    )
    det.family = classify_family(det).value
    return det


def test_unknown_units_mean_no_price_anywhere():
    units = DrawingUnits(unit="drawing_units", source="unknown", confidence=0.0)
    report = generate_cost_report("p", [_wall("w1", 1000.0)], units, CostingConfig(), None, None,
        price_book=LIBRO,
    )
    assert not report.boq.units_reliable
    assert report.boq.lines and all(ln.unpriced and ln.amount == 0.0 for ln in report.boq.lines)
    assert report.boq.direct_cost_total == 0.0 and report.integration.grand_total == 0.0
    assert any(w.startswith("SIN UNIDADES") for w in report.boq.warnings)
    for fmt in ("klave", "opus", "licitacion"):
        content = build_presupuesto_workbook(report, [], ProjectReviews(), "Obra", None, fmt=fmt)
        cells = [
            c.value for ws in load_workbook(io.BytesIO(content)).worksheets
            for row in ws.iter_rows() for c in row
        ]
        assert SIN_UNIDADES in cells, fmt


def _labeled_value(ws, label: str, label_col: int, value_col: int):
    """The value beside a summary label, e.g. the amount next to 'TOTAL'.

    Scoped lookups by label+column rather than "is this number anywhere in
    the workbook", because a workbook has many sheets (Programa, Flujo...)
    that may legitimately echo a running total elsewhere — checking the
    exact labeled cell is what actually proves a specific site was gated.
    """
    for row in ws.iter_rows():
        if row[label_col - 1].value == label:
            return row[value_col - 1].value
    raise AssertionError(f"no row labeled {label!r} in sheet {ws.title!r}")


def test_a_priced_but_unconfirmed_report_shows_no_total_in_the_workbook():
    """units_reliable=True here — the engine priced this run for real,
    unlike the fully-unknown-unit case above where grand_total is already
    zero at the source (so asserting its absence there would hold even with
    no gate at all). Confidence sits under CONFIDENCE_FIRM (0.3 < 0.7) with
    no human confirmation, so resolve_money_state still says "blocked" —
    this is the shape that actually proves the three summary cells stop
    leaking a real, nonzero total under their own SIN UNIDADES/SIN VERIFICAR
    banner, in every one of the three functions Task 3 threads money_state
    through."""
    units = DrawingUnits(unit="m", source="dxf_header", confidence=0.3)
    report = generate_cost_report(
        "p", [_wall("w1", 10.0)], units, CostingConfig(), None, None, price_book=LIBRO,
    )
    assert report.boq.units_reliable  # the engine priced it — a real total exists to hide
    assert report.integration.grand_total > 0

    klave = load_workbook(io.BytesIO(
        build_presupuesto_workbook(report, [], ProjectReviews(), "Obra", None, fmt="klave")
    ))
    assert _labeled_value(klave["Carátula"], "Total con contingencia", 1, 2) == UNPRICED
    assert _labeled_value(klave["Presupuesto"], "TOTAL", 5, 6) == UNPRICED

    licitacion = load_workbook(io.BytesIO(
        build_presupuesto_workbook(report, [], ProjectReviews(), "Obra", None, fmt="licitacion")
    ))
    ws = licitacion["Catálogo de conceptos"]
    assert _labeled_value(ws, "SUBTOTAL", 3, 8) == UNPRICED
    assert _labeled_value(ws, f"I.V.A. {IVA_PCT:.0f} %", 3, 8) == UNPRICED
    assert _labeled_value(ws, "TOTAL", 3, 8) == UNPRICED
    # The spelled-out total is the same number in another alphabet: blanking
    # the digits while this cell still reads "...con letra: Setecientos
    # ses.." below them would be the fix undoing itself one row down.
    assert not any(
        isinstance(c.value, str) and c.value.startswith("Importe total con letra")
        for row in ws.iter_rows() for c in row
    )


def test_a_lone_heuristic_is_not_enough_to_price():
    units = DrawingUnits(unit="cm", source="text_height_heuristic", confidence=0.5)
    report = generate_cost_report("p", [_wall("w1", 1000.0)], units, CostingConfig(), None, None,
        price_book=LIBRO,
    )
    assert not report.boq.units_reliable and report.boq.direct_cost_total == 0.0


def test_detector_thresholds_follow_the_extent_when_units_are_unknown():
    unknown = DrawingUnits(unit="drawing_units", source="unknown", confidence=0.0)
    generic = DetectorSuiteConfig.preset_for_units(unknown)
    in_cm = DetectorSuiteConfig.preset_for_units(unknown, extent=(0.0, 0.0, 3000.0, 2000.0))
    declared_cm = DetectorSuiteConfig.preset_for_units(
        DrawingUnits(unit="cm", source="dxf_header", confidence=1.0)
    )
    assert in_cm.model_dump() == declared_cm.model_dump()
    assert in_cm.model_dump() != generic.model_dump()
