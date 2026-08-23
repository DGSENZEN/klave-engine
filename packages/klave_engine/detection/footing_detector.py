"""Footing detection from closed, roughly rectangular polylines."""

import re

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
from klave_engine.geometry.bbox import bbox_center, bbox_distance
from klave_engine.geometry.measurements import polygon_area, rectangularity
from klave_engine.geometry.spatial_index import SpatialIndex

# Z-1, ZC-2, ZA-3, ZCM-1: zapata marks as the cuadro de zapatas names them.
_ZAPATA_MARK_RE = re.compile(r"^Z(?:C|A|CM)?-?\d{1,3}[A-Z]?$")


class FootingDetectorConfig(BaseModel):
    min_area: float = 100.0
    max_area: float = 50000.0
    min_rectangularity: float = 0.75
    high_rectangularity: float = 0.9
    # Zapata corrida: a long strip under a wall. Wider than max_area allows
    # when its short side is a footing's (≤ strip_max_width) and it is at
    # least strip_min_aspect times longer than wide.
    strip_max_width: float = 0.0  # drawing units; 0 disables strips
    strip_min_aspect: float = 4.0
    # Z-1 / ZC-2 / ZA-3: the zapata's mark, read from the text nearest to it.
    mark_search_radius: float = 0.0  # drawing units; 0 disables mark linking
    layer_hints: list[str] = Field(
        default_factory=lambda: ["FOOT", "FOUND", "FDN", "ZAPATA", "ZAP", "CIM", "CIMENT", "DADO"]
    )
    # Closed rectangles on these layers are casetones, ceilings, walls, rebar
    # details, text boxes or frames — never zapatas.
    avoid_layer_hints: list[str] = Field(
        default_factory=lambda: [
            "LOSA", "NERV", "CASET", "PLAF", "ACAB", "TEXT", "COTA", "DIM", "DIMENSION",
            "EJE", "EJES", "GRID", "MARCO", "FRAME", "CAJET", "MUEBLE", "PUERTA",
            "MURO", "WALL", "ARMADO",
        ]
    )
    # Piles are a different concept (ml of pila/pilote); they are counted and
    # reported, never priced as zapatas or dados.
    pile_layer_hints: list[str] = Field(default_factory=lambda: ["PILOT", "PILA"])
    prefer_semantic_layers: bool = True
    # The foundation layer only takes authority when it carries real
    # zapatas; a lone shape on "cimentacion" does not silence the sheet.
    semantic_authority_min: int = 2
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
    closed = [
        e for e in entities
        if e.entity_type == EntityType.polyline and e.is_closed and e.points
        and len(e.points) >= 3 and not layer_matches(e.layer, config.avoid_layer_hints)
    ]
    piles = [e for e in closed if layer_matches(e.layer, config.pile_layer_hints)]
    if piles:
        output.warnings.append(
            f"{len(piles)} pilotes/pilas en capa de pilotes no se cuantifican como zapatas "
            "(concepto de pilas pendiente; revisar en el plano)."
        )
    pile_ids = {e.entity_id for e in piles}
    candidates = [e for e in closed if e.entity_id not in pile_ids]
    # Authority: with a foundation layer on the sheet, only its shapes count.
    if config.prefer_semantic_layers:
        semantic = [e for e in candidates if layer_matches(e.layer, config.layer_hints)]
        if len(semantic) >= config.semantic_authority_min:
            dropped = len(candidates) - len(semantic)
            candidates = semantic
            if dropped:
                output.warnings.append(
                    f"{dropped} contornos cerrados fuera de las capas de cimentación se "
                    "ignoraron al buscar zapatas."
                )
    mark_texts = [
        e for e in entities
        if e.is_textual and e.text and _ZAPATA_MARK_RE.match(e.text.strip().upper())
    ] if config.mark_search_radius > 0 else []
    footing_counter = 0
    for entity in candidates:
        area = polygon_area(entity.points or [])
        width = min(entity.bbox[2] - entity.bbox[0], entity.bbox[3] - entity.bbox[1])
        length = max(entity.bbox[2] - entity.bbox[0], entity.bbox[3] - entity.bbox[1])
        strip = (
            config.strip_max_width > 0
            and width <= config.strip_max_width
            and length >= config.strip_min_aspect * max(width, 1e-9)
            and area >= config.min_area
        )
        if not strip and not (config.min_area <= area <= config.max_area):
            continue
        rect = rectangularity(entity.points or [])
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
        if strip:
            properties["footing_kind"] = "corrida"
            properties["strip_width"] = round(width, 3)
            properties["strip_length"] = round(length, 3)
            notes.append(
                f"Zapata corrida: {length:.2f} de largo × {width:.2f} de ancho (proporción "
                f"{length / max(width, 1e-9):.1f})"
            )
        if mark_texts:
            cx, cy = bbox_center(entity.bbox)
            best: tuple[float, NormalizedEntity] | None = None
            for text in mark_texts:
                tx, ty = bbox_center(text.bbox)
                distance = ((tx - cx) ** 2 + (ty - cy) ** 2) ** 0.5
                inside = (
                    entity.bbox[0] <= tx <= entity.bbox[2]
                    and entity.bbox[1] <= ty <= entity.bbox[3]
                )
                if (inside or distance <= config.mark_search_radius) and (
                    best is None or distance < best[0]
                ):
                    best = (distance, text)
            if best is not None:
                properties["mark"] = (best[1].text or "").strip().upper()
                source_entities.append(best[1].entity_id)
                notes.append(f"Marca {properties['mark']} junto a la zapata")

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
