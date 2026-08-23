"""Locales (rooms) from the wall network of an architectural planta.

Acabados are priced by the room: piso and plafón by its area, aplanado and
pintura by its walls. A planta de arquitectura draws walls as double lines
on wall layers (A-WALL, MUROS, TABIQUE…); the bounded faces of that network
that are wider than a wall and have a room's plausible size are the
locales. The name drawn inside (RECÁMARA, BAÑO, COCINA…) tells whether the
local is interior (plafón, piso) or exterior (patio, terraza, cochera: piso
only) — a local without a name is reported as such, never guessed.

Only plantas in frames are read when the sheet has frames; detail boxes
and legends are never rooms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.results import (
    DetectionType,
    DetectorOutput,
    layer_matches,
    make_detection,
)
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import BBox

EXTERIOR_RE = re.compile(
    r"\b(PATIO|TERRAZA|JARD[IÍ]N|COCHERA|GARAGE|GARAJE|ESTACIONAMIENTO|AZOTEA|"
    r"BALC[OÓ]N|PORCHE|P[OÓ]RTICO|ROOF|ALBERCA|PISCINA|ASADOR|CUBO DE LUZ|VAC[IÍ]O)\b",
    re.IGNORECASE,
)
INTERIOR_RE = re.compile(
    r"\b(REC[AÁ]MARA|RECAMARA|DORMITORIO|BA[ÑN]O|COCINA|SALA|COMEDOR|ESTUDIO|"
    r"VEST[IÍ]BULO|PASILLO|CLOSET|CL[OÓ]SET|VESTIDOR|LAVANDER[IÍ]A|CUARTO|BODEGA|"
    r"OFICINA|FAMILY|ESTANCIA|ANTECOMEDOR|DESPENSA|ESCALERA|HALL|LOBBY|ALACENA|"
    r"TV|GYM|GIMNASIO|CAVA|MEDIO BA[ÑN]O|TOILET|W\.?C\.?)\b",
    re.IGNORECASE,
)
MIN_INTERIOR_NAMES = 2
_AREA_TEXT_RE = re.compile(r"^\s*[\d.,]+\s*M2?\s*$", re.IGNORECASE)
# Texts that belong to structural details, cuadros and sections: a face
# holding one of these is a detail box, never a local.
_STRUCTURAL_TEXT_RE = re.compile(
    r"^\s*(K|C|D|Z|T|CT|CTA|TR|TL|TP|CE|CR|MC|P|ZC|ZA)-?\d+[A-Z]?\s*$|"
    r"\b(COLUMNA|CASTILLO|DADO|ZAPATA|TRABE|CONTRATRABE|DETALLE|CORTE|SECCI[OÓ]N|"
    r"ESC\.?|ESCALA|ARMADO|ESTRIBOS?|VARS?\.?|#\d|@\s*\d|NOTAS?|SIMBOLOG[IÍ]A|CUADRO)\b",
    re.IGNORECASE,
)


class RoomDetectorConfig(BaseModel):
    wall_layer_hints: list[str] = Field(
        default_factory=lambda: ["WALL", "MURO", "TABIQUE", "TABR", "BLOCK", "ARQ", "ARQUITEC"]
    )
    avoid_layer_hints: list[str] = Field(
        default_factory=lambda: [
            "GRID", "EJE", "EJES", "AXIS", "COTA", "DIM", "DIMENSION", "TEXT", "TXT", "HATCH",
        ]
    )
    min_area: float = 1.5  # m²: a closet
    max_area: float = 400.0  # m²: a hall
    min_width: float = 0.7  # m: 4A/P below this is the strip between a wall's lines
    # A local without a name is kept only from this size up (flagged); smaller
    # nameless faces are wall pockets and detail boxes, not rooms.
    unnamed_note_area: float = 4.0
    label_max_height: float = 0.6  # m: room names are small texts
    # Doors and openings break the wall network: two loose wall ends closer
    # than this are joined so the room closes (a door is ≤ 1.2 m).
    max_opening: float = 1.3
    # The two lines of one wall end this close together: joined first as the
    # wall's end face, so openings are measured between wall ends.
    max_thickness: float = 0.45


@dataclass
class _Room:
    polygon: Polygon
    label: NormalizedEntity | None
    kind: str  # interior | exterior | sin_nombre


def _wall_lines(
    entities: list[NormalizedEntity], config: RoomDetectorConfig
) -> tuple[list[LineString], list[str]]:
    lines: list[LineString] = []
    ids: list[str] = []
    for e in entities:
        if e.entity_type not in (EntityType.line, EntityType.polyline):
            continue
        if not layer_matches(e.layer, config.wall_layer_hints):
            continue
        if layer_matches(e.layer, config.avoid_layer_hints):
            continue
        pts = [tuple(p[:2]) for p in (e.points or [])]
        if e.entity_type == EntityType.polyline and e.is_closed and len(pts) >= 3:
            pts = pts + [pts[0]]
        if len(pts) >= 2:
            lines.append(LineString(pts))
            ids.append(e.entity_id)
    return lines, ids


def _close_openings(
    network: BaseGeometry, max_opening: float, max_thickness: float
) -> list[LineString]:
    """Join loose wall ends across door-sized gaps so rooms close.

    Walls are double lines, so an opening leaves four loose ends: first the
    two lines of each wall end are joined (the jamb), then wall ends closer
    than `max_opening` whose joining segment crosses no wall are joined
    through their jamb midpoints; each end joins once, nearest first."""
    segments: list[BaseGeometry] = (
        list(network.geoms) if isinstance(network, MultiLineString) else [network]
    )
    degree: dict[tuple[float, float], int] = {}
    for seg in segments:
        if not isinstance(seg, LineString):
            continue
        coords = list(seg.coords)
        if len(coords) < 2:
            continue
        for pt in (coords[0], coords[-1]):
            key = (round(pt[0], 4), round(pt[1], 4))
            degree[key] = degree.get(key, 0) + 1
    dangles = [Point(p) for p, d in degree.items() if d == 1]
    if len(dangles) < 2:
        return []

    def pair_up(points: list[Point], reach: float, check_cross: bool) -> list[tuple[int, int]]:
        tree = STRtree(points)
        pairs: list[tuple[float, int, int]] = []
        for i, pt in enumerate(points):
            for j_raw in tree.query(pt.buffer(reach)):
                j = int(j_raw)
                if j <= i:
                    continue
                dist = pt.distance(points[j])
                if 0 < dist <= reach:
                    pairs.append((dist, i, j))
        pairs.sort()
        used: set[int] = set()
        chosen: list[tuple[int, int]] = []
        for _dist, i, j in pairs:
            if i in used or j in used:
                continue
            if check_cross and network.crosses(LineString([points[i], points[j]])):
                continue
            used.update((i, j))
            chosen.append((i, j))
        return chosen

    closures: list[LineString] = []
    jambs = pair_up(dangles, max_thickness, check_cross=False)
    paired = {i for pair in jambs for i in pair}
    wall_ends: list[Point] = []
    for i, j in jambs:
        closures.append(LineString([dangles[i], dangles[j]]))
        wall_ends.append(Point(
            (dangles[i].x + dangles[j].x) / 2, (dangles[i].y + dangles[j].y) / 2
        ))
    wall_ends.extend(pt for k, pt in enumerate(dangles) if k not in paired)
    for i, j in pair_up(wall_ends, max_opening, check_cross=True):
        closures.append(LineString([wall_ends[i], wall_ends[j]]))
    return closures


def _kind(text: str) -> str:
    if EXTERIOR_RE.search(text):
        return "exterior"
    if INTERIOR_RE.search(text):
        return "interior"
    return "sin_nombre"


def detect_rooms(
    entities: list[NormalizedEntity],
    config: RoomDetectorConfig | None = None,
    detection_ids: IdGenerator | None = None,
    frame_boxes: list[BBox] | None = None,
) -> DetectorOutput:
    config = config or RoomDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="room_detector")
    lines, _ids = _wall_lines(entities, config)
    if len(lines) < 8:
        return output  # a planta with walls has dozens of wall lines
    # Room names: small texts, the ones that name a room first. A sheet that
    # names no local at all is not a planta de arquitectura (a structural
    # set draws walls too): nothing is read, and the sheet says why.
    texts = [
        e for e in entities
        if e.is_textual and e.text
        and float((e.properties or {}).get("height") or 0.0) <= config.label_max_height
        and not _AREA_TEXT_RE.match(e.text)
    ]
    # Exterior words alone (AZOTEA, ALBERCA) and a stray ESCALERA appear on
    # structural sheets too; an architectural planta names several
    # different interior locales.
    interior_names: set[str] = set()
    for t in texts:
        words = (t.text or "").split()
        match = INTERIOR_RE.search(t.text or "") if 0 < len(words) <= 3 else None
        if match is not None:  # a room label is the name itself, not a note naming it
            interior_names.add(match.group(0).upper())
    if len(interior_names) < MIN_INTERIOR_NAMES:
        output.warnings.append(
            "Locales: la hoja no nombra locales interiores (recámara, baño, cocina…); "
            "no se leyeron locales ni acabados de ella."
        )
        return output
    network: BaseGeometry = unary_union(lines)
    closures = _close_openings(network, config.max_opening, config.max_thickness)
    if closures:
        network = unary_union([network, *closures])
    faces = [
        poly for poly in polygonize(network)
        if config.min_area <= poly.area <= config.max_area
        and poly.exterior.length > 0
        and 4 * poly.area / poly.exterior.length >= config.min_width
    ]
    if not faces:
        return output
    # A face that contains other faces is the building outline or a wing,
    # not a local: keep the innermost faces only.
    tree = STRtree(faces)
    innermost: list[Polygon] = []
    for i, face in enumerate(faces):
        inner = [
            j for j in tree.query(face, predicate="contains_properly") if int(j) != i
        ]
        if not inner:
            innermost.append(face)
    if frame_boxes:
        def in_frame(poly: Polygon) -> bool:
            c = poly.centroid
            return any(b[0] <= c.x <= b[2] and b[1] <= c.y <= b[3] for b in frame_boxes)
        innermost = [f for f in innermost if in_frame(f)]
    text_points = [Point((e.bbox[0] + e.bbox[2]) / 2, (e.bbox[1] + e.bbox[3]) / 2) for e in texts]
    text_tree = STRtree(text_points) if text_points else None
    counter = 0
    for polygon in innermost:
        label: NormalizedEntity | None = None
        kind = "sin_nombre"
        inside: list[NormalizedEntity] = []
        if text_tree is not None:
            inside = [texts[int(i)] for i in text_tree.query(polygon, predicate="contains")]
            named = [t for t in inside if _kind(t.text or "") != "sin_nombre"]
            label = named[0] if named else (inside[0] if inside else None)
            if label is not None:
                kind = _kind(label.text or "")
        if kind == "sin_nombre":
            if any(_STRUCTURAL_TEXT_RE.search(t.text or "") for t in inside):
                continue  # a detail box or a cuadro, not a local
            if polygon.area < config.unnamed_note_area:
                continue  # nameless and small: a pocket between walls
        counter += 1
        notes: list[str] = []
        if label is None:
            notes.append("Local sin nombre en el plano; uso por confirmar")
        elif kind == "sin_nombre":
            notes.append(f"Texto «{(label.text or '')[:40]}» no nombra un local conocido")
        minx, miny, maxx, maxy = polygon.bounds
        confidence = 0.85 if kind != "sin_nombre" else 0.6
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.room,
                f"LOC{counter}",
                (minx, miny, maxx, maxy),
                confidence,
                [label.entity_id] if label is not None else [],
                "room_from_wall_network",
                notes,
                {
                    "estimated_area": round(polygon.area, 3),
                    "perimeter": round(polygon.exterior.length, 3),
                    "label": " ".join((label.text or "").split())[:60] if label else "",
                    "room_kind": kind,
                    "polygon": [[round(x, 4), round(y, 4)] for x, y in polygon.exterior.coords],
                },
                label.source_file if label is not None else entities[0].source_file,
            )
        )
    return output
