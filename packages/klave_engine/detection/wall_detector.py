"""Wall detection from paired long parallel lines."""

from pydantic import BaseModel, Field
from shapely.geometry import LineString

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.results import (
    Detection,
    DetectionType,
    DetectorOutput,
    layer_matches,
)
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import bbox_union
from klave_engine.geometry.measurements import (
    angles_parallel,
    line_length,
    segment_angle_degrees,
)
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.graph.schema import EdgeType, GraphEdge, GraphNode, NodeType


class WallDetectorConfig(BaseModel):
    min_length: float = 100.0
    max_thickness: float = 25.0
    angle_tolerance_deg: float = 2.0
    min_overlap_ratio: float = 0.5
    layer_hints: list[str] = Field(default_factory=lambda: ["WALL", "MURO"])
    base_confidence: float = 0.5
    layer_bonus: float = 0.2


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
    edge_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or WallDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    edge_ids = edge_ids or IdGenerator("wedge")
    output = DetectorOutput(detector_name="wall_detector")

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

            confidence = config.base_confidence
            notes = [
                f"Parallel line pair with gap {gap:.1f} and overlap {overlap:.1f}",
            ]
            if layer_matches(first.layer, config.layer_hints) or layer_matches(
                second.layer, config.layer_hints
            ):
                confidence += config.layer_bonus
                notes.append("Layer matches wall layer hint")

            confidence = round(confidence, 4)
            wall_counter += 1
            detection_id = detection_ids.next()
            wall_bbox = bbox_union(first.bbox, second.bbox)
            source_entities = [first.entity_id, second.entity_id]
            evidence = EvidencePacket(
                source=first.source_file,
                method="wall_paired_parallel_lines",
                entity_ids=source_entities,
                bbox=wall_bbox,
                confidence=confidence,
                notes=notes,
            )
            detection = Detection(
                detection_id=detection_id,
                detection_type=DetectionType.wall,
                label=f"W{wall_counter}",
                bbox=wall_bbox,
                source_entities=source_entities,
                graph_nodes=[detection_id],
                confidence=confidence,
                evidence=evidence,
                properties={
                    "estimated_length": round(overlap, 3),
                    "estimated_thickness": round(gap, 3),
                },
            )
            output.detections.append(detection)
            output.nodes.append(
                GraphNode(
                    node_id=detection_id,
                    node_type=NodeType.wall,
                    label=detection.label,
                    bbox=wall_bbox,
                    source_entities=source_entities,
                    properties=detection.properties,
                    confidence=confidence,
                    evidence=evidence,
                )
            )
            for entity_id in source_entities:
                output.edges.append(
                    GraphEdge(
                        edge_id=edge_ids.next(),
                        edge_type=EdgeType.possible_structural_element,
                        source_node_id=detection_id,
                        target_node_id=entity_id,
                        confidence=confidence,
                        evidence=evidence,
                    )
                )
            used.update(source_entities)
            break
    return output
