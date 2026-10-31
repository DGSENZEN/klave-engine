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
from klave_engine.detection.instalaciones_symbols import es_trazo_de_simbolo
from klave_engine.detection.results import (
    Detection,
    DetectionType,
    DetectorOutput,
    layer_matches,
    make_detection,
)
from klave_engine.detection.text_patterns import (
    DADO_LAYER_HINTS,
    DADO_MARK_PATTERN,
    FOOTING_MARK_PATTERN,
)
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import bbox_center, bbox_distance
from klave_engine.geometry.forma import Formas
from klave_engine.geometry.measurements import polygon_area, rectangularity
from klave_engine.geometry.spatial_index import SpatialIndex

# Z-1, ZC-2, ZA-3, ZCM-1: zapata marks as the cuadro de zapatas names them.
_ZAPATA_MARK_RE = re.compile(FOOTING_MARK_PATTERN)
_DADO_MARK_RE = re.compile(DADO_MARK_PATTERN)
# Tarea 15b: another outline of the tag's layer at no more than this many times the nearest one's
# distance competes for the tag — the association's «25 % de lados opuestos». On Marina the next
# outline lies 1.5 times as far or more (D-4B 3551C: 0.22 m from its own, 0.33 m from D-3A's),
# except for «D-X», exactly as near D-4's outline as its own.
_COMPITE = 1.25
# One outline lies within another up to this share of the outer one's larger side.
_HOLGURA = 1e-4


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
    # Tarea 15b: on a layer whose name says DADO (Marina: EST-DADOS), the D-n tag written on that
    # same layer labels the outline it lies beside (0.07–0.46 m off it, never on it), when that
    # outline is the nearest of its layer within this reach and no other competes (``_COMPITE``).
    # The layer, not the prefix, says it is a dado (R159). 0 disables it.
    layer_mark_reach: float = 0.0  # drawing units
    layer_mark_hints: list[str] = Field(default_factory=lambda: list(DADO_LAYER_HINTS))
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


def _distancia_a_la_etiqueta(
    contorno: NormalizedEntity, columna: Detection, index: SpatialIndex, formas: Formas
) -> float:
    """From the footing's outline to the letters of a column tag (its first source entity), or to
    the tag's box when its text is not in the index."""
    etiqueta = columna.source_entities[0] if columna.source_entities else None
    try:
        texto = index.get(etiqueta) if etiqueta else None
    except KeyError:
        texto = None
    if texto is None:
        return bbox_distance(contorno.bbox, columna.bbox)
    return formas.distancia(contorno, texto)


class _EtiquetasDeCapa(BaseModel):
    """Lo que las etiquetas de la capa de un dado dicen de cada contorno (por su entity_id): la que
    lo rotula, las que se queda en duda y los contornos de su capa dibujados dentro de él."""

    rotula: dict[str, NormalizedEntity] = Field(default_factory=dict)
    disputadas: dict[str, list[dict]] = Field(default_factory=dict)
    anidados: dict[str, list[dict]] = Field(default_factory=dict)


