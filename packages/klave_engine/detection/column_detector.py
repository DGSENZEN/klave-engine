"""Column tag detection from text patterns, grid proximity, and marker geometry."""

import math

import numpy as np
from pydantic import BaseModel, Field
from shapely.geometry import Polygon
from shapely.ops import unary_union

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.confidence import (
    MARKER,
    NEAR_GRID,
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
from klave_engine.detection.text_patterns import TextPatternConfig, match_category
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.dxf.text_extent import alto_de_texto
from klave_engine.geometry.bbox import bbox_area, bbox_center
from klave_engine.geometry.forma import Formas, cerrada_por_geometria
from klave_engine.geometry.measurements import polygon_area
from klave_engine.geometry.spatial_index import SpatialIndex


def _marker_section(marker: NormalizedEntity) -> tuple[float | None, str]:
    """Real cross-section area of a column marker in drawing units².

    Circle → π r²; closed polyline or hatch → polygon area; anything else → bbox area.
    """
    if marker.entity_type == EntityType.circle:
        radius = marker.properties.get("radius")
        if radius:
            return 3.141592653589793 * float(radius) ** 2, "marcador_circular"
    if (
        marker.entity_type == EntityType.polyline
        and cerrada_por_geometria(marker)
        and marker.points
        and len(marker.points) >= 3
    ):
        return polygon_area(marker.points), "marcador_poligonal"
    if marker.entity_type == EntityType.hatch and len(marker.points or []) >= 3:
        # A castillo drawn only as its fill (PRUEBA-1: 4 of them): the region it fills.
        return polygon_area(marker.points or []), "marcador_sombreado"
    area = bbox_area(marker.bbox)
    return (area if area > 0 else None), "marcador_bbox"


def _contorno(
    marker: NormalizedEntity, index: SpatialIndex, ajenos: set[str] | None = None
) -> dict:
    """R142: the outline a polygon marker draws with the closed polygons of its layer that touch
    it (an L-shaped castillo drawn as two rectangles): its area, whether it is an axis rectangle
    (area / box ≥ 0.98, one piece), its layer and its pieces. Not for circles or blocks; never
    with a polygon that is another tag's marker (``ajenos``, R150: K-14 beside K-3)."""
    if not (
        marker.entity_type == EntityType.polyline
        and cerrada_por_geometria(marker)
        and marker.points
        and len(marker.points) >= 3
    ):
        return {}
    propio = Polygon(marker.points)
    if not propio.is_valid or propio.area <= 0:
        return {}
    tol = 1e-3 * max(marker.bbox[2] - marker.bbox[0], marker.bbox[3] - marker.bbox[1])
    piezas = [marker]
    for hit in index.entities_near_entity(marker.entity_id, tol):
        otro = index.get(hit.entity_id)
        if (
            otro.entity_id in (ajenos or set())
            or otro.entity_type != EntityType.polyline
            or not cerrada_por_geometria(otro)
            or otro.layer != marker.layer
            or len(otro.points or []) < 3
        ):
            continue
        forma = Polygon(otro.points or [])
        if forma.is_valid and forma.area > 0 and forma.distance(propio) <= tol:
            piezas.append(otro)
    union = unary_union([Polygon(p.points or []) for p in piezas]).buffer(tol).buffer(-tol)
    if not isinstance(union, Polygon):
        union, piezas = propio, [marker]
    x0, y0, x1, y1 = union.bounds
    caja = (x1 - x0) * (y1 - y0)
    return {
        "contorno_area_du2": round(float(union.area), 6),
        "contorno_rectangular": bool(caja > 0 and union.area / caja >= 0.98),
        "contorno_capa": marker.layer,
        "contorno_entidades": sorted(p.entity_id for p in piezas),
    }


class ColumnDetectorConfig(BaseModel):
    grid_search_radius: float = 40.0
    geometry_search_radius: float = 20.0
    max_marker_area: float = 10000.0
    layer_hints: list[str] = Field(
        default_factory=lambda: ["COL", "COLS", "COLUMN", "COLUMNA", "CASTILLO", "DADO"]
    )
    # R175: two markers whose distances differ by at most this (1e-4 m, scaled per unit preset)
    # or a millionth of the distance are equally near: the smallest wins (R130).
    marker_tie_tolerance: float = 0.003
    # R175, R179: the layers of a castillo's or column's own symbol, which beat outlines on other
    # layers — never a dado's (a pile cap, EST-DADOS: Marina K-15 DFC6C's castillo lies 0.025
    # farther than the dado beside it).
    symbol_layer_hints: list[str] = Field(
        default_factory=lambda: ["COL", "COLS", "COLUMN", "COLUMNA", "CASTILLO"]
    )


def detect_columns(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    grid_output: DetectorOutput | None = None,
    config: ColumnDetectorConfig | None = None,
    text_config: TextPatternConfig | None = None,
    detection_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or ColumnDetectorConfig()
    text_config = text_config or TextPatternConfig()
    detection_ids = detection_ids or IdGenerator("det")
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

    model = model_for("column_tag")

    formas = Formas(entities)
    con_marcador: list[tuple[int, str]] = []  # (the tag's detection, its marker)
    # R166: each tag with a marker, for «marcador dudoso»: (its detection, its text, the distance
    # to its marker, its other candidates as (distance, id)).
    elegidos: list[tuple[int, NormalizedEntity, float, list[tuple[float, str]]]] = []
    for entity in entities:
        if not entity.is_textual or not entity.text:
            continue
        if match_category(entity.text, text_config, "column_tag") is None:
            continue

        notes = [f"Text '{entity.text.strip()}' matched column tag pattern"]
        source_entities = [entity.entity_id]
        properties: dict = {"has_nearby_grid": False}
        features: dict[str, float] = {}
        nearest_grid: Detection | None = None
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

        # Marker geometry: a symbol-sized circle, block or closed polyline (closed by its flag
        # or by its last vertex returning to the first) nearby; when found measure its real
        # cross-section so costing uses the actual section.
        # R146: the distance is to what the marker draws (a block's children, a polygon's
        # region), from the rectangle of the tag's letters; the index's boxes only preselect.
        # A block bigger than a marker (a whole planta's walls drawn as one block) is never one.
        # R130: the nearest marker; among equally near ones the smallest, then the first entity
        # id — never the spatial index's own order. A leader's lines are never a marker (R135).
        marker_id: str | None = None
        markers: list[tuple[bool, float, float, str]] = []
        de_columna: set[str] = set()
        for hit in index.entities_near_entity(entity.entity_id, config.geometry_search_radius):
            other = index.get(hit.entity_id)
            if other.is_annotation:
                continue
            is_marker = bbox_area(other.bbox) <= config.max_marker_area and (
                other.entity_type in (EntityType.circle, EntityType.insert)
                or (other.entity_type == EntityType.polyline and cerrada_por_geometria(other))
                or (other.entity_type == EntityType.hatch and len(other.points or []) >= 3)
            )
            if not is_marker:
                continue
            distancia = formas.distancia(entity, other)
            if distancia <= config.geometry_search_radius:
                rellenos = other.entity_type == EntityType.hatch
                markers.append((rellenos, distancia, bbox_area(other.bbox), other.entity_id))
                if layer_matches(other.layer, config.symbol_layer_hints):
                    de_columna.add(other.entity_id)
        if markers:
            # A fill is the marker only of a castillo drawn with nothing else (PRUEBA-1: 4); a
            # castillo's outline and its fill are one symbol, and the outline is what R142 reads.
            if not all(m[0] for m in markers):
                markers = [m for m in markers if not m[0]]
            orden = _por_cercania(
                [m[1:] for m in markers], de_columna, alto_de_texto(entity), config
            )
            marker_id = orden[0][2]
            elegidos.append(
                (len(output.detections), entity, orden[0][0], [(d, i) for d, _a, i in orden[1:]])
            )
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
            con_marcador.append((len(output.detections), marker_id))

        if layer_matches(entity.layer, config.layer_hints):
            features[SEMANTIC_LAYER] = 1.0

        confidence = round(model.score(features), 4)
        notes.extend(model.explain(features))
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.column_tag,
                entity.text.strip(),
                entity.bbox,
                confidence,
                source_entities,
                "column_tag_regex_near_grid",
                notes,
                properties,
                entity.source_file,
            )
        )
    _marcadores_dudosos(output, elegidos, index, formas, text_config)
    # R142, R150: each polygon marker's outline, without the other tags' markers.
    marcadores = {marker_id for _i, marker_id in con_marcador}
    for i, marker_id in con_marcador:
        output.detections[i].properties.update(
            _contorno(index.get(marker_id), index, marcadores - {marker_id})
        )
    return output


