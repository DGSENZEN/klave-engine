"""Geometry helper tests: bboxes and measurements."""

import pytest
from klave_engine.common.errors import GeometryError
from klave_engine.geometry.bbox import (
    bbox_center,
    bbox_contains_point,
    bbox_distance,
    bbox_expand,
    bbox_from_points,
    bbox_overlaps,
    bbox_union,
)
from klave_engine.geometry.measurements import (
    angles_parallel,
    is_axis_aligned,
    is_closed_polyline,
    line_length,
    polygon_area,
    polyline_length,
    rectangularity,
    segment_angle_degrees,
)

SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def test_bbox_from_points_and_center() -> None:
    box = bbox_from_points(SQUARE)
    assert box == (0.0, 0.0, 10.0, 10.0)
    assert bbox_center(box) == (5.0, 5.0)


def test_bbox_from_zero_points_raises() -> None:
    with pytest.raises(GeometryError):
        bbox_from_points([])


def test_bbox_overlap_and_union() -> None:
    a = (0.0, 0.0, 10.0, 10.0)
    b = (5.0, 5.0, 15.0, 15.0)
    c = (20.0, 20.0, 30.0, 30.0)
    assert bbox_overlaps(a, b)
    assert not bbox_overlaps(a, c)
    assert bbox_union(a, c) == (0.0, 0.0, 30.0, 30.0)


def test_bbox_distance() -> None:
    a = (0.0, 0.0, 10.0, 10.0)
    assert bbox_distance(a, (5.0, 5.0, 15.0, 15.0)) == 0.0
    assert bbox_distance(a, (13.0, 0.0, 20.0, 10.0)) == 3.0
    assert bbox_distance(a, (13.0, 14.0, 20.0, 20.0)) == 5.0


def test_bbox_expand_and_contains() -> None:
    box = bbox_expand((0.0, 0.0, 10.0, 10.0), 2.0)
    assert box == (-2.0, -2.0, 12.0, 12.0)
    assert bbox_contains_point(box, (-1.0, 11.0))
    assert not bbox_contains_point(box, (13.0, 0.0))


def test_lengths() -> None:
    assert line_length((0, 0), (3, 4)) == 5.0
    assert polyline_length([(0, 0), (10, 0), (10, 5)]) == 15.0


def test_polygon_area_and_rectangularity() -> None:
    assert polygon_area(SQUARE) == 100.0
    assert rectangularity(SQUARE) == 1.0
    triangle = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    assert polygon_area(triangle) == 50.0
    assert rectangularity(triangle) == 0.5


def test_closed_polyline_detection() -> None:
    assert is_closed_polyline([(0, 0), (10, 0), (10, 10), (0, 0)])
    assert not is_closed_polyline([(0, 0), (10, 0), (10, 10)])


def test_angles() -> None:
    assert segment_angle_degrees((0, 0), (10, 0)) == 0.0
    assert segment_angle_degrees((0, 0), (0, 10)) == 90.0
    assert angles_parallel(1.0, 179.5, tolerance_deg=2.0)
    assert is_axis_aligned(89.0)
    assert not is_axis_aligned(45.0)