def _etiquetas_de_capa(
    closed: list[NormalizedEntity],
    entities: list[NormalizedEntity],
    config: FootingDetectorConfig,
    formas: Formas,
) -> _EtiquetasDeCapa:
    """Tarea 15b: qué contorno rotula cada etiqueta D-n escrita en la capa de un dado (una capa
    cuyo nombre dice DADO, ``layer_mark_hints``). La etiqueta es del contorno de su misma capa y
    archivo más cercano a sus letras (la distancia a lo dibujado, R146), a lo más a
    ``layer_mark_reach``, si ningún otro contorno de esa capa queda a no más de ``_COMPITE`` veces
    esa distancia; si otro compite, no es de ninguno y cada uno lo dice nombrando a los dos. Un
    contorno que dos etiquetas escogen tampoco se rotula. Compiten todos los contornos cerrados de
    la capa del tamaño de una zapata o menores (D-X, de 45×45, no es colocación y sí compite); los
    más grandes (un marco) no. Un contorno de la capa dibujado dentro de otro (D-X dentro de D-4)
    se dice en el de afuera, con las etiquetas que lo tocan: nunca se decide ni se cuenta aparte."""
    salida = _EtiquetasDeCapa()
    if config.layer_mark_reach <= 0:
        return salida
    de_capa = [
        e for e in closed
        if layer_matches(e.layer, config.layer_mark_hints)
        and polygon_area(e.points or []) <= config.max_area
    ]  # fmt: skip
    if not de_capa:
        return salida
    capas = {(e.source_file, e.layer) for e in de_capa}
    etiquetas = [
        e for e in entities
        if e.is_textual and e.text and (e.source_file, e.layer) in capas
        and _DADO_MARK_RE.match(e.text.strip().upper())
    ]  # fmt: skip
    escogido: dict[str, list[NormalizedEntity]] = {}
    toca: dict[str, set[str]] = {}  # contorno → las marcas de las etiquetas que lo alcanzan
    for t in etiquetas:
        marca = t.text.strip().upper() if t.text else ""
        cerca = sorted(
            (
                (formas.distancia(c, t), c)
                for c in de_capa
                if c.source_file == t.source_file
                and c.layer == t.layer
                and bbox_distance(c.bbox, t.bbox) <= config.layer_mark_reach
            ),
            key=lambda dc: (dc[0], dc[1].entity_id),
        )
        cerca = [(d, c) for d, c in cerca if d <= config.layer_mark_reach]
        if not cerca:
            continue
        primera = cerca[0][0]
        rivales = [c for d, c in cerca if d <= _COMPITE * primera + 1e-9]
        for c in rivales:
            toca.setdefault(c.entity_id, set()).add(marca)
        if len(rivales) > 1:
            disputa = {
                "marca": marca,
                "entidad": t.entity_id,
                "texto": t.raw_handle,
                "contornos": [c.raw_handle for c in rivales],
            }
            for c in rivales:
                salida.disputadas.setdefault(c.entity_id, []).append(disputa)
            continue
        escogido.setdefault(rivales[0].entity_id, []).append(t)
    for contorno, ts in escogido.items():
        if len(ts) == 1:
            salida.rotula[contorno] = ts[0]
            continue
        handle = next(c.raw_handle for c in de_capa if c.entity_id == contorno)
        for t in ts:
            salida.disputadas.setdefault(contorno, []).append({
                "marca": (t.text or "").strip().upper(),
                "entidad": t.entity_id,
                "texto": t.raw_handle,
                "contornos": [handle],
            })  # fmt: skip
    for afuera in de_capa:
        # A drafting tolerance: Marina's D-X shares D-4's left edge 6e-6 units outside it.
        x0, y0, x1, y1 = afuera.bbox
        region = formas.de(afuera).buffer(_HOLGURA * max(x1 - x0, y1 - y0, 1e-9))
        for adentro in de_capa:
            if (
                adentro is afuera
                or adentro.source_file != afuera.source_file
                or polygon_area(adentro.points or []) >= polygon_area(afuera.points or [])
                or not region.covers(formas.de(adentro))
            ):
                continue
            x0, y0, x1, y1 = adentro.bbox
            salida.anidados.setdefault(afuera.entity_id, []).append({
                "contorno": adentro.raw_handle,
                "lados": [round(x1 - x0, 6), round(y1 - y0, 6)],
                "marcas": sorted(toca.get(adentro.entity_id, set())),
            })  # fmt: skip
    return salida


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
    formas = Formas(entities)

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
        and not es_trazo_de_simbolo(e)
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
    de_capa = _etiquetas_de_capa(closed, entities, config, formas)
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
        if layer_matches(entity.layer, config.layer_mark_hints):
            # Tarea 15b: its layer says DADO; the drawing, not the D- prefix, says what it is.
            properties["familia_de_capa"] = "dado"
        rotulo = de_capa.rotula.get(entity.entity_id)
        if rotulo is not None:
            properties["mark"] = (rotulo.text or "").strip().upper()
            source_entities.append(rotulo.entity_id)
            notes.append(f"Marca {properties['mark']} en su capa, junto al dado")
        if entity.entity_id in de_capa.disputadas:
            properties["etiquetas_disputadas"] = de_capa.disputadas[entity.entity_id]
        if entity.entity_id in de_capa.anidados:
            properties["anidados"] = de_capa.anidados[entity.entity_id]
        if mark_texts and "mark" not in properties:
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

        # R146: the distance from the footing's outline to the letters of the column tag, not
        # between their boxes (the box only preselects).
        nearby_column: Detection | None = None
        nearest = float("inf")
        for column in column_detections:
            if bbox_distance(entity.bbox, column.bbox) > config.column_search_radius:
                continue
            distance = _distancia_a_la_etiqueta(entity, column, index, formas)
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
