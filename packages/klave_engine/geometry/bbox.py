"""Axis-aligned bounding box helpers.

A bbox is a ``(min_x, min_y, max_x, max_y)`` tuple in drawing units.
"""

import math
from collections.abc import Iterable

from klave_engine.common.errors import GeometryError

BBox = tuple[float, float, float, float]
Point = tuple[float, float]


def bbox_from_points(points: Iterable[Point]) -> BBox:
    pts = list(points)
    if not pts:
        raise GeometryError("Cannot compute bbox of zero points")
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_union(a: BBox, b: BBox) -> BBox:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def bbox_union_all(boxes: Iterable[BBox]) -> BBox:
    boxes = list(boxes)
    if not boxes:
        raise GeometryError("Cannot union zero bboxes")
    result = boxes[0]
    for box in boxes[1:]:
        result = bbox_union(result, box)
    return result


def bbox_overlaps(a: BBox, b: BBox) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def bbox_expand(box: BBox, margin: float) -> BBox:
    return (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin)


def bbox_center(box: BBox) -> Point:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def bbox_width(box: BBox) -> float:
    return box[2] - box[0]


def bbox_height(box: BBox) -> float:
    return box[3] - box[1]


def bbox_area(box: BBox) -> float:
    return max(0.0, bbox_width(box)) * max(0.0, bbox_height(box))


def bbox_diagonal(box: BBox) -> float:
    return math.hypot(bbox_width(box), bbox_height(box))


def bbox_contains_point(box: BBox, point: Point) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def bbox_distance(a: BBox, b: BBox) -> float:
    """Minimum distance between two bboxes; 0 if they overlap."""
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dy)


def point_to_bbox_distance(point: Point, box: BBox) -> float:
    dx = max(box[0] - point[0], point[0] - box[2], 0.0)
    dy = max(box[1] - point[1], point[1] - box[3], 0.0)
    return math.hypot(dx, dy)
