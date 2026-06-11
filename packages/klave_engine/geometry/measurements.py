"""Length, area, angle, and alignment measurements in drawing units."""

import math
from collections.abc import Sequence

from shapely.geometry import Polygon

from klave_engine.common.errors import GeometryError
from klave_engine.geometry.bbox import Point

CLOSED_TOLERANCE = 1e-6


def line_length(p1: Point, p2: Point) -> float:
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def polyline_length(points: Sequence[Point]) -> float:
    if len(points) < 2:
        return 0.0
    return sum(line_length(points[i], points[i + 1]) for i in range(len(points) - 1))


def is_closed_polyline(points: Sequence[Point], tolerance: float = CLOSED_TOLERANCE) -> bool:
    if len(points) < 3:
        return False
    return line_length(points[0], points[-1]) <= tolerance


def polygon_area(points: Sequence[Point]) -> float:
    if len(points) < 3:
        raise GeometryError("Polygon area requires at least 3 points")
    polygon = Polygon(points)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    return float(polygon.area)


def segment_angle_degrees(p1: Point, p2: Point) -> float:
    """Angle of a segment normalized to [0, 180)."""
    angle = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0])) % 180.0
    return angle


def angles_parallel(a: float, b: float, tolerance_deg: float = 2.0) -> bool:
    diff = abs(a - b) % 180.0
    return diff <= tolerance_deg or diff >= 180.0 - tolerance_deg


def is_axis_aligned(angle_deg: float, tolerance_deg: float = 2.0) -> bool:
    return angles_parallel(angle_deg, 0.0, tolerance_deg) or angles_parallel(
        angle_deg, 90.0, tolerance_deg
    )


def rectangularity(points: Sequence[Point]) -> float:
    """Ratio of polygon area to its bbox area; 1.0 for an axis-aligned rectangle."""
    from klave_engine.geometry.bbox import bbox_area, bbox_from_points

    area = polygon_area(points)
    box_area = bbox_area(bbox_from_points(points))
    if box_area <= 0:
        return 0.0
    return min(1.0, area / box_area)
