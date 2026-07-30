"""Footing detection from closed, roughly rectangular polylines."""

from pydantic import BaseModel, Field

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.confidence import (
    HIGH_RECT,
    NEAR_COLUMN,
    SEMANTIC_LAYER,
    model_for,
)
from klave_engine.detection.results import (
    Detection,
    DetectionType,
    DetectorOutput,
    layer_matches,
    make_detection,
)
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import bbox_distance
from klave_engine.geometry.measurements import polygon_area, rectangularity
from klave_engine.geometry.spatial_index import SpatialIndex


class FootingDetectorConfig(BaseModel):
    min_area: float = 100.0
    max_area: float = 50000.0
    min_rectangularity: float = 0.75
    high_rectangularity: float = 0.9
    layer_hints: list[str] = Field(
        default_factory=lambda: ["FOOT", "FOUND", "FDN", "ZAPATA", "CIM", "DADO", "PILOT"]
    )
    column_search_radius: float = 50.0


def detect_footings(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    column_output: DetectorOutput | None = None,
    config: FootingDetectorConfig | None = None,
    detection_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or FootingDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="footing_detector")

    column_detections = [
        d
        for d in (column_output.detections if column_output else [])
        if d.detection_type == DetectionType.column_tag
    ]

    model = model_for("footing")
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

        notes = [
            f"Closed polyline with area {area:.1f} within footing size range",
            f"Rectangularity {rect:.2f}",
        ]
        properties: dict = {"estimated_area": round(area, 3), "rectangularity": round(rect, 3)}
        source_entities = [entity.entity_id]
        features: dict[str, float] = {}

        if layer_matches(entity.layer, config.layer_hints):
            features[SEMANTIC_LAYER] = 1.0
        if rect >= config.high_rectangularity:
            features[HIGH_RECT] = 1.0

        nearby_column: Detection | None = None
        nearest = float("inf")
        for column in column_detections:
            distance = bbox_distance(entity.bbox, column.bbox)
            if distance <= config.column_search_radius and distance < nearest:
                nearby_column, nearest = column, distance
        if nearby_column is not None:
            features[NEAR_COLUMN] = 1.0
            properties["nearby_column_tag"] = nearby_column.label
            notes.append(
                f"Column tag {nearby_column.label} within {nearest:.1f} drawing units"
            )

        confidence = round(model.score(features), 4)
        notes.extend(model.explain(features))
        footing_counter += 1
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.footing,
                f"F{footing_counter}",
                entity.bbox,
                confidence,
                source_entities,
                "footing_closed_rectangular_polyline",
                notes,
                properties,
                entity.source_file,
            )
        )
    return output
