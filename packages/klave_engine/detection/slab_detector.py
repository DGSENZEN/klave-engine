"""Slab region detection from hatches and large closed polylines."""

from pydantic import BaseModel, Field

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.results import (
    Detection,
    DetectionType,
    DetectorOutput,
    layer_matches,
)
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import bbox_area
from klave_engine.geometry.measurements import polygon_area
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.graph.schema import EdgeType, GraphEdge, GraphNode, NodeType


class SlabDetectorConfig(BaseModel):
    min_area: float = 10000.0
    layer_hints: list[str] = Field(default_factory=lambda: ["SLAB", "DECK", "LOSA"])
    hatch_base_confidence: float = 0.5
    polyline_base_confidence: float = 0.4
    layer_bonus: float = 0.2


def _estimated_area(entity: NormalizedEntity) -> float:
    if entity.points and len(entity.points) >= 3:
        return polygon_area(entity.points)
    return bbox_area(entity.bbox)


def detect_slabs(
    entities: list[NormalizedEntity],
    config: SlabDetectorConfig | None = None,
    detection_ids: IdGenerator | None = None,
    edge_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or SlabDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    edge_ids = edge_ids or IdGenerator("sedge")
    output = DetectorOutput(detector_name="slab_detector")

    slab_counter = 0
    for entity in entities:
        if entity.entity_type == EntityType.hatch:
            base_confidence = config.hatch_base_confidence
            method = "slab_region_from_hatch"
        elif entity.entity_type == EntityType.polyline and entity.is_closed:
            base_confidence = config.polyline_base_confidence
            method = "slab_region_from_large_closed_polyline"
        else:
            continue

        area = _estimated_area(entity)
        if area < config.min_area:
            continue

        confidence = base_confidence
        notes = [f"Estimated area {area:.1f} above slab minimum {config.min_area:.0f}"]
        if layer_matches(entity.layer, config.layer_hints):
            confidence += config.layer_bonus
            notes.append(f"Layer '{entity.layer}' matches slab layer hint")

        confidence = round(confidence, 4)
        slab_counter += 1
        detection_id = detection_ids.next()
        evidence = EvidencePacket(
            source=entity.source_file,
            method=method,
            entity_ids=[entity.entity_id],
            bbox=entity.bbox,
            confidence=confidence,
            notes=notes,
        )
        detection = Detection(
            detection_id=detection_id,
            detection_type=DetectionType.slab_region,
            label=f"SLAB{slab_counter}",
            bbox=entity.bbox,
            source_entities=[entity.entity_id],
            graph_nodes=[detection_id],
            confidence=confidence,
            evidence=evidence,
            properties={"estimated_area": round(area, 3)},
        )
        output.detections.append(detection)
        output.nodes.append(
            GraphNode(
                node_id=detection_id,
                node_type=NodeType.slab_region,
                label=detection.label,
                bbox=entity.bbox,
                source_entities=[entity.entity_id],
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
                target_node_id=entity.entity_id,
                confidence=confidence,
                evidence=evidence,
            )
        )
    return output
