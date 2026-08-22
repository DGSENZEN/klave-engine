"""Slab panels (tableros de losa): faces bounded by trabes, typed by content.

A Mexican structural plan does not draw slabs as closed polylines. It draws
the trabes/contratrabes (and concrete walls) that bound each tablero, fills
the tablero with the pattern of its system — nervaduras for a losa
reticular, vigueta lines for vigueta y bovedilla, a hatch for losa maciza —
and labels the zone: ``LOSA MACIZA H=20``, ``LOSA RETICULAR ALIGERADA
H=30``, ``LOSA DE CIMENTACIÓN H=25``. Openings are crossed out or labeled
VACÍO.

So a tablero is a face of the planar network formed by the beam linework
(ejes close the faces where trabes stop), its family is whatever is drawn
inside it, and its thickness is the ``H=`` on its label — or the nearest
label of the same family on the sheet, with that said in the evidence.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from shapely import STRtree
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.footing_detector import layer_matches
from klave_engine.detection.results import DetectionType, DetectorOutput, make_detection
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import BBox, bbox_area

FAMILY_RETICULAR = "reticular"
FAMILY_VIGUETA = "vigueta_bovedilla"
FAMILY_MACIZA = "maciza"
FAMILY_CIMENTACION = "cimentacion"
FAMILY_SIN_TIPO = "sin_tipo"

_LABEL_RE = re.compile(r"\bLOSA\b", re.I)
_THICKNESS_RE = re.compile(r"\bH\s*=\s*(\d{1,3})", re.I)
_VOID_RE = re.compile(r"VAC[IÍ]O|HUECO|ESCALERA|PATIO|DUCTO|CUBO", re.I)
_FAMILY_TEXT: list[tuple[str, re.Pattern[str]]] = [
    (FAMILY_CIMENTACION, re.compile(r"CIMENTACI", re.I)),
    (FAMILY_MACIZA, re.compile(r"MACIZA", re.I)),
    (FAMILY_RETICULAR, re.compile(r"RETICULAR|NERVAD|ALIGERAD|CASET", re.I)),
    (FAMILY_VIGUETA, re.compile(r"VIGUETA|BOVEDILLA", re.I)),
]


class SlabPanelConfig(BaseModel):
    boundary_layer_hints: list[str] = Field(
        default_factory=lambda: [
            "TRABE", "CONTRATRABE", "BEAM", "VIGA", "MURO", "WALL", "CERRAMIENTO", "DALA",
        ]
    )
    # A closed outline this big on a slab layer is the zone's own boundary
    # (losa reticular drawn as an outlined zone), not a casetón.
    pattern_outline_min_area: float = 4.0
    pattern_min_weight: int = 3  # one hatch (3) or three pattern lines
    grid_layer_hints: list[str] = Field(default_factory=lambda: ["EJE", "GRID", "AXIS"])
    slab_layer_hints: list[str] = Field(default_factory=lambda: ["LOSA", "SLAB"])
    # Short hints apply on slab layers (EST-LOSA VIG Y BOV); the full words
    # identify a slab pattern layer on their own (E-VIGUETAS, CASETONES).
    pattern_layer_families: dict[str, list[str]] = Field(
        default_factory=lambda: {
            FAMILY_RETICULAR: ["NERV", "RETIC", "ALIGER", "CASET"],
            FAMILY_VIGUETA: ["VIG", "BOV"],
            FAMILY_MACIZA: ["MACIZA", "SOLID"],
        }
    )
    standalone_layer_families: dict[str, list[str]] = Field(
        default_factory=lambda: {
            FAMILY_RETICULAR: ["NERVAD", "CASETON", "CASETÓN", "RETICULAR"],
            FAMILY_VIGUETA: ["VIGUETA", "BOVEDILLA"],
            FAMILY_MACIZA: ["MACIZA"],
        }
    )
    # Walls bound rooms, trabes bound tableros: an untyped face is only a
    # tablero when beams (not walls) bound it.
    wall_layer_hints: list[str] = Field(default_factory=lambda: ["MURO", "WALL"])
    min_area: float = 1.0  # drawing units²; scaled from 1 m² by the preset
    max_area: float = 400.0
    min_width: float = 0.6  # thinner faces are the strip between a beam's two lines
    beam_share_min: float = 0.5  # share of the face perimeter that is beam linework
    edge_tolerance: float = 0.03
    label_search_radius: float = 30.0  # nearest same-family label for thickness
    family_inherit_radius: float = 6.0  # an unmarked tablero takes the nearest label's family
    min_boundary_segments: int = 4


@dataclass
class _Face:
    polygon: Polygon
    beam_share: float
    strict_share: float = 0.0  # share bounded by trabes only (walls excluded)
    families: Counter = field(default_factory=Counter)
    pattern_entities: list[str] = field(default_factory=list)
    labels: list[NormalizedEntity] = field(default_factory=list)
    label: NormalizedEntity | None = None
    void_reason: str | None = None
    frame: int = 0


def _as_lines(entities: list[NormalizedEntity]) -> list[LineString]:
    lines: list[LineString] = []
    for e in entities:
        pts = [tuple(p[:2]) for p in (e.points or [])]
        if e.entity_type == EntityType.polyline and e.is_closed and len(pts) >= 3:
            pts = pts + [pts[0]]
        if len(pts) >= 2:
            lines.append(LineString(pts))
    return lines


def _family_from_text(text: str) -> str | None:
    for family, pattern in _FAMILY_TEXT:
        if pattern.search(text):
            return family
    return None


def _family_from_layer(layer: str, config: SlabPanelConfig) -> str | None:
    if layer_matches(layer, config.slab_layer_hints):
        for family, hints in config.pattern_layer_families.items():
            if layer_matches(layer, hints):
                return family
        return None
    for family, hints in config.standalone_layer_families.items():
        if layer_matches(layer, hints):
            return family
    return None


def _center(e: NormalizedEntity) -> Point:
    return Point((e.bbox[0] + e.bbox[2]) / 2, (e.bbox[1] + e.bbox[3]) / 2)


def _is_cross(face: Polygon, lines: list[LineString]) -> bool:
    """Two diagonals joining opposite corners of the face: an opening."""
    minx, miny, maxx, maxy = face.bounds
    tol = 0.04 * max(maxx - minx, maxy - miny)
    corners = [(minx, miny), (maxx, maxy), (minx, maxy), (maxx, miny)]

    def joins(line: LineString, a: tuple[float, float], b: tuple[float, float]) -> bool:
        p, q = line.coords[0], line.coords[-1]
        near = lambda u, v: abs(u[0] - v[0]) <= tol and abs(u[1] - v[1]) <= tol  # noqa: E731
        return (near(p, a) and near(q, b)) or (near(p, b) and near(q, a))

    d1 = any(joins(line, corners[0], corners[1]) for line in lines)
    d2 = any(joins(line, corners[2], corners[3]) for line in lines)
    return d1 and d2


def _faces(
    network: object, beam_edge: object, config: SlabPanelConfig, strict_edge: object = None
) -> list[_Face]:
    """Tableros: faces of the beam+eje network, merged across edges that are
    ejes only (an eje crossing a tablero does not split it), then kept when
    beams bound most of their perimeter and they are not a beam's own strip."""
    raw = [poly for poly in polygonize(network) if poly.area <= 4 * config.max_area]
    if not raw:
        return []
    tree = STRtree(raw)
    parent = list(range(len(raw)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, poly in enumerate(raw):
        for j_raw in tree.query(poly, predicate="touches"):
            j = int(j_raw)
            if j <= i:
                continue
            shared = poly.exterior.intersection(raw[j].exterior)
            if shared.length <= 0:
                continue
            if shared.intersection(beam_edge).length < 0.5 * shared.length:
                parent[find(i)] = find(j)
    groups: dict[int, list[Polygon]] = defaultdict(list)
    for i, poly in enumerate(raw):
        groups[find(i)].append(poly)

    faces: list[_Face] = []
    for members in groups.values():
        merged = unary_union(members)
        parts = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        for polygon in parts:
            if not isinstance(polygon, Polygon):
                continue
            area = polygon.area
            if not (config.min_area <= area <= config.max_area):
                continue
            perimeter = polygon.exterior.length
            if perimeter <= 0 or 4 * area / perimeter < config.min_width:
                continue  # the strip between a beam's two lines
            share = polygon.exterior.intersection(beam_edge).length / perimeter
            if share < config.beam_share_min:
                continue
            strict = (
                polygon.exterior.intersection(strict_edge).length / perimeter
                if strict_edge is not None else share
            )
            faces.append(_Face(polygon=polygon, beam_share=share, strict_share=strict))
    return faces


def _pick_label(face: _Face, config: SlabPanelConfig) -> NormalizedEntity | None:
    """Of the labels inside a tablero, the one that names the system drawn in
    it; else the most repeated family; else the first."""
    if not face.labels:
        return None
    pattern = None
    if face.families and face.families.most_common(1)[0][1] >= config.pattern_min_weight:
        pattern = face.families.most_common(1)[0][0]
    families = Counter(_family_from_text(" ".join((t.text or "").split())) for t in face.labels)
    for t in face.labels:
        if pattern is not None and _family_from_text(" ".join((t.text or "").split())) == pattern:
            return t
    best = families.most_common(1)[0][0]
    for t in face.labels:
        if _family_from_text(" ".join((t.text or "").split())) == best:
            return t
    return face.labels[0]


def _cross_boxes(lines: list[LineString], tolerance: float) -> list[Polygon]:
    """Boxes spanned by two diagonals with the same extent: crossed-out
    openings drawn as loose lines rather than a closed box."""
    groups: dict[tuple[int, int, int, int], list[LineString]] = defaultdict(list)
    step = max(tolerance, 1e-9)
    for line in lines:
        b = line.bounds
        if b[2] - b[0] < 2 * step or b[3] - b[1] < 2 * step:
            continue
        key = (
            int(round(b[0] / step)), int(round(b[1] / step)),
            int(round(b[2] / step)), int(round(b[3] / step)),
        )
        groups[key].append(line)
    boxes: list[Polygon] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        rising = any(
            (m.coords[-1][0] - m.coords[0][0]) * (m.coords[-1][1] - m.coords[0][1]) > 0
            for m in members
        )
        falling = any(
            (m.coords[-1][0] - m.coords[0][0]) * (m.coords[-1][1] - m.coords[0][1]) < 0
            for m in members
        )
        if rising and falling:
            b = unary_union(members).bounds
            boxes.append(Polygon([(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])]))
    return boxes


def detect_slab_panels(
    entities: list[NormalizedEntity],
    config: SlabPanelConfig | None = None,
    detection_ids: IdGenerator | None = None,
    frame_boxes: list[BBox] | None = None,
) -> DetectorOutput:
    config = config or SlabPanelConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="slab_panel_detector")

    linework = [
        e for e in entities
        if e.entity_type in (EntityType.line, EntityType.polyline) and e.points
    ]
    boundary = [e for e in linework if layer_matches(e.layer, config.boundary_layer_hints)]
    # A zone outline on a slab layer (closed, or three sides that walls
    # close) bounds the tablero as much as a trabe does.
    boundary += [
        e for e in linework
        if e.entity_type == EntityType.polyline and len(e.points or []) >= 3
        and _family_from_layer(e.layer, config) is not None
        and bbox_area(e.bbox) >= config.pattern_outline_min_area
    ]
    if len(boundary) < config.min_boundary_segments:
        return output
    grid = [e for e in linework if layer_matches(e.layer, config.grid_layer_hints)]
    beam_lines = _as_lines(boundary)
    beam_union = unary_union(beam_lines)
    network = unary_union(beam_lines + _as_lines(grid))
    beam_edge = beam_union.buffer(config.edge_tolerance)
    strict_lines = _as_lines(
        [e for e in boundary if not layer_matches(e.layer, config.wall_layer_hints)]
    )
    strict_edge = (
        unary_union(strict_lines).buffer(config.edge_tolerance) if strict_lines else None
    )

    faces = _faces(network, beam_edge, config, strict_edge)
    if not faces:
        return output

    tree = STRtree([f.polygon for f in faces])

    def face_at(point: Point) -> _Face | None:
        for idx in tree.query(point, predicate="within"):
            return faces[int(idx)]
        return None

    # What is drawn inside each tablero: its system's pattern and its label.
    labels: list[tuple[NormalizedEntity, str | None, int | None]] = []
    other_lines: dict[int, list[LineString]] = defaultdict(list)
    boundary_ids = {e.entity_id for e in boundary} | {e.entity_id for e in grid}
    void_texts: list[Point] = []
    for e in entities:
        if e.is_textual and e.text:
            text = " ".join(e.text.split())
            face = face_at(_center(e))
            if _LABEL_RE.search(text):
                family = _family_from_text(text)
                match = _THICKNESS_RE.search(text)
                thickness = int(match.group(1)) if match else None
                labels.append((e, family, thickness))
                if face is not None:
                    face.labels.append(e)
            elif _VOID_RE.search(text):
                void_texts.append(_center(e))
                if face is not None:
                    face.void_reason = text[:40]
            continue
        if e.entity_type in (EntityType.line, EntityType.polyline, EntityType.hatch):
            family = _family_from_layer(e.layer, config)
            face = face_at(_center(e))
            if face is None:
                continue
            pts = e.points or []
            if family is not None:
                face.families[family] += 3 if e.entity_type == EntityType.hatch else 1
                face.pattern_entities.append(e.entity_id)
            elif e.entity_id not in boundary_ids and len(pts) == 2:
                other_lines[id(face)].append(LineString([(p[0], p[1]) for p in pts]))

    def nearest_label(
        family: str | None, point: Point, radius: float
    ) -> tuple[NormalizedEntity, str, int | None] | None:
        """Nearest label within radius; of the given family, or any typed
        label when family is None."""
        best: tuple[float, NormalizedEntity, str, int | None] | None = None
        for entity, label_family, label_thickness in labels:
            if label_family is None or (family is not None and label_family != family):
                continue
            if family is not None and label_thickness is None:
                continue
            distance = point.distance(_center(entity))
            if distance <= radius and (best is None or distance < best[0]):
                best = (distance, entity, label_family, label_thickness)
        return (best[1], best[2], best[3]) if best else None

    # Openings drawn inside a tablero: a closed box with a cross or a VACÍO
    # label. They are subtracted; a tablero that is nothing but an opening
    # is dropped.
    all_lines = [
        LineString([(p[0], p[1]) for p in (e.points or [])[:2]])
        for e in linework
        if e.entity_id not in boundary_ids and len(e.points or []) == 2
    ]
    line_tree = STRtree(all_lines) if all_lines else None
    void_boxes: list[Polygon] = []
    for e in linework:
        if e.entity_type != EntityType.polyline or not e.is_closed:
            continue
        pts = [(p[0], p[1]) for p in (e.points or [])]
        if len(pts) not in (4, 5):
            continue
        box = Polygon(pts)
        if not box.is_valid or not (config.min_area * 0.25 <= box.area <= config.max_area):
            continue
        labeled = any(box.contains(pt) for pt in void_texts)
        crossed = False
        if not labeled and line_tree is not None:
            inside = [all_lines[int(i)] for i in line_tree.query(box, predicate="within")]
            crossed = _is_cross(box, inside)
        if labeled or crossed:
            void_boxes.append(box)
    for box in _cross_boxes(all_lines, config.edge_tolerance * 2):
        if config.min_area * 0.25 <= box.area <= config.max_area:
            void_boxes.append(box)
    void_tree = STRtree(void_boxes) if void_boxes else None

    # Sheet frames: a face outside every frame belongs to no sheet; an
    # untyped face only counts on a sheet that labels or patterns its losas.
    def frame_of(polygon: Polygon) -> int:
        if not frame_boxes:
            return 0
        c = polygon.centroid
        for index, box in enumerate(frame_boxes):
            if box[0] <= c.x <= box[2] and box[1] <= c.y <= box[3]:
                return index
        return -1

    typed_frames: set[int] = set()
    for face in faces:
        face.label = _pick_label(face, config)
        face.frame = frame_of(face.polygon)
        if face.label is not None or (
            face.families and face.families.most_common(1)[0][1] >= config.pattern_min_weight
        ):
            typed_frames.add(face.frame)
    if not typed_frames:
        # No tablero on this sheet is labeled or patterned: the drawing does
        # not use the convention, and outline-based slab detection stands.
        return output

    counter = 0
    voids = 0
    untyped = 0
    for face in faces:
        polygon = face.polygon
        if face.frame < 0:
            continue
        has_slab_evidence = face.label is not None or (
            face.families and face.families.most_common(1)[0][1] >= config.pattern_min_weight
        )
        if face.void_reason is None and _is_cross(polygon, other_lines.get(id(face), [])):
            face.void_reason = "cruz de vacío"
        if face.void_reason is not None and not has_slab_evidence:
            voids += 1
            continue
        subtracted = 0.0
        if void_tree is not None:
            holes = [
                void_boxes[int(i)] for i in void_tree.query(polygon, predicate="contains")
            ]
            if holes:
                before = polygon.area
                polygon = polygon.difference(unary_union(holes))
                if polygon.geom_type != "Polygon":
                    polygon = max(polygon.geoms, key=lambda g: g.area)
                subtracted = before - polygon.area

        # A stray leader on a slab layer is not a pattern: one hatch or
        # three lines make a system.
        family = None
        if face.families:
            best_family, weight = face.families.most_common(1)[0]
            if weight >= config.pattern_min_weight:
                family = best_family
        thickness = None
        thickness_source = ""
        label_text = ""
        source_entities = list(face.pattern_entities[:20])
        notes = [
            f"Tablero acotado por trabes/contratrabes ({face.beam_share:.0%} del perímetro)",
            f"Área {polygon.area:.2f} unidades²",
        ]
        if subtracted > 0:
            notes.append(f"Vacíos descontados: {subtracted:.2f} unidades²")
        elif face.void_reason is not None:
            notes.append(
                f"Contiene «{face.void_reason}» sin caja acotada; descontar el vacío manualmente"
            )
        if face.label is not None:
            label_text = " ".join((face.label.text or "").split())
            label_family = _family_from_text(label_text)
            if label_family:
                family = label_family
            match = _THICKNESS_RE.search(label_text)
            if match:
                thickness = int(match.group(1))
                thickness_source = "etiqueta en el tablero"
            source_entities.append(face.label.entity_id)
            notes.append(f"Etiqueta: «{label_text[:60]}»")
        if family is not None and face.families:
            count = sum(face.families.values())
            notes.append(f"Patrón de {family} dibujado en el tablero ({count} elementos)")
        inherited = False
        if family is None and face.strict_share >= 0.8:
            near_any = nearest_label(None, polygon.centroid, config.family_inherit_radius)
            if near_any is not None:
                family, thickness = near_any[1], near_any[2]
                thickness_source = "etiqueta cercana"
                inherited = True
                near_text = (near_any[0].text or "")[:40]
                notes.append(
                    f"Sin patrón ni etiqueta propia; familia y espesor de «{near_text}» "
                    "cercana (confirmar)"
                )
        if family is None:
            if face.strict_share < 0.8 or face.frame not in typed_frames:
                continue  # rooms between walls, patios: not a tablero without evidence
            family = FAMILY_SIN_TIPO
            untyped += 1
            notes.append("Sin patrón ni etiqueta de losa en el tablero; tipo por confirmar")
        if thickness is None and family != FAMILY_SIN_TIPO:
            near = nearest_label(family, polygon.centroid, config.label_search_radius)
            if near is not None:
                thickness = near[2]
                thickness_source = "etiqueta cercana de la misma familia"
                notes.append(
                    f"Espesor H={thickness} tomado de «{(near[0].text or '')[:40]}» cercana"
                )
        if family == FAMILY_SIN_TIPO:
            confidence = 0.55
        elif inherited:
            confidence = 0.6
        else:
            confidence = 0.92 if face.label else 0.85
        counter += 1
        minx, miny, maxx, maxy = polygon.bounds
        bbox: BBox = (minx, miny, maxx, maxy)
        properties = {
            "estimated_area": round(polygon.area, 3),
            "family": family,
            "thickness_cm": thickness,
            "thickness_source": thickness_source,
            "label": label_text,
            "beam_share": round(face.beam_share, 3),
            "void_area": round(subtracted, 3),
            "polygon": [[round(x, 4), round(y, 4)] for x, y in polygon.exterior.coords],
        }
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.slab_region,
                f"TAB{counter}",
                bbox,
                confidence,
                source_entities,
                "slab_panel",
                notes,
                properties,
                face.label.source_file if face.label is not None else (
                    boundary[0].source_file
                ),
            )
        )

    if voids:
        output.warnings.append(
            f"{voids} tableros con vacío/hueco (cruz o etiqueta) no se cuantificaron como losa."
        )
    if untyped:
        output.warnings.append(
            f"{untyped} tableros sin patrón ni etiqueta de losa: se cuantifican como losa sin "
            "tipo (confianza baja); confirmar el sistema en el plano."
        )
    return output
