"""Escaleras: the ESCALERA text standing on its tread pattern.

A stair in plan is a run of short, parallel, evenly spaced lines (the
huellas) with the word ESCALERA (or RAMPA) on or beside it. The treads give
the geometry away: their common length is the stair's width, their span is
the horizontal run, their count is the number of steps. Nothing is invented:
without the tread pattern the text alone only produces a warning.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict

from pydantic import BaseModel, Field

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.results import (
    DetectionType,
    DetectorOutput,
    layer_matches,
    make_detection,
)
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import bbox_center
from klave_engine.geometry.spatial_index import SpatialIndex

_STAIR_TEXT_RE = re.compile(r"\b(ESCALERA|ESC\.|RAMPA)\b", re.I)


class StairDetectorConfig(BaseModel):
    # Everything in drawing units; the suite scales them by the unit preset.
    search_radius: float = 4.0  # around the text, where the treads must live
    tread_min_length: float = 0.6  # a stair is at least this wide
    tread_max_length: float = 3.0
    tread_min_spacing: float = 0.2  # huella (going) per step
    tread_max_spacing: float = 0.45
    min_treads: int = 5
    avoid_layer_hints: list[str] = Field(
        default_factory=lambda: ["COTA", "DIM", "DIMENSION", "TEXT", "TXT", "EJE", "EJES", "GRID"]
    )


def _length(entity: NormalizedEntity) -> float:
    points = entity.points or [(0.0, 0.0)]
    return max(abs(points[-1][0] - points[0][0]), abs(points[-1][1] - points[0][1]))


def _axis_lines(
    entities: list[NormalizedEntity], config: StairDetectorConfig
) -> dict[str, list[NormalizedEntity]]:
    """Short horizontal/vertical lines that could be treads, by axis."""
    by_axis: dict[str, list[NormalizedEntity]] = defaultdict(list)
    for entity in entities:
        if entity.entity_type != EntityType.line or not entity.points:
            continue
        if layer_matches(entity.layer, config.avoid_layer_hints):
            continue
        (x0, y0), (x1, y1) = entity.points[0], entity.points[-1]
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        length = max(dx, dy)
        if not (config.tread_min_length <= length <= config.tread_max_length):
            continue
        if dy <= 0.05 * max(dx, 1e-9):
            by_axis["horizontal"].append(entity)
        elif dx <= 0.05 * max(dy, 1e-9):
            by_axis["vertical"].append(entity)
    return by_axis


def _tread_run(
    lines: list[NormalizedEntity], axis: str, config: StairDetectorConfig
) -> tuple[list[NormalizedEntity], float] | None:
    """The longest evenly spaced run among candidate tread lines."""
    # Treads of one flight share their length closely; group by rounded length.
    if len(lines) < config.min_treads:
        return None
    lengths = [_length(e) for e in lines]
    median_len = statistics.median(lengths)
    flight = [
        e for e, ln in zip(lines, lengths, strict=True)
        if abs(ln - median_len) <= 0.25 * median_len
    ]
    if len(flight) < config.min_treads:
        return None
    # Sort across the run: horizontal treads stack vertically and vice versa.
    coord = (lambda e: bbox_center(e.bbox)[1]) if axis == "horizontal" else (
        lambda e: bbox_center(e.bbox)[0]
    )
    flight.sort(key=coord)
    best: list[NormalizedEntity] = []
    current: list[NormalizedEntity] = [flight[0]]
    for prev, item in zip(flight, flight[1:], strict=False):
        spacing = coord(item) - coord(prev)
        if config.tread_min_spacing * 0.5 <= spacing <= config.tread_max_spacing * 1.5:
            current.append(item)
        else:
            if len(current) > len(best):
                best = current
            current = [item]
    if len(current) > len(best):
        best = current
    if len(best) < config.min_treads:
        return None
    spacings = [coord(b) - coord(a) for a, b in zip(best, best[1:], strict=False)]
    typical = statistics.median(spacings)
    if not (config.tread_min_spacing <= typical <= config.tread_max_spacing):
        return None
    return best, typical


def detect_stairs(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    config: StairDetectorConfig | None = None,
    detection_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or StairDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="stair_detector")
    texts = [
        e for e in entities
        if e.is_textual and e.text and _STAIR_TEXT_RE.search(e.text)
        and len((e.text or "").split()) <= 4
    ]
    if not texts:
        return output
    by_axis = _axis_lines(entities, config)
    used: set[str] = set()
    counter = 0
    for text in texts:
        cx, cy = bbox_center(text.bbox)
        nearby: dict[str, list[NormalizedEntity]] = {
            axis: [
                line for line in lines
                if line.entity_id not in used
                and abs(bbox_center(line.bbox)[0] - cx) <= config.search_radius
                and abs(bbox_center(line.bbox)[1] - cy) <= config.search_radius
            ]
            for axis, lines in by_axis.items()
        }
        run = None
        for axis in ("horizontal", "vertical"):
            candidate = _tread_run(nearby.get(axis, []), axis, config)
            if candidate and (run is None or len(candidate[0]) > len(run[0])):
                run = candidate
        is_ramp = "RAMPA" in (text.text or "").upper()
        if run is None:
            output.warnings.append(
                f"«{' '.join((text.text or '').split())[:40]}» sin patrón de huellas "
                "alrededor; la escalera no se cuantificó."
            )
            continue
        treads, spacing = run
        used.update(t.entity_id for t in treads)
        xs = [c for t in treads for c in (t.bbox[0], t.bbox[2])]
        ys = [c for t in treads for c in (t.bbox[1], t.bbox[3])]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        width = statistics.median(_length(t) for t in treads)
        run_length = spacing * (len(treads) - 1)
        counter += 1
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.stair,
                f"ESC{counter}",
                bbox,
                0.8,
                [text.entity_id] + [t.entity_id for t in treads],
                "stair_treads_near_text",
                [
                    f"{len(treads)} huellas de {width:.2f} de ancho, paso {spacing:.2f}, "
                    f"junto a «{' '.join((text.text or '').split())[:30]}»",
                ],
                {
                    "tread_count": len(treads),
                    "tread_spacing": round(spacing, 3),
                    "stair_width": round(width, 3),
                    "run_length": round(run_length, 3),
                    "estimated_area": round(width * run_length, 3),
                    "stair_kind": "rampa" if is_ramp else "escalera",
                },
                text.source_file,
            )
        )
    return output
