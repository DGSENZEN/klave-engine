"""Slab region detection from hatches and large closed polylines."""

from pydantic import BaseModel, Field

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.confidence import (
    IS_HATCH,
    LARGE_AREA,
    SEMANTIC_LAYER,
    model_for,
)
from klave_engine.detection.results import (
    DetectionType,
    DetectorOutput,
    layer_matches,
    make_detection,
)
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import BBox, bbox_area
from klave_engine.geometry.measurements import polygon_area


class SlabDetectorConfig(BaseModel):
    min_area: float = 10000.0
    layer_hints: list[str] = Field(default_factory=lambda: ["SLAB", "DECK", "LOSA"])
    avoid_layer_hints: list[str] = Field(
        default_factory=lambda: ["MARCO", "FRAME", "CAJET", "TEXT", "COTA", "DIM", "EJE", "GRID",
                                 "TITLE", "BORDE", "BORDER"]
    )
    # An area this many× the minimum counts as strong "large area" evidence.
    large_area_factor: float = 3.0
    # A closed shape covering this share of a sheet frame is the frame, or
    # its cajetín — never a slab.
    frame_area_ratio: float = 0.25


def _estimated_area(entity: NormalizedEntity) -> float:
    if entity.points and len(entity.points) >= 3:
        return polygon_area(entity.points)
    return bbox_area(entity.bbox)


def detect_slabs(
    entities: list[NormalizedEntity],
    config: SlabDetectorConfig | None = None,
    detection_ids: IdGenerator | None = None,
    frame_boxes: list[BBox] | None = None,
) -> DetectorOutput:
    config = config or SlabDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="slab_detector")
    model = model_for("slab_region")
    frame_areas = [bbox_area(box) for box in (frame_boxes or [])]
    min_frame_area = min(frame_areas) if frame_areas else None

    def is_frame_like(entity: NormalizedEntity) -> bool:
        if min_frame_area is None:
            return False
        area = bbox_area(entity.bbox)
        if area >= config.frame_area_ratio * min_frame_area:
            return True
        return any(
            abs(entity.bbox[i] - box[i]) <= 0.02 * (box[2] - box[0]) for box in (frame_boxes or [])
            for i in (0, 2)
        ) and any(
            abs(entity.bbox[i] - box[i]) <= 0.02 * (box[3] - box[1]) for box in (frame_boxes or [])
            for i in (1, 3)
        )

    slab_counter = 0
    skipped_frames = 0
    for entity in entities:
        if layer_matches(entity.layer, config.avoid_layer_hints):
            continue
        features: dict[str, float] = {}
        if entity.entity_type == EntityType.hatch:
            features[IS_HATCH] = 1.0
            method = "slab_region_from_hatch"
        elif entity.entity_type == EntityType.polyline and entity.is_closed:
            method = "slab_region_from_large_closed_polyline"
        else:
            continue

        area = _estimated_area(entity)
        if area < config.min_area:
            continue
        if is_frame_like(entity):
            skipped_frames += 1
            continue

        notes = [f"Estimated area {area:.1f} above slab minimum {config.min_area:.0f}"]
        if area >= config.min_area * config.large_area_factor:
            features[LARGE_AREA] = 1.0
        if layer_matches(entity.layer, config.layer_hints):
            features[SEMANTIC_LAYER] = 1.0

        confidence = round(model.score(features), 4)
        notes.extend(model.explain(features))
        slab_counter += 1
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.slab_region,
                f"SLAB{slab_counter}",
                entity.bbox,
                confidence,
                [entity.entity_id],
                method,
                notes,
                {"estimated_area": round(area, 3)},
                entity.source_file,
            )
        )
    if skipped_frames:
        output.warnings.append(
            f"{skipped_frames} contornos del tamaño de un marco de hoja no se tomaron como losa."
        )
    return output
