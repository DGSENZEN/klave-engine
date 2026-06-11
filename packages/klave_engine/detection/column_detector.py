"""Column tag detection from text patterns, grid proximity, and marker geometry."""

from pydantic import BaseModel, Field

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.results import (
    Detection,
    DetectionType,
    DetectorOutput,
    layer_matches,
)
from klave_engine.detection.text_patterns import TextPatternConfig, match_category
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import bbox_area, bbox_center
from klave_engine.geometry.measurements import line_length
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.graph.schema import EdgeType, GraphEdge, GraphNode, NodeType


class ColumnDetectorConfig(BaseModel):
    grid_search_radius: float = 40.0
    geometry_search_radius: float = 20.0
    max_marker_area: float = 10000.0
    layer_hints: list[str] = Field(
        default_factory=lambda: ["COL", "COLUMN", "COLUMNA", "CASTILLO", "DADO"]
    )
    base_confidence: float = 0.5
    grid_bonus: float = 0.2
    geometry_bonus: float = 0.2
    layer_bonus: float = 0.1
    max_confidence: float = 0.95


def detect_columns(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    grid_output: DetectorOutput | None = None,
    config: ColumnDetectorConfig | None = None,
    text_config: TextPatternConfig | None = None,
    detection_ids: IdGenerator | None = None,
    edge_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or ColumnDetectorConfig()
    text_config = text_config or TextPatternConfig()
    detection_ids = detection_ids or IdGenerator("det")
    edge_ids = edge_ids or IdGenerator("cedge")
    output = DetectorOutput(detector_name="column_detector")

    grid_intersections = [
        d
        for d in (grid_output.detections if grid_output else [])
        if d.detection_type == DetectionType.grid_intersection
    ]

    for entity in entities:
        if not entity.is_textual or not entity.text:
            continue
        if match_category(entity.text, text_config, "column_tag") is None:
            continue

        confidence = config.base_confidence
        notes = [f"Text '{entity.text.strip()}' matched column tag pattern"]
        source_entities = [entity.entity_id]
        properties: dict = {"has_nearby_grid": False}
        center = bbox_center(entity.bbox)

        # Grid proximity bonus.
        nearest_grid: Detection | None = None
        nearest_grid_distance = float("inf")
        for intersection in grid_intersections:
            point = intersection.properties.get("point")
            if point is None:
                continue
            distance = line_length(center, tuple(point))
            if distance < nearest_grid_distance:
                nearest_grid, nearest_grid_distance = intersection, distance
        if nearest_grid is not None and nearest_grid_distance <= config.grid_search_radius:
            confidence += config.grid_bonus
            properties.update(
                has_nearby_grid=True,
                nearest_grid=nearest_grid.label,
                nearest_grid_distance=round(nearest_grid_distance, 3),
            )
            notes.append(
                f"Near grid intersection {nearest_grid.label} "
                f"(distance {nearest_grid_distance:.1f})"
            )
        else:
            notes.append("No grid intersection within search radius")

        # Marker geometry bonus: circle, insert, or small closed polyline nearby.
        marker_id: str | None = None
        for hit in index.entities_near_entity(entity.entity_id, config.geometry_search_radius):
            other = index.get(hit.entity_id)
            is_marker = other.entity_type in (EntityType.circle, EntityType.insert) or (
                other.entity_type == EntityType.polyline
                and other.is_closed
                and bbox_area(other.bbox) <= config.max_marker_area
            )
            if is_marker:
                marker_id = other.entity_id
                break
        if marker_id is not None:
            confidence += config.geometry_bonus
            source_entities.append(marker_id)
            notes.append("Marker geometry (circle/block/closed polyline) found nearby")

        if layer_matches(entity.layer, config.layer_hints):
            confidence += config.layer_bonus
            notes.append(f"Layer '{entity.layer}' matches column layer hint")

        confidence = round(min(confidence, config.max_confidence), 4)
        detection_id = detection_ids.next()
        evidence = EvidencePacket(
            source=entity.source_file,
            method="column_tag_regex_near_grid",
            entity_ids=source_entities,
            bbox=entity.bbox,
            confidence=confidence,
            notes=notes,
        )
        detection = Detection(
            detection_id=detection_id,
            detection_type=DetectionType.column_tag,
            label=entity.text.strip(),
            bbox=entity.bbox,
            source_entities=source_entities,
            graph_nodes=[detection_id],
            confidence=confidence,
            evidence=evidence,
            properties=properties,
        )
        output.detections.append(detection)
        output.nodes.append(
            GraphNode(
                node_id=detection_id,
                node_type=NodeType.column_tag,
                label=detection.label,
                bbox=entity.bbox,
                source_entities=source_entities,
                properties=properties,
                confidence=confidence,
                evidence=evidence,
            )
        )
        output.edges.append(
            GraphEdge(
                edge_id=edge_ids.next(),
                edge_type=EdgeType.labels,
                source_node_id=entity.entity_id,
                target_node_id=detection_id,
                confidence=confidence,
                evidence=evidence,
            )
        )
        if marker_id is not None:
            output.edges.append(
                GraphEdge(
                    edge_id=edge_ids.next(),
                    edge_type=EdgeType.possible_structural_element,
                    source_node_id=detection_id,
                    target_node_id=marker_id,
                    confidence=confidence,
                    evidence=evidence,
                )
            )
        if nearest_grid is not None and properties["has_nearby_grid"]:
            output.edges.append(
                GraphEdge(
                    edge_id=edge_ids.next(),
                    edge_type=EdgeType.belongs_to_grid,
                    source_node_id=detection_id,
                    target_node_id=nearest_grid.detection_id,
                    confidence=confidence,
                    evidence=evidence,
                )
            )
    return output
