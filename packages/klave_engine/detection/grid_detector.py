"""Grid detection: long axis-aligned lines, labels near endpoints, intersections.

Not every long line is a grid line: candidates must be axis-aligned and long
relative to the drawing extent. Confidence is higher when a grid label is found
near a line endpoint.
"""

from pydantic import BaseModel, Field
from shapely.geometry import LineString

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.confidence import GRID_LABEL, SEMANTIC_LAYER, model_for
from klave_engine.detection.results import (
    DetectionType,
    DetectorOutput,
    layer_matches,
    make_detection,
)
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


class GridDetectorConfig(BaseModel):
    min_relative_length: float = 0.5
    angle_tolerance_deg: float = 2.0
    label_search_radius_factor: float = 0.05  # fraction of drawing extent diagonal
    layer_hints: list[str] = Field(default_factory=lambda: ["GRID", "EJE", "AXIS"])


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
) -> DetectorOutput:
    config = config or GridDetectorConfig()
    text_config = text_config or TextPatternConfig()
    detection_ids = detection_ids or IdGenerator("det")
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

    model = model_for("grid_line")
    auto_counter = {"horizontal": 0, "vertical": 0}
    for candidate in candidates:
        features: dict[str, float] = {}
        if layer_matches(index.get(candidate.entity_id).layer, config.layer_hints):
            features[SEMANTIC_LAYER] = 1.0
        if candidate.label is None:
            auto_counter[candidate.axis] += 1
            prefix = "H" if candidate.axis == "horizontal" else "V"
            label = f"{prefix}{auto_counter[candidate.axis]}"
            # Write the auto-label back so intersections read "H1/V2", not "?/?".
            candidate.label = label
            notes = ["No grid label found near line endpoints"]
        else:
            label = candidate.label
            features[GRID_LABEL] = 1.0
            notes = [f"Grid label '{label}' found near line endpoint"]
        confidence = round(model.score(features), 4)
        notes.extend(model.explain(features))

        detection_id = detection_ids.next()
        candidate.detection_id = detection_id
        candidate.confidence = confidence
        source_entities = [candidate.entity_id]
        if candidate.label_entity_id:
            source_entities.append(candidate.label_entity_id)
        line_entity = index.get(candidate.entity_id)
        output.detections.append(
            make_detection(
                detection_id,
                DetectionType.grid_line,
                label,
                line_entity.bbox,
                confidence,
                source_entities,
                "grid_line_axis_aligned_long_line",
                notes,
                {"axis": candidate.axis, "length": round(candidate.length, 3)},
                candidate.source_file,
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
            point_bbox = bbox_expand((point.x, point.y, point.x, point.y), 1.0)
            output.detections.append(
                make_detection(
                    detection_ids.next(),
                    DetectionType.grid_intersection,
                    label,
                    point_bbox,
                    confidence,
                    [h.entity_id, v.entity_id],
                    "grid_intersection_of_grid_lines",
                    [f"Intersection of grid lines {h.label or '?'} and {v.label or '?'}"],
                    {"point": (point.x, point.y)},
                    h.source_file,
                )
            )
    return output
