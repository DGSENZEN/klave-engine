"""Wall detection from paired long parallel lines."""

from pydantic import BaseModel, Field
from shapely.geometry import LineString

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.confidence import GEOM_PLAUSIBLE, SEMANTIC_LAYER, model_for
from klave_engine.detection.results import (
    DetectionType,
    DetectorOutput,
    layer_matches,
    make_detection,
)
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import bbox_union
from klave_engine.geometry.measurements import (
    angles_parallel,
    line_length,
    segment_angle_degrees,
)
from klave_engine.geometry.spatial_index import SpatialIndex


class WallDetectorConfig(BaseModel):
    min_length: float = 100.0
    max_thickness: float = 25.0
    angle_tolerance_deg: float = 2.0
    min_overlap_ratio: float = 0.5
    layer_hints: list[str] = Field(default_factory=lambda: ["WALL", "MURO"])


Segment = tuple[tuple[float, float], tuple[float, float]]


def _projection_overlap(a: Segment, b: Segment) -> float:
    """Overlap length of two segments projected onto the direction of segment a."""
    (ax1, ay1), (ax2, ay2) = a
    dx, dy = ax2 - ax1, ay2 - ay1
    length = line_length((ax1, ay1), (ax2, ay2))
    if length == 0:
        return 0.0
    ux, uy = dx / length, dy / length

    def project(point: tuple[float, float]) -> float:
        return (point[0] - ax1) * ux + (point[1] - ay1) * uy

    a_interval = sorted([0.0, length])
    b_interval = sorted([project(b[0]), project(b[1])])
    overlap = min(a_interval[1], b_interval[1]) - max(a_interval[0], b_interval[0])
    return max(0.0, overlap)


def detect_walls(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    config: WallDetectorConfig | None = None,
    detection_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or WallDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="wall_detector")
    model = model_for("wall")

    candidates: dict[str, tuple[NormalizedEntity, Segment, float]] = {
        e.entity_id: (e, (e.points[0], e.points[1]),
                      segment_angle_degrees(e.points[0], e.points[1]))
        for e in entities
        if e.entity_type == EntityType.line
        and e.points
        and line_length(e.points[0], e.points[1]) >= config.min_length
    }

    used: set[str] = set()
    wall_counter = 0
    for first, first_segment, angle_a in candidates.values():
        if first.entity_id in used:
            continue
        # Only candidate lines within wall thickness of this one, via the index.
        for hit in index.entities_near_entity(first.entity_id, config.max_thickness):
            partner = candidates.get(hit.entity_id)
            if partner is None:
                continue
            second, second_segment, angle_b = partner
            if second.entity_id in used:
                continue
            if not angles_parallel(angle_a, angle_b, config.angle_tolerance_deg):
                continue
            gap = float(LineString(first_segment).distance(LineString(second_segment)))
            if gap <= 0 or gap > config.max_thickness:
                continue
            overlap = _projection_overlap(first_segment, second_segment)
            min_len = min(
                line_length(*first_segment), line_length(*second_segment)
            )
            if min_len == 0 or overlap / min_len < config.min_overlap_ratio:
                continue

            notes = [
                f"Parallel line pair with gap {gap:.1f} and overlap {overlap:.1f}",
            ]
            # A clean, well-overlapping pair is plausible wall geometry.
            features: dict[str, float] = {GEOM_PLAUSIBLE: 1.0}
            if layer_matches(first.layer, config.layer_hints) or layer_matches(
                second.layer, config.layer_hints
            ):
                features[SEMANTIC_LAYER] = 1.0

            confidence = round(model.score(features), 4)
            notes.extend(model.explain(features))
            wall_counter += 1
            source_entities = [first.entity_id, second.entity_id]
            output.detections.append(
                make_detection(
                    detection_ids.next(),
                    DetectionType.wall,
                    f"W{wall_counter}",
                    bbox_union(first.bbox, second.bbox),
                    confidence,
                    source_entities,
                    "wall_paired_parallel_lines",
                    notes,
                    {
                        "estimated_length": round(overlap, 3),
                        "estimated_thickness": round(gap, 3),
                    },
                    first.source_file,
                )
            )
            used.update(source_entities)
            break
    return output
