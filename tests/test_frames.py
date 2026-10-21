"""Sheet frames as views; frames and casetones never become slabs or zapatas."""

import ezdxf
import pytest
from klave_engine.common.ids import IdGenerator
from klave_engine.detection.footing_detector import FootingDetectorConfig, detect_footings
from klave_engine.detection.frames import detect_frames
from klave_engine.detection.results import DetectionType, make_detection
from klave_engine.detection.slab_detector import SlabDetectorConfig, detect_slabs
from klave_engine.detection.views import segment_views
from klave_engine.dxf.parser import DxfParser
from klave_engine.geometry.spatial_index import SpatialIndex


def _frame(msp, x, y, code, title, w=44.0, h=29.4):
    msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True,
                       dxfattribs={"layer": "ESTRUCTURAL"})
    sx = x + w - 5.7
    msp.add_lwpolyline([(sx, y), (x + w, y), (x + w, y + h), (sx, y + h)], close=True,
                       dxfattribs={"layer": "ESTRUCTURAL"})
    msp.add_text(code, height=0.33).set_placement((sx + 0.3, y + 0.3))
    msp.add_text(title, height=0.12).set_placement((sx + 0.3, y + 2.0))
    msp.add_text("RESIDENCIA LOTE 04", height=0.28).set_placement((sx + 0.3, y + 3.0))
    # A sheet has content: forty-odd lines of linework inside the frame.
    for i in range(45):
        msp.add_line((x + 2 + i * 0.5, y + 20), (x + 2 + i * 0.5, y + 24),
                     dxfattribs={"layer": "EST-EJES"})


def _entities(tmp_path, build):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    build(doc.modelspace())
    path = tmp_path / "frames.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path).entities


def test_frames_become_views_and_are_never_slabs(tmp_path):
    def build(msp):
        _frame(msp, 0, 0, "ES-100", "PLANTA DE CIMENTACIÓN")
        _frame(msp, 50, 0, "ES-101", "PLANTA ESTRUCTURAL NIVEL 1")
        _frame(msp, 100, 0, "ES-500", "DETALLES DE ESTRUCTURA DE PLANTA BAJA")
        # A real slab inside frame 2 (8×6 m) and a casetón grid in frame 3.
        msp.add_lwpolyline([(55, 5), (63, 5), (63, 11), (55, 11)], close=True,
                           dxfattribs={"layer": "EST-LOSA"})
        for i in range(3):
            msp.add_lwpolyline([(105 + i, 5), (105.6 + i, 5), (105.6 + i, 5.6), (105 + i, 5.6)],
                               close=True, dxfattribs={"layer": "EST-LOSA NERVADA"})
        msp.add_lwpolyline([(5, 5), (6.2, 5), (6.2, 6.2), (5, 6.2)], close=True,
                           dxfattribs={"layer": "EST-ZAPATAS"})

    entities = _entities(tmp_path, build)
    frames = detect_frames(entities)
    assert [f.code for f in frames] == ["ES-100", "ES-101", "ES-500"]
    assert [f.kind for f in frames] == ["plan", "plan", "excluded"]
    assert frames[0].level_key == "cimentacion" and frames[1].level_key == "nivel_1"

    slabs = detect_slabs(
        entities, SlabDetectorConfig(min_area=16.0), IdGenerator("slab"),
        frame_boxes=[f.bbox for f in frames],
    )
    assert len(slabs.detections) == 1 and slabs.detections[0].properties["estimated_area"] == 48.0
    assert any("marco" in w for w in slabs.warnings)

    index = SpatialIndex(entities)
    footings = detect_footings(
        entities, index, None, FootingDetectorConfig(min_area=0.3, max_area=30.0),
        IdGenerator("zap"),
    )
    assert len(footings.detections) == 1  # casetones on EST-LOSA NERVADA are not zapatas

    dets = slabs.detections + footings.detections + [
        make_detection("x", DetectionType.column_tag, "K-1", (101, 1, 101.5, 1.5), 0.9, [], "m", [])
    ]
    seg = segment_views(entities, dets, frames)
    assert seg.is_segmented
    titles = {v.view_id: v.title for v in seg.views}
    assert seg.assignment[footings.detections[0].detection_id] == "frame_00"
    assert seg.assignment[slabs.detections[0].detection_id] == "frame_01"
    assert seg.assignment["x"] == "frame_02" and "ES-500" in titles["frame_02"]
    assert [v.level_key for v in seg.foundation_views()] == ["cimentacion"]


def test_no_repeated_frames_means_no_frames(tmp_path):
    def build(msp):
        _frame(msp, 0, 0, "ES-100", "PLANTA")
        msp.add_lwpolyline([(60, 0), (80, 0), (80, 10), (60, 10)], close=True)

    assert detect_frames(_entities(tmp_path, build)) == []


