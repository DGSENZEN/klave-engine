"""Beam tag detection: beam-pattern text associated with nearby linework."""

from pydantic import BaseModel, Field

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.confidence import NEAR_LINE, SEMANTIC_LAYER, model_for
from klave_engine.detection.results import (
    DetectionType,
    DetectorOutput,
    layer_matches,
    make_detection,
)
from klave_engine.detection.text_patterns import TextPatternConfig, match_category
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.measurements import polyline_length
from klave_engine.geometry.spatial_index import SpatialIndex


class BeamDetectorConfig(BaseModel):
    line_search_radius: float = 30.0
    min_beam_length: float = 50.0
    # Spans above this are axes or borders, not trabes (scaled per unit preset).
    max_beam_length: float = 1e12
    layer_hints: list[str] = Field(
        default_factory=lambda: [
            "BEAM", "GIRD", "TRABE", "VIGA", "CADENA", "CERRAM", "DALA",
        ]
    )
    avoid_layer_hints: list[str] = Field(default_factory=lambda: ["GRID", "EJE", "EJES", "AXIS"])


def detect_beams(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    config: BeamDetectorConfig | None = None,
    text_config: TextPatternConfig | None = None,
    detection_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or BeamDetectorConfig()
    text_config = text_config or TextPatternConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="beam_detector")
    model = model_for("beam_tag")

    for entity in entities:
        if not entity.is_textual or not entity.text:
            continue
        if match_category(entity.text, text_config, "beam_tag") is None:
            continue

        notes = [f"Text '{entity.text.strip()}' matched beam tag pattern"]
        source_entities = [entity.entity_id]
        properties: dict = {}
        features: dict[str, float] = {}

        # The trabe's own line: open linework of plausible span within the
        # search radius, preferring beam layers and never a grid axis. A
        # nearer axis must not win over the trabe line beside it.
        beam_line: NormalizedEntity | None = None
        best_key: tuple[int, int, float] | None = None
        for hit in index.entities_near_entity(entity.entity_id, config.line_search_radius):
            other = index.get(hit.entity_id)
            if other.entity_type not in (EntityType.line, EntityType.polyline):
                continue
            if other.is_closed or not other.points:
                continue
            length = polyline_length(other.points)
            if not (config.min_beam_length <= length <= config.max_beam_length):
                continue
            if layer_matches(other.layer, config.avoid_layer_hints):
                continue
            on_beam_layer = layer_matches(other.layer, config.layer_hints)
            key = (0 if on_beam_layer else 1, 0, float(hit.distance))
            if best_key is None or key < best_key:
                best_key, beam_line = key, other
        if beam_line is not None:
            span = polyline_length(beam_line.points or [])
            features[NEAR_LINE] = 1.0
            source_entities.append(beam_line.entity_id)
            properties["estimated_span_length"] = round(span, 3)
            properties["span_layer"] = beam_line.layer
            notes.append(f"Associated with linework of length {span:.1f}")
            if layer_matches(beam_line.layer, config.layer_hints):
                notes.append(f"Línea de trabe en capa {beam_line.layer}")

        hint_layer = entity.layer if layer_matches(entity.layer, config.layer_hints) else None
        if hint_layer is None and beam_line is not None:
            if layer_matches(beam_line.layer, config.layer_hints):
                hint_layer = beam_line.layer
        if hint_layer is not None:
            features[SEMANTIC_LAYER] = 1.0

        confidence = round(model.score(features), 4)
        notes.extend(model.explain(features))
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.beam_tag,
                entity.text.strip(),
                entity.bbox,
                confidence,
                source_entities,
                "beam_tag_regex_near_linework",
                notes,
                properties,
                entity.source_file,
            )
        )
    return output
