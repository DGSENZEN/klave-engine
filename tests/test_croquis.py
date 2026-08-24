"""Croquis for the generadores: the sheet render with the line's elements
highlighted, cropped to where they are, cached per run."""

import ezdxf
from klave_engine.common.io import write_json
from klave_engine.costing.croquis import croquis_for_line
from klave_engine.costing.models import BoqLine, QuantityKind
from klave_engine.detection.frames import detect_frames
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.views import SheetSegmentation, ViewKind, ViewRegion
from klave_engine.dxf.parser import DxfParser
from klave_engine.llm.render import Highlight, render_region
from PIL import Image


def _frame(msp, x, y, code, title, w=44.0, h=29.4):
    msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True)
    sx = x + w - 5.7
    msp.add_lwpolyline([(sx, y), (x + w, y), (x + w, y + h), (sx, y + h)], close=True)
    msp.add_text(code, height=0.33).set_placement((sx + 0.3, y + 0.3))
    msp.add_text(title, height=0.12).set_placement((sx + 0.3, y + 2.0))
    for i in range(45):
        msp.add_line((x + 2 + i * 0.5, y + 20), (x + 2 + i * 0.5, y + 24))


def _project(tmp_path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    _frame(msp, 0, 0, "ES-100", "PLANTA BAJA")
    _frame(msp, 50, 0, "ES-200", "PLANTA ALTA")
    path = tmp_path / "sheet.dxf"
    doc.saveas(path)
    entities = DxfParser().parse_file(path).entities
    frames = detect_frames(entities)
    artifact = tmp_path / "run"
    artifact.mkdir()
    write_json(artifact / "normalized_entities.json", entities)
    write_json(artifact / "frames.json", frames)
    control = tmp_path / "processed"
    control.mkdir()
    return entities, frames, artifact, control


def test_highlights_are_drawn_over_the_render():
    pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    plain = render_region([], (0, 0, 10, 10), long_side_px=200)
    marked = render_region(
        [], (0, 0, 10, 10), long_side_px=200,
        highlights=[Highlight(points=[(2, 2), (8, 2), (8, 8), (2, 8)], label="K-1")],
    )
    assert plain.width == marked.width and marked.png != plain.png
    assert pts  # the shape covered the middle of a blank page: a red tint appears
    image = Image.open(__import__("io").BytesIO(marked.png)).convert("RGB")
    r, g, b = image.getpixel((100, 100))
    assert r > g + 30 and r > b + 30


def test_croquis_per_planta_cached_per_run(tmp_path):
    _e, frames, artifact, control = _project(tmp_path)
    by_id = {}
    for i, fx in enumerate((5.0, 55.0)):
        det = make_detection(
            f"c{i}", DetectionType.column_tag, "K-1", (fx, 5.0, fx + 0.2, 5.2), 0.9, [], "m",
            [], {"section_cm": "15x20"},
        )
        det.mark = "K-1"
        by_id[det.detection_id] = det
    segmentation = SheetSegmentation(
        views=[
            ViewRegion(view_id=frames[0].frame_id, title="ES-100 · PLANTA BAJA",
                       kind=ViewKind.plan, level_key="planta_baja", anchor=(0, 0)),
            ViewRegion(view_id=frames[1].frame_id, title="ES-200 · PLANTA ALTA",
                       kind=ViewKind.plan, level_key="planta_alta", anchor=(0, 0)),
        ],
        assignment={"c0": frames[0].frame_id, "c1": frames[1].frame_id},
        is_segmented=True,
    )
    line = BoqLine(
        concept_code="EST-001", description="Castillos", unit="M3", quantity=1.0,
        unit_price=1.0, amount=1.0, phase="estructura", raw_quantity=2, raw_kind=QuantityKind.COUNT,
        source_detection_count=2, source_detections=["c0", "c1"], confidence=0.9,
    )
    out = croquis_for_line(artifact, control, line, by_id, segmentation, frames, run_id="run_a")
    assert [c.title for c in out] == ["ES-100 · PLANTA BAJA", "ES-200 · PLANTA ALTA"]
    assert all(c.path.exists() and c.count == 1 for c in out)
    image = Image.open(out[0].path)
    assert max(image.size) <= 1600
    # The crop keeps at least a third of the sheet: context, not a postage stamp.
    base = Image.open(control / "renders" / "ES-100.png")
    assert image.width * 1600 / max(image.size) >= base.width / 3 * (1600 / max(base.size)) * 0.9
    stamp = out[0].path.stat().st_mtime_ns
    again = croquis_for_line(artifact, control, line, by_id, segmentation, frames, run_id="run_a")
    assert again[0].path.stat().st_mtime_ns == stamp  # cached
    other = croquis_for_line(artifact, control, line, by_id, segmentation, frames, run_id="run_b")
    assert other[0].path != out[0].path  # another run renders its own


def test_frameless_drawing_renders_from_entities(tmp_path):
    entities, _frames, artifact, control = _project(tmp_path)
    det = make_detection(
        "w1", DetectionType.wall, "M", (5.0, 5.0, 15.0, 5.15), 0.9, [], "m", [],
        {"estimated_length": 10.0},
    )
    line = BoqLine(
        concept_code="EST-004", description="Muros", unit="M2", quantity=1.0, unit_price=1.0,
        amount=1.0, phase="estructura", raw_quantity=10, raw_kind=QuantityKind.LENGTH,
        source_detection_count=1, source_detections=["w1"], confidence=0.9,
    )
    out = croquis_for_line(artifact, control, line, {"w1": det}, None, [], run_id="run_a")
    assert len(out) == 1 and out[0].title == "Plano completo" and out[0].path.exists()


def test_the_croquis_provider_actually_reaches_the_workbook():
    """It did not: build_presupuesto_workbook accepted a provider and dropped
    it, so every Generadores sheet shipped without the evidence images that
    make a quantity checkable."""
    from klave_engine.costing.exports import build_presupuesto_workbook
    from klave_engine.costing.reviews import ProjectReviews

    from tests.test_hallazgos import _line, _report

    asked: list[str] = []

    def provider(line):
        asked.append(line.concept_code)
        return []

    report = _report([_line("EST-002")])
    report.boq.lines[0].source_detections = ["det_1"]
    build_presupuesto_workbook(
        report, [], ProjectReviews(), project_name="Obra", client=None,
        croquis=provider,
    )
    assert asked == ["EST-002"]
