"""Beam tag detection: beam-pattern text associated with nearby linework."""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

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
from klave_engine.geometry.bbox import Point, bbox_center
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
        # nearer axis must not win over the trabe line beside it. A leader's
        # lines are annotation, never a trabe (R135).
        candidates: list[_Candidata] = []
        for hit in index.entities_near_entity(entity.entity_id, config.line_search_radius):
            other = index.get(hit.entity_id)
            if other.entity_type not in (EntityType.line, EntityType.polyline):
                continue
            if other.is_closed or not other.points or other.is_annotation:
                continue
            length = polyline_length(other.points)
            if not (config.min_beam_length <= length <= config.max_beam_length):
                continue
            if layer_matches(other.layer, config.avoid_layer_hints):
                continue
            on_beam_layer = layer_matches(other.layer, config.layer_hints)
            candidates.append(
                _Candidata(0 if on_beam_layer else 1, float(hit.distance), other, length)
            )
        beam_line, dudoso = _linea_de_la_trabe(
            candidates, bbox_center(entity.bbox), config.line_search_radius
        )
        if beam_line is not None:
            span = polyline_length(beam_line.points or [])
            features[NEAR_LINE] = 1.0
            source_entities.append(beam_line.entity_id)
            properties["estimated_span_length"] = round(span, 3)
            properties["span_layer"] = beam_line.layer
            notes.append(f"Associated with linework of length {span:.1f}")
            if layer_matches(beam_line.layer, config.layer_hints):
                notes.append(f"Línea de trabe en capa {beam_line.layer}")
            if dudoso is not None:
                properties["claro_dudoso"] = dudoso
                notes.append(dudoso)

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


@dataclass(frozen=True)
class _Candidata:
    """A line a trabe tag may belong to: its layer preference (0 on a beam layer), its distance
    to the tag, the line and its length."""

    preferencia: int
    distancia: float
    linea: NormalizedEntity
    largo: float


# Two candidates whose lengths differ by more than this share of the longer one make the span
# doubtful when they are equally near (R135).
_CLARO_DUDOSO = 0.10


def _linea_de_la_trabe(
    candidatas: list[_Candidata], centro: Point, radio: float
) -> tuple[NormalizedEntity | None, str | None]:
    """The tag's line: the preferred layer, then the nearest; among lines equally near (within
    a millionth of the search radius) the one whose midpoint is nearest the tag's centre, then
    the first entity id — never the spatial index's order (R135). When the tied lines' lengths
    differ by more than 10 %, the span is doubtful and the aviso says so."""
    if not candidatas:
        return None, None
    mejor = min((c.preferencia, c.distancia) for c in candidatas)
    holgura = radio * 1e-6
    empatadas = [
        c for c in candidatas if c.preferencia == mejor[0] and c.distancia <= mejor[1] + holgura
    ]
    elegida = min(
        empatadas,
        key=lambda c: (
            math.dist(centro, _punto_medio(c.linea.points or [])),
            _orden_de_id(c.linea.entity_id),
        ),
    )
    distintas = [
        c
        for c in empatadas
        if abs(c.largo - elegida.largo) > _CLARO_DUDOSO * max(c.largo, elegida.largo)
    ]
    if not distintas:
        return elegida.linea, None
    largos = ", ".join(f"{v:g}" for v in sorted({round(c.largo, 3) for c in empatadas}))
    return elegida.linea, (
        f"claro dudoso: {len(empatadas)} líneas igual de cerca de la etiqueta, de largos "
        f"{largos}; se toma la de {round(elegida.largo, 3):g}, la de punto medio más cercano"
    )


def _punto_medio(puntos: Sequence[Point]) -> Point:
    """The point halfway along the line."""
    falta = polyline_length(puntos) / 2
    for a, b in zip(puntos, puntos[1:], strict=False):
        tramo = math.dist(a, b)
        if tramo >= falta and tramo > 0:
            f = falta / tramo
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        falta -= tramo
    return puntos[-1] if puntos else (0.0, 0.0)


def _orden_de_id(entity_id: str) -> tuple[tuple[int, int | str], ...]:
    """An entity id in its natural order: «ent_9» before «ent_10»."""
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in re.findall(r"\d+|\D+", entity_id))
