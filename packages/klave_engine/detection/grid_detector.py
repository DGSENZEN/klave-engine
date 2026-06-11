"""Grid detection: long axis-aligned lines, labels near endpoints, intersections.

Not every long line is a grid line: candidates must be axis-aligned and long
relative to the drawing extent. Confidence is higher when a grid label is found
near a line endpoint.
"""

from pydantic import BaseModel
from shapely.geometry import LineString

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.results import Detection, DetectionType, DetectorOutput
from klave_engine.detection.text_patterns import TextPatternConfig, match_category
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import (
    bbox_center,
    bbox_diagonal,
    bbox_expand,
    bbox_height,
    bbox_width,
)
from klave_engine.geometry.measurements import (
    angles_parallel,
    line_length,
    segment_angle_degrees,
)
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.graph.schema import EdgeType, GraphEdge, GraphNode, NodeType


class GridDetectorConfig(BaseModel):
    min_relative_length: float = 0.5
    angle_tolerance_deg: float = 2.0
    label_search_radius_factor: float = 0.05  # fraction of drawing extent diagonal
    labeled_confidence: float = 0.9
    unlabeled_confidence: float = 0.6


class _GridLineCandidate(BaseModel):
    entity_id: str
    source_file: str
    axis: str  # "horizontal" | "vertical"
    start: tuple[float, float]
    end: tuple[float, float]
    length: float
    label: str | None = None
    label_entity_id: str | None = None
    detection_id: str | None = None
    confidence: float = 0.0


def _line_endpoints(entity: NormalizedEntity) -> tuple | None:
    if entity.entity_type == EntityType.line and entity.points:
        return entity.points[0], entity.points[1]
    if (
        entity.entity_type == EntityType.polyline
        and entity.points
        and len(entity.points) == 2
        and not entity.is_closed
    ):
        return entity.points[0], entity.points[1]
    return None


