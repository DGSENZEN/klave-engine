"""Terreno natural from the topographic survey drawn on the sheet.

Terracerías (despalme, corte, terraplén) need the ground: curvas de nivel
(polylines on topo layers with their elevation, or a level text on them)
and puntos de nivel (a numeric text next to a marker on a topo layer). The
detector reads them into ONE terrain detection per file — a sample of
(x, y, z) points plus the lot polygon when the sheet draws one — and the
costing stage compares that ground against the platform level the
engineer sets. No topography → no terrain, and the sheet says so; the
platform level is never guessed.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field
from shapely.geometry import MultiPoint, Polygon

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.results import (
    DetectionType,
    DetectorOutput,
    layer_matches,
    make_detection,
)
from klave_engine.dxf.entities import EntityType, NormalizedEntity

_LEVEL_TEXT_RE = re.compile(r"^\s*[+\-]?\d{1,4}(?:[.,]\d{1,3})?\s*$")
MAX_SAMPLE_POINTS = 4000


class TerrainDetectorConfig(BaseModel):
    contour_layer_hints: list[str] = Field(
        default_factory=lambda: [
            "CURVA", "NIVEL", "TOPO", "CONTOUR", "TN", "TERRENO", "TOPOGRAF", "CN", "COTA-NIVEL",
        ]
    )
    lot_layer_hints: list[str] = Field(
        default_factory=lambda: ["LOTE", "LINDERO", "PREDIO", "TERRENO", "PROPIEDAD", "POLIGONO"]
    )
    avoid_layer_hints: list[str] = Field(
        default_factory=lambda: ["COTA", "DIM", "TEXT", "TXT", "EJE", "GRID"]
    )
    # A contour's level text sits this close to the line (drawing units).
    label_search_radius: float = 1.0
    min_contours: int = 3
    # Contour levels must spread at least this much to describe a slope.
    min_level_spread: float = 0.2
    # Implausible ground: levels below this are page coordinates, not meters.
    max_abs_level: float = 9000.0


def _level_from_text(text: str) -> float | None:
    if not _LEVEL_TEXT_RE.match(text):
        return None
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


def _sample(points: list[tuple[float, float, float]]) -> list[list[float]]:
    if len(points) <= MAX_SAMPLE_POINTS:
        return [[round(x, 3), round(y, 3), round(z, 3)] for x, y, z in points]
    step = len(points) / MAX_SAMPLE_POINTS
    return [
        [round(points[int(i * step)][0], 3), round(points[int(i * step)][1], 3),
         round(points[int(i * step)][2], 3)]
        for i in range(MAX_SAMPLE_POINTS)
    ]


def detect_terrain(
    entities: list[NormalizedEntity],
    config: TerrainDetectorConfig | None = None,
    detection_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or TerrainDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="terrain_detector")
    topo = [
        e for e in entities
        if layer_matches(e.layer, config.contour_layer_hints)
        and not layer_matches(e.layer, config.avoid_layer_hints)
    ]
    if not topo:
        return output
    level_texts = [
        (e, level) for e in topo
        if e.is_textual and e.text and (level := _level_from_text(e.text)) is not None
        and abs(level) <= config.max_abs_level
    ]
    contours: list[tuple[NormalizedEntity, float, str]] = []
    for e in topo:
        if e.entity_type != EntityType.polyline or not e.points or len(e.points) < 2:
            continue
        elevation = (e.properties or {}).get("elevation")
        if elevation is not None and 0 < abs(float(elevation)) <= config.max_abs_level:
            contours.append((e, float(elevation), "elevación de la polilínea"))
            continue
        # A level written beside the line names it.
        x0, y0, x1, y1 = e.bbox
        r = config.label_search_radius
        near = [
            level for t, level in level_texts
            if x0 - r <= (t.bbox[0] + t.bbox[2]) / 2 <= x1 + r
            and y0 - r <= (t.bbox[1] + t.bbox[3]) / 2 <= y1 + r
        ]
        if len(near) == 1:
            contours.append((e, near[0], "texto de nivel junto a la curva"))
    points: list[tuple[float, float, float]] = []
    source_entities: list[str] = []
    for e, level, _how in contours:
        for p in e.points or []:
            points.append((float(p[0]), float(p[1]), level))
        source_entities.append(e.entity_id)
    # Spot levels: a numeric text on a topo layer is a point of known level.
    spot = 0
    for t, level in level_texts:
        points.append(((t.bbox[0] + t.bbox[2]) / 2, (t.bbox[1] + t.bbox[3]) / 2, level))
        source_entities.append(t.entity_id)
        spot += 1
    levels = sorted({z for _x, _y, z in points})
    if len(contours) < config.min_contours and spot < 6:
        if contours or spot:
            output.warnings.append(
                f"Topografía: {len(contours)} curvas con nivel y {spot} puntos de nivel; "
                "insuficiente para describir el terreno (se necesitan ≥3 curvas o ≥6 puntos)."
            )
        return output
    if levels and levels[-1] - levels[0] < config.min_level_spread:
        output.warnings.append(
            "Topografía: todas las curvas tienen el mismo nivel; no hay pendiente que leer."
        )
        return output
    # The lot: a closed polyline on a lot layer; else the hull of the survey.
    lot: Polygon | None = None
    lot_source = "envolvente de la topografía"
    for e in entities:
        if (
            e.entity_type == EntityType.polyline and e.is_closed and e.points
            and len(e.points) >= 3 and layer_matches(e.layer, config.lot_layer_hints)
        ):
            candidate = Polygon([tuple(p[:2]) for p in e.points])
            if candidate.is_valid and (lot is None or candidate.area > lot.area):
                lot = candidate
                lot_source = f"polígono en capa {e.layer}"
                source_entities.append(e.entity_id)
    if lot is None:
        hull = MultiPoint([(x, y) for x, y, _z in points]).convex_hull
        lot = hull if isinstance(hull, Polygon) else None
    if lot is None or lot.area <= 0:
        output.warnings.append("Topografía: no se pudo delimitar el terreno.")
        return output
    minx, miny, maxx, maxy = lot.bounds
    output.detections.append(
        make_detection(
            detection_ids.next(),
            DetectionType.terrain,
            "TERRENO",
            (minx, miny, maxx, maxy),
            0.8 if len(contours) >= config.min_contours else 0.6,
            source_entities[:500],
            "terrain_from_contours",
            [
                f"{len(contours)} curvas de nivel, {spot} puntos de nivel, "
                f"niveles {levels[0]:.2f} a {levels[-1]:.2f}; lote: {lot_source}",
            ],
            {
                "estimated_area": round(lot.area, 3),
                "level_min": round(levels[0], 3),
                "level_max": round(levels[-1], 3),
                "contour_count": len(contours),
                "spot_count": spot,
                "lot_source": lot_source,
                "polygon": [[round(x, 4), round(y, 4)] for x, y in lot.exterior.coords],
                "sample_points": _sample(points),
            },
            contours[0][0].source_file if contours else level_texts[0][0].source_file,
        )
    )
    return output
