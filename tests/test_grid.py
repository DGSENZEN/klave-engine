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
