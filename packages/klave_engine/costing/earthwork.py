"""Corte y terraplén: the surveyed ground against a platform level.

The terrain detection carries a sample of (x, y, z) points (contour
vertices and spot levels) and the lot polygon. The ground inside the lot is
interpolated on a grid from the nearest sample points (inverse-distance
weighting); every cell above the platform is corte, every cell below is
terraplén. The grid is fine enough that a cell is at most a 1/60th of the
lot's side, and the method is written on the line so a reviewer can judge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.prepared import prep

GRID_CELLS_PER_SIDE = 60
NEIGHBOURS = 8


@dataclass
class EarthworkVolumes:
    cut_m3: float
    fill_m3: float
    area_m2: float
    cell_m: float
    ground_min: float
    ground_max: float
    cells: int


def cut_fill_volumes(
    sample_points: list[list[float]],
    polygon: list[list[float]],
    platform_level: float,
    meters_factor: float = 1.0,
) -> EarthworkVolumes | None:
    """Volumes in m³ (drawing lengths scaled by `meters_factor` to meters;
    levels are taken as meters already, the survey's own unit)."""
    if len(sample_points) < 3 or len(polygon) < 3:
        return None
    lot = Polygon([(p[0] * meters_factor, p[1] * meters_factor) for p in polygon])
    if not lot.is_valid or lot.area <= 0:
        return None
    pts = np.array(
        [[p[0] * meters_factor, p[1] * meters_factor, p[2]] for p in sample_points],
        dtype=float,
    )
    minx, miny, maxx, maxy = lot.bounds
    side = max(maxx - minx, maxy - miny)
    cell = max(side / GRID_CELLS_PER_SIDE, 0.05)
    xs = np.arange(minx + cell / 2, maxx, cell)
    ys = np.arange(miny + cell / 2, maxy, cell)
    if xs.size == 0 or ys.size == 0:
        return None
    prepared = prep(lot)
    centres = [(x, y) for y in ys for x in xs if prepared.contains(Point(x, y))]
    if not centres:
        return None
    grid = np.array(centres, dtype=float)
    # IDW over the nearest samples, vectorised per chunk.
    k = min(NEIGHBOURS, len(pts))
    ground = np.empty(len(grid))
    for start in range(0, len(grid), 2048):
        block = grid[start:start + 2048]
        d2 = ((block[:, None, 0] - pts[None, :, 0]) ** 2
              + (block[:, None, 1] - pts[None, :, 1]) ** 2)
        idx = np.argpartition(d2, k - 1, axis=1)[:, :k]
        near_d2 = np.take_along_axis(d2, idx, axis=1)
        near_z = pts[idx, 2]
        weights = 1.0 / np.maximum(near_d2, 1e-6)
        ground[start:start + len(block)] = (weights * near_z).sum(axis=1) / weights.sum(axis=1)
    diff = ground - platform_level
    cell_area = cell * cell
    cut = float(np.clip(diff, 0, None).sum() * cell_area)
    fill = float(np.clip(-diff, 0, None).sum() * cell_area)
    return EarthworkVolumes(
        cut_m3=round(cut, 3),
        fill_m3=round(fill, 3),
        area_m2=round(len(grid) * cell_area, 3),
        cell_m=round(cell, 3),
        ground_min=round(float(ground.min()), 3),
        ground_max=round(float(ground.max()), 3),
        cells=len(grid),
    )


def describe(volumes: EarthworkVolumes, platform_level: float) -> str:
    return (
        f"Terreno interpolado (IDW, malla de {volumes.cell_m:.2f} m, {volumes.cells} celdas) "
        f"entre {volumes.ground_min:.2f} y {volumes.ground_max:.2f} contra plataforma "
        f"{platform_level:.2f}: corte {volumes.cut_m3:,.1f} m³, terraplén "
        f"{volumes.fill_m3:,.1f} m³ (medidos en banco/compactado, sin abundamiento)"
    )


def is_finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)
