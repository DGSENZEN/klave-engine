"""Simple 2D point transforms."""

import math
from collections.abc import Sequence

from klave_engine.geometry.bbox import Point


def translate(points: Sequence[Point], dx: float, dy: float) -> list[Point]:
    return [(x + dx, y + dy) for x, y in points]


def scale(points: Sequence[Point], factor: float, origin: Point = (0.0, 0.0)) -> list[Point]:
    ox, oy = origin
    return [((x - ox) * factor + ox, (y - oy) * factor + oy) for x, y in points]


def rotate(points: Sequence[Point], angle_deg: float, origin: Point = (0.0, 0.0)) -> list[Point]:
    angle = math.radians(angle_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    ox, oy = origin
    return [
        ((x - ox) * cos_a - (y - oy) * sin_a + ox, (x - ox) * sin_a + (y - oy) * cos_a + oy)
        for x, y in points
    ]
