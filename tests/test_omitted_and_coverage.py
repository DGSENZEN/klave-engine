"""Recall tooling: omitted elements become priced lines with perito
provenance, and the coverage audit flags sheets where the model counts
more than the engine detected."""

from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import CostingAssumptions
from klave_engine.costing.omitted import synthetic_detections
from klave_engine.costing.reviews import OmittedElement, ProjectReviews
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection, DetectionType
from klave_engine.dxf.units import DrawingUnits
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.llm.coverage import coverage_flags
from klave_engine.llm.reader import SheetRead


def _omitted(family: str, **kwargs) -> OmittedElement:
    return OmittedElement(element_id="om_x1", family=family, **kwargs)


def test_synthetic_castillos_carry_perito_provenance():
    dets = synthetic_detections(
        [_omitted("castillo", mark="K-7", count=3, section_cm="15x15", actor="Diego")],
        unit_to_m=1.0,
    )
    assert len(dets) == 3
    assert {d.detection_type for d in dets} == {DetectionType.column_tag}
    assert all(d.confidence == 1.0 for d in dets)
    assert all(d.family == "castillo" and d.mark == "K-7" for d in dets)
    assert all(d.evidence.method == "levantamiento_manual" for d in dets)
    assert all(d.properties["section_cm"] == "15x15" for d in dets)
    assert "Diego" in dets[0].evidence.notes[0]
    # Unique, stable ids and labels: deletable, reviewable, re-runnable.
    assert len({d.detection_id for d in dets}) == 3
    assert len({d.display_label for d in dets}) == 3


def test_omitted_trabe_prices_like_a_detected_one():
    """12 m of missed trabe 30x80 must add exactly 12 × 0.24 m³ of concrete."""
    omitted = [_omitted("trabe", mark="T-9", count=2, length_m=12.0, section_cm="30x80")]
    dets = synthetic_detections(omitted, unit_to_m=1.0)
    assert all(abs(d.properties["estimated_span_length"] - 6.0) < 1e-9 for d in dets)

    assumptions = CostingAssumptions()
    catalog = [c for c in build_default_catalog(assumptions) if c.code == "EST-002"]
    boq = generate_bill_of_quantities(
        "t", dets, DrawingUnits(unit="m", source="declared", confidence=1.0),
        catalog, build_all_apus(catalog), assumptions=assumptions,
    )
    line = next(line for line in boq.lines if line.concept_code == "EST-002")
    assert abs(line.quantity - 12.0 * 0.24) < 1e-6
    assert line.source_detection_count == 2


def test_measures_convert_to_drawing_units_at_synthesis():
    """A cm drawing stores the span in cm, so a later unit confirmation
    re-derives the same meters."""
    dets = synthetic_detections(
        [_omitted("trabe", length_m=12.0, count=2)], unit_to_m=0.01
    )
    assert all(abs(d.properties["estimated_span_length"] - 600.0) < 1e-9 for d in dets)
    areas = synthetic_detections([_omitted("losa", area_m2=50.0)], unit_to_m=0.01)
    assert abs(areas[0].properties["estimated_area"] - 500_000.0) < 1e-6


def test_wall_kind_and_unknown_families():
    concreto = synthetic_detections(
        [_omitted("muro_concreto", length_m=8.0)], unit_to_m=1.0
    )
    assert concreto[0].properties["wall_kind"] == "concreto"
    assert concreto[0].properties["estimated_length"] == 8.0
    # A reviews file from a newer version with a family this build ignores.
    assert synthetic_detections([_omitted("acabado_futuro")], unit_to_m=1.0) == []


def test_reviews_roundtrip_keeps_omitted():
    reviews = ProjectReviews(omitted=[_omitted("zapata", area_m2=4.0)])
    again = ProjectReviews.model_validate(reviews.model_dump(mode="json"))
    assert again.omitted[0].family == "zapata"
    assert again.omitted[0].area_m2 == 4.0
    # Old reviews files (no "omitted" key) still load.
    assert ProjectReviews.model_validate({"detections": {}}).omitted == []


