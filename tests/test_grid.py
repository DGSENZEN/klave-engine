"""Grid axes: semantic-layer authority, fragment merging, labels by bubble
and by sequence, and per-sheet intersections."""

import ezdxf
from klave_engine.detection.grid_detector import GridDetectorConfig, detect_grid
from klave_engine.dxf.parser import DxfParser
from klave_engine.geometry.spatial_index import SpatialIndex


def _detect(path, config=None):
    drawing = DxfParser().parse_file(path)
    index = SpatialIndex(drawing.entities)
    config = config or GridDetectorConfig(min_relative_length=0.2)
    return detect_grid(drawing.entities, index, config)


def test_fragments_merge_into_labeled_axes(tmp_path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    # Axis A: three fragments broken by bubble gaps, on the grid layer.
    for a, b in ((0, 30), (32, 60), (61, 100)):
        msp.add_line((a, 0), (b, 0), dxfattribs={"layer": "S-GRID"})
    msp.add_text("A", height=1.0).set_placement((-3, 0))
    # An unlabeled axis between A and C.
    msp.add_line((0, 10), (100, 10), dxfattribs={"layer": "S-GRID"})
    msp.add_line((0, 20), (100, 20), dxfattribs={"layer": "S-GRID"})
    msp.add_text("C", height=1.0).set_placement((-3, 20))
    # Vertical axis 1, and axis 2 split by a view-sized gap (two plan views).
    msp.add_line((0, 0), (0, 100), dxfattribs={"layer": "S-GRID"})
    msp.add_text("1", height=1.0).set_placement((0, -3))
    msp.add_line((50, 0), (50, 40), dxfattribs={"layer": "S-GRID"})
    msp.add_line((50, 70), (50, 100), dxfattribs={"layer": "S-GRID"})
    msp.add_text("2", height=1.0).set_placement((50, -3))
    msp.add_text("2", height=1.0).set_placement((50, 103))  # the second view's bubble
    # A long architectural wall line: not an axis on a sheet that has a grid layer.
    msp.add_line((0, 5), (100, 5), dxfattribs={"layer": "A-WALL"})
    path = tmp_path / "grid.dxf"
    doc.saveas(path)

    output = _detect(path)
    axes = {d.label: d for d in output.detections if d.detection_type.value == "grid_line"}
    labels = sorted(d.label for d in output.detections if d.detection_type.value == "grid_line")
    assert labels == ["1", "2", "2", "A", "B", "C"]
    assert axes["A"].properties["fragment_count"] == 3
    assert axes["A"].properties["label_source"] == "bubble"
    assert axes["B"].properties["label_source"] == "sequence"
    assert "secuencia" in " ".join(axes["B"].evidence.notes)
    assert axes["A"].bbox[0] == 0.0 and axes["A"].bbox[2] == 100.0
    assert any("se descartaron como ejes" in w for w in output.warnings)

    intersections = sorted(
        d.label for d in output.detections if d.detection_type.value == "grid_intersection"
    )
    # Both halves of axis 2 are separate axes; only the first (y∈[0,40])
    # crosses A, B and C, so every crossing appears exactly once.
    assert intersections == ["A/1", "A/2", "B/1", "B/2", "C/1", "C/2"]


def test_without_grid_layer_unlabeled_long_lines_still_count(tmp_path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0))
    msp.add_line((0, 50), (100, 50))
    msp.add_line((0, 0), (0, 50))
    path = tmp_path / "plain.dxf"
    doc.saveas(path)

    output = _detect(path)
    labels = sorted(d.label for d in output.detections if d.detection_type.value == "grid_line")
    assert labels == ["H1", "H2", "V1"]
    auto = next(d for d in output.detections if d.label == "H1")
    assert auto.properties["label_source"] == "auto"
    assert auto.evidence.notes[0].startswith("No grid label found")  # taxonomy relies on it


def test_ejes_por_marco_en_hoja_mosaicada(tmp_path):
    # Dos marcos de 40×30 mosaicados en model space (como el estructural de
    # Marina): los ejes miden ~26 m — la mitad del marco, pero una fracción
    # del extent del archivo. Sin marcos no pasan el umbral; con marcos, sí.
    from klave_engine.detection.frames import SheetFrame

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for ox in (0.0, 60.0):  # dos plantas lado a lado
        for i in range(3):
            x = ox + 5 + i * 12
            msp.add_line((x, 2), (x, 28), dxfattribs={"layer": "EJES"})
            msp.add_text(str(i + 1), height=1.0).set_placement((x, -1))
        for j in range(2):
            y = 5 + j * 18
            msp.add_line((ox + 2, y), (ox + 38, y), dxfattribs={"layer": "EJES"})
            msp.add_text(chr(65 + j), height=1.0).set_placement((ox - 2, y))
    path = tmp_path / "mosaico.dxf"
    doc.saveas(path)

    drawing = DxfParser().parse_file(path)
    index = SpatialIndex(drawing.entities)
    frames = [
        SheetFrame(frame_id="frame_00", bbox=(0.0, 0.0, 40.0, 30.0),
                   source_file=drawing.entities[0].source_file, code="ES-000"),
        SheetFrame(frame_id="frame_01", bbox=(60.0, 0.0, 100.0, 30.0),
                   source_file=drawing.entities[0].source_file, code="ES-100"),
    ]
    config = GridDetectorConfig()  # el default 0.5 relativo: el caso real

    sin_marcos = detect_grid(drawing.entities, index, config)
    con_marcos = detect_grid(drawing.entities, index, config, frames=frames)

    def ejes(output):
        return [d for d in output.detections if d.detection_type.value == "grid_line"]

    # La caracterización del bug: contra el extent del archivo ningún eje
    # horizontal de 36 m pasa (umbral ~51 m); contra su marco, todos pasan.
    assert len(ejes(sin_marcos)) < len(ejes(con_marcos))
    assert len(ejes(con_marcos)) == 10  # (3 verticales + 2 horizontales) × 2 marcos
    # Los ejes de marcos distintos nunca se funden en uno.
    for det in ejes(con_marcos):
        x0, _, x1, _ = det.bbox
        assert x1 <= 40.5 or x0 >= 59.5