def test_frames_hold_only_their_own_file(tmp_path):
    """Two files share model-space coordinates; a detection from file B at a
    point inside file A's frame is not file A's content."""
    entities = _entities(tmp_path, lambda msp: (
        _frame(msp, 0, 0, "ES-100", "PLANTA DE CIMENTACIÓN"),
        _frame(msp, 50, 0, "ES-101", "PLANTA ESTRUCTURAL NIVEL 1"),
    ))
    frames = detect_frames(entities)
    for f in frames:
        f.source_file = "a.dxf"
    inside_a = make_detection(
        "x", DetectionType.slab_region, "S", (5, 5, 6, 6), 0.9, [], "m", [],
        {"estimated_area": 1.0}, "a.dxf",
    )
    from_b = make_detection(
        "y", DetectionType.slab_region, "S", (5, 5, 6, 6), 0.9, [], "m", [],
        {"estimated_area": 1.0}, "b.dxf",
    )
    seg = segment_views(entities, [inside_a, from_b], frames)
    assert seg is not None
    assert seg.assignment["x"] == frames[0].frame_id
    assert seg.assignment["y"] == "outside_frames"


def test_lo_lejano_de_todo_titulo_queda_excluido(tmp_path):
    # Camino de anclas por título (sin marcos): una detección a 10 m del
    # título se atribuye; una a 400 m de todos queda excluida, no adoptada.
    def build(msp):
        for i in range(8):
            msp.add_text("nota chica", height=0.2).set_placement((i, -5))
        msp.add_text("PLANTA BAJA", height=1.0).set_placement((0, 30))
        msp.add_text("PLANTA ALTA", height=1.0).set_placement((50, 30))

    entities = _entities(tmp_path, build)
    cerca = make_detection(
        "d1", DetectionType.column_tag, "K-1", (5, 25, 5.5, 25.5), 0.9, [], "m", []
    )
    lejos = make_detection(
        "d2", DetectionType.column_tag, "K-2", (400, 400, 400.5, 400.5), 0.9, [], "m", []
    )
    seg = segment_views(entities, [cerca, lejos], [])
    assert seg.is_segmented
    assigned = seg.assignment["d1"]
    assert seg.assignment["d2"] == "far_from_titles"
    far = next(v for v in seg.views if v.view_id == "far_from_titles")
    assert far.kind.value == "excluded"
    assert assigned != "far_from_titles"


def _muro(msp, puntos):
    """Un muro en trazos de 1 m: ninguno tan largo como para unir dos dibujos de la hoja."""
    for (x0, y0), (x1, y1) in zip(puntos, puntos[1:], strict=False):
        n = max(1, round(max(abs(x1 - x0), abs(y1 - y0))))
        for i in range(n):
            a = (x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n)
            b = (x0 + (x1 - x0) * (i + 1) / n, y0 + (y1 - y0) * (i + 1) / n)
            msp.add_line(a, b, dxfattribs={"layer": "MUROS"})


def _k(detection_id, x, y):
    caja = (x - 0.1, y - 0.1, x + 0.1, y + 0.1)
    return make_detection(detection_id, DetectionType.column_tag, "K-1", caja, 0.9, [], "m", [])


@pytest.mark.parametrize("con_muro", [True, False])
def test_a_near_tie_between_two_titles_is_decided_by_the_drawing(tmp_path, con_muro):
    # R165 (PRUEBA-1, sin marcos): un castillo casi igual de cerca de dos títulos (11.24 contra
    # 11.59, menos de 10 %) no se decide por el centro de los títulos: es de la planta cuyo dibujo
    # toca (el muro donde están los castillos que sí son claramente de PLANTA BAJA). Sin dibujo que
    # lo diga, se queda en el título más cercano y lo dice: «vista dudosa».
    def build(msp):
        for i in range(8):
            msp.add_text("nota chica", height=0.2).set_placement((i, -5))
        msp.add_text("PLANTA BAJA", height=1.0).set_placement((0, 0))
        msp.add_text("PLANTA ALTA", height=1.0).set_placement((20, 0))
        if con_muro:
            _muro(msp, [(2, 4), (13.6, 4), (13.6, 8), (2, 8), (2, 4)])

    entities = _entities(tmp_path, build)
    seg = segment_views(entities, [_k("a", 3.0, 4.0), _k("b", 5.0, 8.0), _k("t", 13.5, 6.0)], [])
    titulos = {v.view_id: v.title for v in seg.views}
    # Los títulos se ubican como antes (su caja de 0.6 altos por letra desde su inserción), no en
    # su centro real (4.95): mover el centro no mueve las vistas.
    assert sorted(v.anchor for v in seg.views) == [(3.3, 0.5), (23.3, 0.5)]
    assert titulos[seg.assignment["a"]] == titulos[seg.assignment["b"]] == "PLANTA BAJA"
    if con_muro:
        assert titulos[seg.assignment["t"]] == "PLANTA BAJA"
        assert seg.vistas_dudosas == {}
    else:
        assert titulos[seg.assignment["t"]] == "PLANTA ALTA"
        assert seg.vistas_dudosas == {
            "t": "vista dudosa: casi igual de cerca de «PLANTA ALTA» y de «PLANTA BAJA», y su "
            "dibujo no dice de cuál es (0 contra 0); se deja en «PLANTA ALTA»"
        }
        assert "1 detecciones en vista dudosa" in seg.notes