def test_omitted_survives_view_scoping_on_segmented_sheets():
    """The original bug: segmented sheets scope quantities per view, and a
    synthetic detection (no bbox, no view assignment) was silently dropped."""
    from klave_engine.detection.results import make_detection
    from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion

    drawn = make_detection(
        "b1", DetectionType.beam_tag, "T-1", (0, 0, 1, 1), 0.9, [], "m", [],
        {"estimated_span_length": 4.0, "section_cm": "30x80", "family": "trabe"},
    )
    drawn.family = "trabe"
    seg = SheetSegmentation(
        views=[
            ViewRegion(view_id="f1", title="ES-100 · PLANTA BAJA", kind=ViewKind.plan,
                       level_key="planta_baja", anchor=(0, 0)),
        ],
        assignment={"b1": "f1"},
        is_segmented=True,
    )
    synthetic = synthetic_detections(
        [_omitted("trabe", mark="T-9", count=2, length_m=12.0, section_cm="30x80")],
        unit_to_m=1.0,
    )
    assumptions = CostingAssumptions()
    catalog = [c for c in build_default_catalog(assumptions) if c.code == "EST-002"]
    boq = generate_bill_of_quantities(
        "t", [drawn] + synthetic, DrawingUnits(unit="m", source="declared", confidence=1.0),
        catalog, build_all_apus(catalog), segmentation=seg, assumptions=assumptions,
    )
    line = next(line for line in boq.lines if line.concept_code == "EST-002")
    # 4 m drawn + 12 m manual, all at 30x80.
    assert abs(line.quantity - 16.0 * 0.24) < 1e-6
    assert any("levantamiento" in a.lower() for a in line.assumptions)


# ---------------------------------------------------------------- coverage


def _det(det_id: str, family: str, x: float, y: float, source: str = "E-01.dxf") -> Detection:
    return Detection(
        detection_id=det_id,
        detection_type=DetectionType.column_tag,
        label="K-1",
        bbox=(x, y, x + 1.0, y + 1.0),
        confidence=0.9,
        evidence=EvidencePacket(source=source, method="test"),
        family=family,
    )


def _frame(code: str, bbox=(0.0, 0.0, 100.0, 100.0)) -> SheetFrame:
    return SheetFrame(frame_id=code, bbox=bbox, source_file="E-01.dxf", code=code)


def _reading(code: str, conteo: list[dict]) -> dict:
    return {"frame_code": code, "read": {"conteo": conteo}}


def test_coverage_flags_the_recall_direction_first():
    detections = [_det(f"d{i}", "castillo", 10.0 * i, 10.0) for i in range(4)]
    detections += [_det("z1", "zapata", 5.0, 50.0), _det("z2", "zapata", 15.0, 50.0)]
    flags = coverage_flags(
        [_reading("E-01", [
            {"family": "castillo", "drawn_count": 6},
            {"family": "zapata", "drawn_count": 1},
            {"family": "muro", "drawn_count": 3},  # continuous: never compared
        ])],
        detections,
        [_frame("E-01")],
    )
    assert [(f.family, f.kind, f.ai_count, f.engine_count) for f in flags] == [
        ("castillo", "faltante", 6, 4),
        ("zapata", "sobrante", 1, 2),
    ]


def test_coverage_counts_only_inside_the_frame_and_file():
    detections = [
        _det("in", "castillo", 10.0, 10.0),
        _det("outside", "castillo", 500.0, 500.0),
        _det("other_file", "castillo", 10.0, 20.0, source="E-02.dxf"),
    ]
    flags = coverage_flags(
        [_reading("E-01", [{"family": "castillo", "drawn_count": 1}])],
        detections,
        [_frame("E-01")],
    )
    assert flags == []  # 1 == 1: agreement is silence


def test_coverage_survives_empty_and_unknown_frames():
    assert coverage_flags([], [], []) == []
    assert coverage_flags(
        [_reading("NO-SUCH", [{"family": "castillo", "drawn_count": 2}])], [], []
    ) == []
    assert coverage_flags([_reading("E-01", [])], [], [_frame("E-01")]) == []


def test_sheet_read_backcompat_without_conteo():
    read = SheetRead.model_validate({"elements": [], "notes": ["ok"]})
    assert read.conteo == []
