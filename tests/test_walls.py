"""Walls: layer authority, real thickness, and fragments merged into one wall."""

import ezdxf
from klave_engine.detection.wall_detector import WallDetectorConfig, detect_walls
from klave_engine.dxf.parser import DxfParser
from klave_engine.geometry.spatial_index import SpatialIndex

CONFIG = WallDetectorConfig(
    min_length=1.5, max_thickness=0.45, min_thickness=0.05, merge_gap=0.30
)


def _walls(tmp_path, build, config=CONFIG):
    doc = ezdxf.new("R2010")
    build(doc.modelspace())
    path = tmp_path / "walls.dxf"
    doc.saveas(path)
    drawing = DxfParser().parse_file(path)
    return detect_walls(drawing.entities, SpatialIndex(drawing.entities), config)


def _pair(msp, x0, x1, y, thickness, layer):
    msp.add_line((x0, y), (x1, y), dxfattribs={"layer": layer})
    msp.add_line((x0, y + thickness), (x1, y + thickness), dxfattribs={"layer": layer})


def test_fragments_merge_and_non_walls_are_refused(tmp_path):
    def build(msp):
        # One 10 m wall drawn as three fragments (axis breaks), 15 cm thick.
        _pair(msp, 0.0, 3.0, 0.0, 0.15, "A-WALL")
        _pair(msp, 3.1, 6.5, 0.0, 0.15, "A-WALL")
        _pair(msp, 6.6, 10.0, 0.0, 0.15, "A-WALL")
        # A door opening (1.2 m) separates the next wall.
        _pair(msp, 11.2, 15.0, 0.0, 0.15, "A-WALL")
        # Two grid axes 25 cm apart: never a wall.
        _pair(msp, 0.0, 20.0, 5.0, 0.25, "S-GRID")
        # The same line twice (block + model): 0.0 apart, not a wall.
        _pair(msp, 0.0, 8.0, 8.0, 0.004, "A-WALL")
        # A border pair on another layer: ignored while wall layers exist.
        _pair(msp, 0.0, 30.0, 12.0, 0.2, "bordes")

    output = _walls(tmp_path, build)
    walls = sorted(output.detections, key=lambda d: d.bbox[0])
    assert len(walls) == 2
    first, second = walls
    assert first.properties["segment_count"] == 3
    assert abs(first.properties["estimated_length"] - 10.0) < 1e-6
    assert abs(first.properties["estimated_thickness"] - 0.15) < 1e-6
    assert first.properties["layer"] == "A-WALL"
    assert second.properties["estimated_length"] == 3.8
    assert any("se ignoraron" in w for w in output.warnings)


def test_without_wall_layers_any_plausible_pair_counts(tmp_path):
    def build(msp):
        _pair(msp, 0.0, 6.0, 0.0, 0.12, "0")
        _pair(msp, 0.0, 6.0, 4.0, 0.12, "0")

    output = _walls(tmp_path, build)
    assert len(output.detections) == 2
    assert all(d.properties["estimated_thickness"] == 0.12 for d in output.detections)