def detect_grid(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    config: GridDetectorConfig | None = None,
    text_config: TextPatternConfig | None = None,
    detection_ids: IdGenerator | None = None,
    edge_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or GridDetectorConfig()
    text_config = text_config or TextPatternConfig()
    detection_ids = detection_ids or IdGenerator("det")
    edge_ids = edge_ids or IdGenerator("gedge")
    output = DetectorOutput(detector_name="grid_detector")

    extent = index.extent()
    if extent is None:
        output.warnings.append("Empty drawing: no entities to detect grid lines in")
        return output

    label_radius = bbox_diagonal(extent) * config.label_search_radius_factor
    grid_label_texts = [
        e
        for e in entities
        if e.is_textual and e.text and match_category(e.text, text_config, "grid_label")
    ]

    candidates: list[_GridLineCandidate] = []
    for entity in entities:
        endpoints = _line_endpoints(entity)
        if endpoints is None:
            continue
        start, end = endpoints
        angle = segment_angle_degrees(start, end)
        length = line_length(start, end)
        if angles_parallel(angle, 0.0, config.angle_tolerance_deg):
            axis, extent_dim = "horizontal", bbox_width(extent)
        elif angles_parallel(angle, 90.0, config.angle_tolerance_deg):
            axis, extent_dim = "vertical", bbox_height(extent)
        else:
            continue
        if extent_dim <= 0 or length < config.min_relative_length * extent_dim:
            continue
        candidates.append(
            _GridLineCandidate(
                entity_id=entity.entity_id,
                source_file=entity.source_file,
                axis=axis,
                start=start,
                end=end,
                length=length,
            )
        )

    # Associate labels: text whose center is near either endpoint of a candidate.
    for candidate in candidates:
        best: tuple[float, NormalizedEntity] | None = None
        for text_entity in grid_label_texts:
            center = bbox_center(text_entity.bbox)
            distance = min(
                line_length(center, candidate.start), line_length(center, candidate.end)
            )
            if distance <= label_radius and (best is None or distance < best[0]):
                best = (distance, text_entity)
        if best is not None:
            candidate.label = best[1].text.strip() if best[1].text else None
            candidate.label_entity_id = best[1].entity_id

    auto_counter = {"horizontal": 0, "vertical": 0}
    for candidate in candidates:
        if candidate.label is None:
            auto_counter[candidate.axis] += 1
            prefix = "H" if candidate.axis == "horizontal" else "V"
            label = f"{prefix}{auto_counter[candidate.axis]}"
            # Write the auto-label back so intersections read "H1/V2", not "?/?".
            candidate.label = label
            confidence = config.unlabeled_confidence
            notes = ["No grid label found near line endpoints"]
        else:
            label = candidate.label
            confidence = config.labeled_confidence
            notes = [f"Grid label '{label}' found near line endpoint"]

        detection_id = detection_ids.next()
        candidate.detection_id = detection_id
        candidate.confidence = confidence
        source_entities = [candidate.entity_id]
        if candidate.label_entity_id:
            source_entities.append(candidate.label_entity_id)
        line_entity = index.get(candidate.entity_id)
        evidence = EvidencePacket(
            source=candidate.source_file,
            method="grid_line_axis_aligned_long_line",
            entity_ids=source_entities,
            bbox=line_entity.bbox,
            confidence=confidence,
            notes=notes,
        )
        detection = Detection(
            detection_id=detection_id,
            detection_type=DetectionType.grid_line,
            label=label,
            bbox=line_entity.bbox,
            source_entities=source_entities,
            graph_nodes=[detection_id],
            confidence=confidence,
            evidence=evidence,
            properties={"axis": candidate.axis, "length": round(candidate.length, 3)},
        )
        output.detections.append(detection)
        output.nodes.append(
            GraphNode(
                node_id=detection_id,
                node_type=NodeType.grid_line,
                label=label,
                bbox=line_entity.bbox,
                source_entities=source_entities,
                properties=detection.properties,
                confidence=confidence,
                evidence=evidence,
            )
        )
        output.edges.append(
            GraphEdge(
                edge_id=edge_ids.next(),
                edge_type=EdgeType.possible_structural_element,
                source_node_id=detection_id,
                target_node_id=candidate.entity_id,
                confidence=confidence,
                evidence=evidence,
            )
        )
        if candidate.label_entity_id:
            output.edges.append(
                GraphEdge(
                    edge_id=edge_ids.next(),
                    edge_type=EdgeType.labels,
                    source_node_id=candidate.label_entity_id,
                    target_node_id=detection_id,
                    confidence=confidence,
                    evidence=evidence,
                )
            )

    # Intersections of horizontal x vertical grid lines.
    horizontals = [c for c in candidates if c.axis == "horizontal"]
    verticals = [c for c in candidates if c.axis == "vertical"]
    for h in horizontals:
        h_geom = LineString([h.start, h.end])
        for v in verticals:
            point = h_geom.intersection(LineString([v.start, v.end]))
            if point.is_empty or point.geom_type != "Point":
                continue
            label = f"{h.label or '?'}/{v.label or '?'}"
            confidence = min(h.confidence, v.confidence)
            detection_id = detection_ids.next()
            point_bbox = bbox_expand((point.x, point.y, point.x, point.y), 1.0)
            evidence = EvidencePacket(
                source=h.source_file,
                method="grid_intersection_of_grid_lines",
                entity_ids=[h.entity_id, v.entity_id],
                bbox=point_bbox,
                confidence=confidence,
                notes=[f"Intersection of grid lines {h.label or '?'} and {v.label or '?'}"],
            )
            detection = Detection(
                detection_id=detection_id,
                detection_type=DetectionType.grid_intersection,
                label=label,
                bbox=point_bbox,
                source_entities=[h.entity_id, v.entity_id],
                graph_nodes=[detection_id],
                confidence=confidence,
                evidence=evidence,
                properties={"point": (point.x, point.y)},
            )
            output.detections.append(detection)
            output.nodes.append(
                GraphNode(
                    node_id=detection_id,
                    node_type=NodeType.grid_intersection,
                    label=label,
                    bbox=point_bbox,
                    source_entities=detection.source_entities,
                    properties=detection.properties,
                    confidence=confidence,
                    evidence=evidence,
                )
            )
            for grid_candidate in (h, v):
                if grid_candidate.detection_id:
                    output.edges.append(
                        GraphEdge(
                            edge_id=edge_ids.next(),
                            edge_type=EdgeType.belongs_to_grid,
                            source_node_id=detection_id,
                            target_node_id=grid_candidate.detection_id,
                            confidence=confidence,
                            evidence=evidence,
                        )
                    )
    return output
