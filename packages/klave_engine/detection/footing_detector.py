"""Footing detection from closed, roughly rectangular polylines."""

from pydantic import BaseModel, Field

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.results import (
    Detection,
    DetectionType,
    DetectorOutput,
    layer_matches,
)
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import bbox_distance
from klave_engine.geometry.measurements import polygon_area, rectangularity
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.graph.schema import EdgeType, GraphEdge, GraphNode, NodeType


class FootingDetectorConfig(BaseModel):
    min_area: float = 100.0
    max_area: float = 50000.0
    min_rectangularity: float = 0.75
    high_rectangularity: float = 0.9
    layer_hints: list[str] = Field(
        default_factory=lambda: ["FOOT", "FOUND", "FDN", "ZAPATA", "CIM", "DADO", "PILOT"]
    )
    column_search_radius: float = 50.0
    base_confidence: float = 0.4
    layer_bonus: float = 0.2
    column_bonus: float = 0.2
    rectangularity_bonus: float = 0.1


def detect_footings(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    column_output: DetectorOutput | None = None,
    config: FootingDetectorConfig | None = None,
    detection_ids: IdGenerator | None = None,
    edge_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or FootingDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    edge_ids = edge_ids or IdGenerator("fedge")
    output = DetectorOutput(detector_name="footing_detector")

    column_detections = [
        d
        for d in (column_output.detections if column_output else [])
        if d.detection_type == DetectionType.column_tag
    ]

    footing_counter = 0
    for entity in entities:
        if entity.entity_type != EntityType.polyline or not entity.is_closed:
            continue
        if not entity.points or len(entity.points) < 3:
            continue
        area = polygon_area(entity.points)
        if not (config.min_area <= area <= config.max_area):
            continue
        rect = rectangularity(entity.points)
        if rect < config.min_rectangularity:
            output.warnings.append(
                f"Closed polyline {entity.entity_id} in footing size range but "
                f"rectangularity {rect:.2f} below threshold; skipped"
            )
            continue

        confidence = config.base_confidence
        notes = [
            f"Closed polyline with area {area:.1f} within footing size range",
            f"Rectangularity {rect:.2f}",
        ]
        properties: dict = {"estimated_area": round(area, 3), "rectangularity": round(rect, 3)}
        source_entities = [entity.entity_id]

        if layer_matches(entity.layer, config.layer_hints):
            confidence += config.layer_bonus
            notes.append(f"Layer '{entity.layer}' matches foundation layer hint")
        if rect >= config.high_rectangularity:
            confidence += config.rectangularity_bonus

        nearby_column: Detection | None = None
        nearest = float("inf")
        for column in column_detections:
            distance = bbox_distance(entity.bbox, column.bbox)
            if distance <= config.column_search_radius and distance < nearest:
                nearby_column, nearest = column, distance
        if nearby_column is not None:
            confidence += config.column_bonus
            properties["nearby_column_tag"] = nearby_column.label
            notes.append(
                f"Column tag {nearby_column.label} within {nearest:.1f} drawing units"
            )
        else:
            notes.append("No column tag found near footing")

        confidence = round(confidence, 4)
        footing_counter += 1
        detection_id = detection_ids.next()
        evidence = EvidencePacket(
            source=entity.source_file,
            method="footing_closed_rectangular_polyline",
            entity_ids=source_entities,
            bbox=entity.bbox,
            confidence=confidence,
            notes=notes,
        )
        detection = Detection(
            detection_id=detection_id,
            detection_type=DetectionType.footing,
            label=f"F{footing_counter}",
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
                node_type=NodeType.footing,
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
                edge_type=EdgeType.possible_structural_element,
                source_node_id=detection_id,
                target_node_id=entity.entity_id,
                confidence=confidence,
                evidence=evidence,
            )
        )
        if nearby_column is not None:
            output.edges.append(
                GraphEdge(
                    edge_id=edge_ids.next(),
                    edge_type=EdgeType.near,
                    source_node_id=detection_id,
                    target_node_id=nearby_column.detection_id,
                    confidence=confidence,
                    evidence=evidence,
                )
            )
    return output