# R166: half a text height (see ``_marcadores_dudosos``).
_MARGEN_DE_MARCADOR = 0.5


def _por_cercania(
    markers: list[tuple[float, float, str]],
    de_columna: set[str],
    alto: float,
    config: ColumnDetectorConfig,
) -> list[tuple[float, float, str]]:
    """R130, R175, R179: a tag's markers (distance, area, id), the chosen one first. Within half a
    text height of the nearest (the width a text box may exceed its letters by, R166) a symbol on
    a castillo or column layer beats outlines on other layers — a slab piece, a MUROS1 box, a pile
    cap, an architect's wall outline (Marina K-1 8E092: its castillo 0.0386 farther than a piece of
    EST-LOSA MACIZA; PRUEBA-1 K-1 6701: its 15×15 0.015 farther than an A-WALL outline). Among
    the nearest of those, distances within ``marker_tie_tolerance`` or a millionth are equal —
    never the float sort's noise (C-3 C793B: its castillo 1.8e-5 farther than a pile cap; K-2
    8E264 and 8E288: theirs 1.8e-6 farther than a MUROS1 box) —, a castillo or column layer first,
    then the smallest, then the first id. The others follow by distance."""
    orden = sorted(markers)
    cercania = orden[0][0] + _MARGEN_DE_MARCADOR * alto
    suyos = [m for m in orden if m[0] <= cercania and m[2] in de_columna]
    candidatos = suyos or orden
    d0 = candidatos[0][0]
    empatados = [
        m
        for m in candidatos
        if math.isclose(m[0], d0, rel_tol=1e-6, abs_tol=config.marker_tie_tolerance)
    ]
    elegido = min(empatados, key=lambda m: (m[2] not in de_columna, m[1], m[2]))
    return [elegido, *(m for m in orden if m is not elegido)]


