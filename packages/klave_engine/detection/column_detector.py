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
from klave_engine.geometry.measurements import line_length, polygon_area
from klave_engine.geometry.spatial_index import SpatialIndex
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.graph.schema import EdgeType, GraphEdge, GraphNode, NodeType


def _marker_section(marker: NormalizedEntity) -> tuple[float | None, str]:
    """Real cross-section area of a column marker in drawing units².

    Circle → π r²; closed polyline → polygon area; anything else → bbox area.
    """
    if marker.entity_type == EntityType.circle:
        radius = marker.properties.get("radius")
        if radius:
            return 3.141592653589793 * float(radius) ** 2, "marcador_circular"
    if (
        marker.entity_type == EntityType.polyline
        and marker.is_closed
        and marker.points
        and len(marker.points) >= 3
    ):
        return polygon_area(marker.points), "marcador_poligonal"
    area = bbox_area(marker.bbox)
    return (area if area > 0 else None), "marcador_bbox"


class ColumnDetectorConfig(BaseModel):
    grid_search_radius: float = 40.0
    geometry_search_radius: float = 20.0
    max_marker_area: float = 10000.0
    layer_hints: list[str] = Field(
        default_factory=lambda: ["COL", "COLUMN", "COLUMNA", "CASTILLO", "DADO"]
    )


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
        and d.properties.get("point") is not None
    ]
    # Precompute intersection points once for vectorized nearest-grid queries.
    grid_points = np.array(
        [d.properties["point"] for d in grid_intersections], dtype=float
    ) if grid_intersections else np.empty((0, 2))

    model = ConfidenceModel.model_validate(model_for("column_tag").model_dump())

    for entity in entities:
        if not entity.is_textual or not entity.text:
            continue
        if match_category(entity.text, text_config, "column_tag") is None:
            continue

        notes = [f"Text '{entity.text.strip()}' matched column tag pattern"]
        source_entities = [entity.entity_id]
        properties: dict = {"has_nearby_grid": False}
        features: dict[str, float] = {}
        cx, cy = bbox_center(entity.bbox)

        # Grid proximity: vectorized nearest intersection (NumPy broadcast).
        if len(grid_points):
            distances = np.hypot(grid_points[:, 0] - cx, grid_points[:, 1] - cy)
            nearest_idx = int(distances.argmin())
            nearest_grid_distance = float(distances[nearest_idx])
            if nearest_grid_distance <= config.grid_search_radius:
                nearest_grid = grid_intersections[nearest_idx]
                features[NEAR_GRID] = 1.0
                properties.update(
                    has_nearby_grid=True,
                    nearest_grid=nearest_grid.label,
                    nearest_grid_distance=round(nearest_grid_distance, 3),
                )
                notes.append(
                    f"Near grid intersection {nearest_grid.label} "
                    f"(distance {nearest_grid_distance:.1f})"
                )

        # Marker geometry: circle/insert/small closed polyline nearby; when found
        # measure its real cross-section so costing uses the actual section.
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
            features[MARKER] = 1.0
            source_entities.append(marker_id)
            section, section_source = _marker_section(index.get(marker_id))
            if section is not None:
                properties["section_area_du2"] = round(section, 6)
                properties["section_source"] = section_source
                notes.append(
                    f"Sección medida del marcador: {section:.4f} u.dib.² ({section_source})"
                )

        if layer_matches(entity.layer, config.layer_hints):
            features[SEMANTIC_LAYER] = 1.0

        confidence = round(model.score(features), 4)
        notes.extend(model.explain(features))
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
