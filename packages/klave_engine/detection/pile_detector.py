"""Pilotes: a P-n mark standing on its circle in the cimentación.

A pile is drawn as a circle (or a small block) on a pile layer with the
mark beside it — P-4 — and its length lives in the notes or the detail,
never in plan. Here each mark becomes one pile with the diameter of the
circle it stands on; the length is not invented.
"""

import re

from pydantic import BaseModel, Field

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.footing_detector import layer_matches
from klave_engine.detection.results import DetectionType, DetectorOutput, make_detection
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import bbox_center
from klave_engine.geometry.spatial_index import SpatialIndex

_PILE_MARK_RE = re.compile(r"^P-?\d{1,2}[A-Z]?$")


class PileDetectorConfig(BaseModel):
    layer_hints: list[str] = Field(default_factory=lambda: ["PILOT", "PILA", "PILE"])
    circle_search_radius: float = 1.5  # drawing units; scaled by the preset
    min_diameter: float = 0.2
    max_diameter: float = 2.5


def _roughly_round(entity: NormalizedEntity) -> bool:
    w = entity.bbox[2] - entity.bbox[0]
    h = entity.bbox[3] - entity.bbox[1]
    return w > 0 and h > 0 and 0.8 <= w / h <= 1.25


def detect_piles(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    config: PileDetectorConfig | None = None,
    detection_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or PileDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="pile_detector")
    # A pile in plan is a circle, or an octagon/hatch standing for one.
    circles = [
        e for e in entities
        if layer_matches(e.layer, config.layer_hints)
        and (
            e.entity_type == EntityType.circle
            or (
                e.entity_type in (EntityType.polyline, EntityType.hatch)
                and e.points and len(e.points) >= 3
                and _roughly_round(e)
            )
        )
    ]
    if not circles:
        return output
    counter = 0
    for text in entities:
        if not text.is_textual or not text.text:
            continue
        mark = text.text.strip().upper()
        if not _PILE_MARK_RE.match(mark):
            continue
        cx, cy = bbox_center(text.bbox)
        best: tuple[float, NormalizedEntity] | None = None
        for circle in circles:
            ccx, ccy = bbox_center(circle.bbox)
            distance = ((ccx - cx) ** 2 + (ccy - cy) ** 2) ** 0.5
            if distance <= config.circle_search_radius and (best is None or distance < best[0]):
                best = (distance, circle)
        if best is None:
            continue
        circle = best[1]
        if any(circle.entity_id in d.source_entities for d in output.detections):
            continue  # one symbol, one pile — even with the mark written twice
        diameter = circle.bbox[2] - circle.bbox[0]
        if not (config.min_diameter <= diameter <= config.max_diameter):
            continue
        counter += 1
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.pile,
                mark,
                circle.bbox,
                0.85,
                [text.entity_id, circle.entity_id],
                "pile_mark_on_circle",
                [
                    f"Marca {mark} sobre un círculo de Ø{diameter:.3f} en capa {circle.layer}",
                    "Longitud del pilote: por notas o detalle, no se infiere del plano",
                ],
                {"diameter": round(diameter, 3), "layer": circle.layer},
                text.source_file,
            )
        )
    if counter:
        output.warnings.append(
            f"{counter} pilotes contados por su marca; su longitud no está en planta — "
            "el concepto se cuantifica por pieza y el precio debe adoptarse del catálogo."
        )
    return output
