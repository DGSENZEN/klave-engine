"""The crop that makes an AI reading checkable: found in the drawing's own
text, never asked of the model."""

import ezdxf
from klave_engine.detection.frames import detect_frames
from klave_engine.dxf.parser import DxfParser
from klave_engine.llm.evidencia import crop_from_frame_render, find_mark_region
from klave_engine.llm.render import render_region


def _draw_frame(msp, x: float, code: str, w: float = 44.0, h: float = 29.4) -> None:
    msp.add_lwpolyline([(x, 0), (x + w, 0), (x + w, h), (x, h)], close=True)
    sx = x + w - 5.7
    msp.add_lwpolyline([(sx, 0), (x + w, 0), (x + w, h), (sx, h)], close=True)
    msp.add_text(code, height=0.33).set_placement((sx + 0.3, 0.3))
    msp.add_text("PLANTA", height=0.12).set_placement((sx + 0.3, 2.0))
    for i in range(45):  # linework, so the frame reads as a plan
        msp.add_line((x + 2 + i * 0.5, 20), (x + 2 + i * 0.5, 24))


def _sheet(tmp_path, marks: list[tuple[str, float, float]]):
    """A drawing of two sheet frames; the marks go in the first."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    _draw_frame(msp, 0.0, "ES-100")
    _draw_frame(msp, 50.0, "ES-101")
    for text, x, y in marks:
        msp.add_text(text, height=0.2).set_placement((x, y))
    path = tmp_path / "sheet.dxf"
    doc.saveas(path)
    entities = DxfParser().parse_file(path).entities
    frames = detect_frames(entities)
    return entities, next(f for f in frames if f.code == "ES-100")


def test_the_crop_lands_where_the_mark_is_written(tmp_path):
    entities, frame = _sheet(tmp_path, [("K-1", 5.0, 10.0), ("T-2", 30.0, 5.0)])
    region = find_mark_region(entities, frame, "K-1")
    assert region is not None
    x0, y0, x1, y1 = region
    assert x0 <= 5.0 <= x1 and y0 <= 10.0 <= y1
    assert not (x0 <= 30.0 <= x1 and y0 <= 5.0 <= y1)  # the other mark is elsewhere


def test_a_mark_matches_as_a_whole_token(tmp_path):
    """K-1 must not be found inside K-15: a crop of the wrong element is
    worse than no crop, because it looks like confirmation."""
    entities, frame = _sheet(tmp_path, [("K-15", 5.0, 10.0)])
    assert find_mark_region(entities, frame, "K-1") is None
    assert find_mark_region(entities, frame, "K-15") is not None


def test_the_crop_prefers_where_the_reported_values_appear_beside_the_mark(tmp_path):
    """The model claimed K-1 is 15x20. The sheet writes K-1 twice — once bare
    in the planta, once in the cuadro next to its section. The useful crop is
    the second: it shows the claim and its evidence together."""
    entities, frame = _sheet(
        tmp_path,
        [("K-1", 4.0, 24.0), ("K-1", 30.0, 6.0), ("15x20", 31.5, 6.0), ("4#3", 33.0, 6.0)],
    )
    plain = find_mark_region(entities, frame, "K-1")
    corroborated = find_mark_region(entities, frame, "K-1", ["15x20", "4#3"])
    assert plain is not None and corroborated is not None
    x0, y0, x1, y1 = corroborated
    assert x0 <= 30.0 <= x1 and y0 <= 6.0 <= y1  # the cuadro, not the bare tag
    assert corroborated != plain


def test_an_absent_mark_yields_nothing_rather_than_a_guess(tmp_path):
    entities, frame = _sheet(tmp_path, [("K-1", 5.0, 10.0)])
    assert find_mark_region(entities, frame, "CTA-9") is None
    assert find_mark_region(entities, frame, "") is None
    assert find_mark_region(entities, frame, "X") is None  # too short to be a mark


def test_the_crop_is_a_real_image_of_that_region(tmp_path):
    entities, frame = _sheet(tmp_path, [("K-1", 5.0, 10.0)])
    render = render_region(entities, frame.bbox, long_side_px=1200)
    path = tmp_path / "ES-100.png"
    path.write_bytes(render.png)

    region = find_mark_region(entities, frame, "K-1")
    png = crop_from_frame_render(path, frame, region, long_side_px=1200)
    assert png is not None and png[:8] == b"\x89PNG\r\n\x1a\n"

    # A render made with other settings is refused: a stale crop would point
    # at the wrong place while looking authoritative.
    assert crop_from_frame_render(path, frame, region, long_side_px=800) is None