def _marcadores_dudosos(
    output: DetectorOutput,
    elegidos: list[tuple[int, NormalizedEntity, float, list[tuple[float, str]]]],
    index: SpatialIndex,
    formas: Formas,
    text_config: TextPatternConfig,
) -> None:
    """R166: a marker that a tag of another mark reaches about as near — within half a text
    height of this tag's distance, the width the text box may exceed the drawn letters by on a
    side — may be that tag's (PRUEBA-1: K-0 at 0.066 and K-2 at 0.065 from K-2's 15×30, while
    K-0's circle lies at 0.109; K-0's box is 0.065 wider on the left than its «K»). The value is
    kept; the tag says «marcador dudoso» with the other tag and its own next candidate."""
    for i, etiqueta, distancia, siguientes in elegidos:
        detection = output.detections[i]
        marcador = detection.source_entities[-1]
        marca = (etiqueta.text or "").strip()
        margen = _MARGEN_DE_MARCADOR * alto_de_texto(etiqueta)
        otras: list[tuple[float, str]] = []
        for hit in index.entities_near_entity(marcador, distancia + margen):
            otra = index.get(hit.entity_id)
            if otra.entity_id == etiqueta.entity_id or not otra.is_textual or not otra.text:
                continue
            if otra.text.strip() == marca:
                continue
            if match_category(otra.text, text_config, "column_tag") is None:
                continue
            d = formas.distancia(otra, index.get(marcador))
            if d <= distancia + margen:
                otras.append((d, otra.text.strip()))
        if not otras:
            continue
        d_otra, otra_marca = min(otras)
        siguiente = (
            f"el siguiente: {_tipo_de(index.get(siguientes[0][1]))} a {siguientes[0][0]:.3f}"
            if siguientes
            else "no hay otro"
        )
        aviso = (
            f"marcador dudoso: el marcador tomado ({_tipo_de(index.get(marcador))}) está a "
            f"{distancia:.3f} de esta etiqueta y a {d_otra:.3f} de «{otra_marca}», otra marca; "
            f"{siguiente}; se conserva"
        )
        detection.properties["marcador_dudoso"] = aviso
        detection.evidence.notes.append(aviso)


def _tipo_de(marker: NormalizedEntity) -> str:
    area, _fuente = _marker_section(marker)
    nombre = {
        EntityType.circle: "círculo",
        EntityType.polyline: "polilínea",
        EntityType.hatch: "relleno",
        EntityType.insert: "bloque",
    }.get(marker.entity_type, marker.entity_type.value)
    return f"{nombre} de {area:.4g} u²" if area is not None else nombre
