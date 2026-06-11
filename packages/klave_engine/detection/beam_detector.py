"""Beam tag detection: beam-pattern text associated with nearby linework."""

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
from klave_engine.geometry.measurements import polyline_length
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.graph.schema import EdgeType, GraphEdge, GraphNode, NodeType


class BeamDetectorConfig(BaseModel):
    line_search_radius: float = 30.0
    min_beam_length: float = 50.0
    layer_hints: list[str] = Field(default_factory=lambda: ["BEAM", "GIRD", "TRABE", "VIGA"])
    base_confidence: float = 0.5
    line_bonus: float = 0.2
    layer_bonus: float = 0.1


def detect_beams(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    config: BeamDetectorConfig | None = None,
    text_config: TextPatternConfig | None = None,
    detection_ids: IdGenerator | None = None,
    edge_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or BeamDetectorConfig()
    text_config = text_config or TextPatternConfig()
    detection_ids = detection_ids or IdGenerator("det")
    edge_ids = edge_ids or IdGenerator("bedge")
    output = DetectorOutput(detector_name="beam_detector")

    for entity in entities:
        if not entity.is_textual or not entity.text:
            continue
        if match_category(entity.text, text_config, "beam_tag") is None:
            continue

        confidence = config.base_confidence
        notes = [f"Text '{entity.text.strip()}' matched beam tag pattern"]
        source_entities = [entity.entity_id]
        properties: dict = {}

        # Nearest sufficiently long open linework within the search radius.
        beam_line: NormalizedEntity | None = None
        for hit in index.entities_near_entity(entity.entity_id, config.line_search_radius):
            other = index.get(hit.entity_id)
            if other.entity_type not in (EntityType.line, EntityType.polyline):
                continue
            if other.is_closed or not other.points:
                continue
            if polyline_length(other.points) >= config.min_beam_length:
                beam_line = other
                break
        if beam_line is not None:
            span = polyline_length(beam_line.points or [])
            confidence += config.line_bonus
            source_entities.append(beam_line.entity_id)
            properties["estimated_span_length"] = round(span, 3)
            notes.append(f"Associated with linework of length {span:.1f}")
        else:
            notes.append("No suitable linework found near beam tag")

        hint_layer = entity.layer if layer_matches(entity.layer, config.layer_hints) else None
        if hint_layer is None and beam_line is not None:
            if layer_matches(beam_line.layer, config.layer_hints):
                hint_layer = beam_line.layer
        if hint_layer is not None:
            confidence += config.layer_bonus
            notes.append(f"Layer '{hint_layer}' matches beam layer hint")

        confidence = round(confidence, 4)
        detection_id = detection_ids.next()
        evidence = EvidencePacket(
            source=entity.source_file,
            method="beam_tag_regex_near_linework",
            entity_ids=source_entities,
            bbox=entity.bbox,
            confidence=confidence,
            notes=notes,
        )
        detection = Detection(
            detection_id=detection_id,
            detection_type=DetectionType.beam_tag,
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
                node_type=NodeType.beam_tag,
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
        if beam_line is not None:
            output.edges.append(
                GraphEdge(
                    edge_id=edge_ids.next(),
                    edge_type=EdgeType.aligned_with,
                    source_node_id=detection_id,
                    target_node_id=beam_line.entity_id,
                    confidence=confidence,
                    evidence=evidence,
                )
            )
    return output
