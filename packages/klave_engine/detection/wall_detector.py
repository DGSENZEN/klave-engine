"""Wall detection from paired parallel lines, merged into walls.

A wall on a sheet is two parallel lines a wall-thickness apart. But so are
a grid axis and its neighbour, a dimension line and its extension, and two
copies of the same line (from a block and from model space, 0.0 apart). So
the detector works by authority: lines on grid, dimension, or text layers
never pair; when the sheet has wall layers (A-WALL, MUROS, TABIQUE) only
those pair; the gap must be a real thickness; and the fragments that CAD
draws for one wall — broken at every door, axis and block boundary — are
merged into one wall per run of collinear pairs.

A wall drawn with its finish (Tarea 15f, R275): Revit draws a compound wall as two nested
outlines on the same layer — the block (core) and, a finish thickness outside it on each side,
the plaster. A line parallel to a wall face, on the wall's layer, ``finish_max`` or less outside
it and overlapping it ``finish_min_overlap`` or more (of the shorter), is that face's finish
boundary, never a face of its own: the wall's thickness is the core's, its length the core's
centreline (each T-joint once: the core of the wall that arrives stops at the core of the one
that receives it), and its openings the gaps both core faces share. A thin line on another
layer (a cancel, an acabado) is never a finish.
"""

from bisect import bisect_left, bisect_right

from pydantic import BaseModel, Field
from shapely.geometry import LineString

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.confidence import GEOM_PLAUSIBLE, SEMANTIC_LAYER, model_for
from klave_engine.detection.instalaciones_symbols import es_trazo_de_simbolo
from klave_engine.detection.results import (
    DetectionType,
    DetectorOutput,
    layer_matches,
    make_detection,
)
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import BBox, bbox_union, bbox_union_all
from klave_engine.geometry.measurements import (
    angles_parallel,
    line_length,
    segment_angle_degrees,
)
from klave_engine.geometry.spatial_index import SpatialIndex


class WallDetectorConfig(BaseModel):
    min_length: float = 100.0
    max_thickness: float = 25.0
    # Two lines closer than this are the same line drawn twice, not a wall.
    min_thickness: float = 0.0
    angle_tolerance_deg: float = 2.0
    min_overlap_ratio: float = 0.5
    layer_hints: list[str] = Field(
        default_factory=lambda: ["WALL", "MURO", "TABIQUE", "TABR", "BLOCK"]
    )
    avoid_layer_hints: list[str] = Field(
        default_factory=lambda: [
            "GRID", "EJE", "EJES", "AXIS", "COTA", "DIM", "DIMENSION", "TEXT", "TXT",
        ]
    )
    # A wall on a concrete-wall layer is cast, not laid: priced in m³, not m².
    concrete_layer_hints: list[str] = Field(
        default_factory=lambda: ["CONCRETO", "CONCRETE", "MURO CONC", "MC", "PANTALLA"]
    )
    prefer_semantic_layers: bool = True
    # Collinear wall pairs merge across gaps up to this (axis breaks and
    # block seams); wider gaps up to ``opening_gap_max`` are doors and
    # windows: the wall continues over them and the gap is kept as an
    # opening on the wall, for the vano deduction.
    merge_gap: float = 0.0
    merge_gap_thickness_factor: float = 2.0
    opening_gap_max: float = 0.0  # drawing units; 0 keeps the old split behaviour
    # Tarea 15f (R275): a same-layer line this close outside a face is its finish (plaster)
    # boundary, not a face (0 turns the reading off); two lines this close are one face.
    finish_max: float = 0.0
    finish_min_overlap: float = 0.9
    face_tolerance: float = 0.0


Segment = tuple[tuple[float, float], tuple[float, float]]


class _WallPair(BaseModel):
    entity_ids: list[str]
    source_file: str
    layer: str
    axis: str  # horizontal | vertical | oblique
    angle: float
    coordinate: float  # position across the wall direction (center line)
    span: tuple[float, float]  # along the wall direction
    thickness: float
    length: float
    bbox: BBox
    semantic: bool
    # Door/window gaps bridged inside this wall, along the wall (drawing units).
    openings: list[float] = []
    # Tarea 15f: read from the wall's faces (``_leer_caras``). ``thickness_from`` is «core» (a
    # finish outline around it was recognised) or «outline» (two faces, nothing else drawn).
    thickness_from: str | None = None
    finish: float | None = None
    outline: float | None = None
    centreline: float | None = None


def _projection_overlap(a: Segment, b: Segment) -> float:
    """Overlap length of two segments projected onto the direction of segment a."""
    (ax1, ay1), (ax2, ay2) = a
    dx, dy = ax2 - ax1, ay2 - ay1
    length = line_length((ax1, ay1), (ax2, ay2))
    if length == 0:
        return 0.0
    ux, uy = dx / length, dy / length

    def project(point: tuple[float, float]) -> float:
        return (point[0] - ax1) * ux + (point[1] - ay1) * uy

    a_interval = sorted([0.0, length])
    b_interval = sorted([project(b[0]), project(b[1])])
    overlap = min(a_interval[1], b_interval[1]) - max(a_interval[0], b_interval[0])
    return max(0.0, overlap)


def _orientation(angle: float, tolerance: float) -> str:
    if angles_parallel(angle, 0.0, tolerance):
        return "horizontal"
    if angles_parallel(angle, 90.0, tolerance):
        return "vertical"
    return "oblique"


def _flush_cluster(
    cluster: list[_WallPair], merged: list[_WallPair], config: WallDetectorConfig
) -> None:
    """Split one collinear cluster into runs separated by real openings."""
    if not cluster:
        return
    cluster.sort(key=lambda p: p.span[0])
    run: list[_WallPair] = [cluster[0]]
    openings: list[float] = []
    for pair in cluster[1:]:
        previous_end = max(p.span[1] for p in run)
        gap = pair.span[0] - previous_end
        allowed = max(config.merge_gap, pair.thickness * config.merge_gap_thickness_factor)
        if gap <= allowed:
            run.append(pair)
        elif gap <= config.opening_gap_max:
            # A door or window: the same wall goes on past it.
            openings.append(gap)
            run.append(pair)
        else:
            merged.append(_merge_run(run, openings))
            run = [pair]
            openings = []
    merged.append(_merge_run(run, openings))
    cluster.clear()


def _merge_pairs(pairs: list[_WallPair], config: WallDetectorConfig) -> list[_WallPair]:
    """Collinear, overlapping-or-nearly-touching pairs become one wall."""
    merged: list[_WallPair] = []
    groups: dict[tuple[str, str], list[_WallPair]] = {}
    for pair in pairs:
        if pair.axis == "oblique":
            merged.append(pair)
            continue
        groups.setdefault((pair.source_file, pair.axis), []).append(pair)
    for members in groups.values():
        members.sort(key=lambda p: (p.coordinate, p.span[0]))
        cluster: list[_WallPair] = []
        for pair in members:
            if cluster and abs(pair.coordinate - cluster[-1].coordinate) > max(
                pair.thickness, cluster[-1].thickness
            ) * 0.75:
                _flush_cluster(cluster, merged, config)
            cluster.append(pair)
        _flush_cluster(cluster, merged, config)
    return merged


def _merge_run(run: list[_WallPair], openings: list[float] | None = None) -> _WallPair:
    if len(run) == 1 and not openings:
        return run[0]
    span = (min(p.span[0] for p in run), max(p.span[1] for p in run))
    return _WallPair(
        openings=list(openings or []),
        entity_ids=[eid for p in run for eid in p.entity_ids],
        source_file=run[0].source_file,
        layer=run[0].layer,
        axis=run[0].axis,
        angle=run[0].angle,
        coordinate=sum(p.coordinate for p in run) / len(run),
        span=span,
        thickness=sum(p.thickness for p in run) / len(run),
        length=span[1] - span[0],
        bbox=bbox_union_all([p.bbox for p in run]),
        semantic=any(p.semantic for p in run),
    )


# A face line: (entity id, position across the wall, start and end along it, layer, whether it
# is long enough to pair: only those make a face; the short ones complete a face's extent).
_Cara = tuple[str, float, float, float, str, bool]
_Tramo = tuple[float, float]


def _caras_por_eje(
    lineas: dict[str, tuple[NormalizedEntity, Segment, float]],
    largas: set[str],
    config: WallDetectorConfig,
) -> dict[str, list[_Cara]]:
    """Every wall line on an axis, by axis, sorted by its position across it."""
    por_eje: dict[str, list[_Cara]] = {"horizontal": [], "vertical": []}
    for eid, (entity, ((x1, y1), (x2, y2)), angle) in lineas.items():
        axis = _orientation(angle, config.angle_tolerance_deg)
        larga = eid in largas
        if axis == "horizontal":
            por_eje[axis].append(
                (eid, (y1 + y2) / 2, min(x1, x2), max(x1, x2), entity.layer, larga)
            )
        elif axis == "vertical":
            por_eje[axis].append(
                (eid, (x1 + x2) / 2, min(y1, y2), max(y1, y2), entity.layer, larga)
            )
    for caras in por_eje.values():
        caras.sort(key=lambda c: c[1])
    return por_eje


def _union(tramos: list[_Tramo]) -> list[_Tramo]:
    juntos: list[_Tramo] = []
    for ini, fin in sorted(tramos):
        if juntos and ini <= juntos[-1][1]:
            juntos[-1] = (juntos[-1][0], max(juntos[-1][1], fin))
        else:
            juntos.append((ini, fin))
    return juntos


def _largo(tramos: list[_Tramo]) -> float:
    return sum(fin - ini for ini, fin in tramos)


def _cruce(a: list[_Tramo], b: list[_Tramo]) -> float:
    return sum(max(0.0, min(fa, fb) - max(ia, ib)) for ia, fa in a for ib, fb in b)


def _huecos(tramos: list[_Tramo]) -> list[_Tramo]:
    return [(a[1], b[0]) for a, b in zip(tramos, tramos[1:], strict=False)]


class _Nivel(BaseModel):
    """One face of a wall: every line at one position across it, clipped to the wall's span."""

    posicion: float
    tramos: list[_Tramo]
    capas: set[str]

    @property
    def extension(self) -> float:
        return self.tramos[-1][1] - self.tramos[0][0]


def _niveles(
    wall: _WallPair, por_eje: dict[str, list[_Cara]], tol: float, banda: float
) -> list[_Nivel]:
    """The wall's faces: the positions of its own lines and of every long wall line along its
    span within ``banda`` outside them (a face the pairing left unpaired is still drawn: the
    core line beside a finish line that took its partner), each with all its lines there, the
    short fragments included."""
    todas = por_eje.get(wall.axis, [])
    suyas = set(wall.entity_ids)
    # The wall's own lines lie inside its box, across it.
    a0, a1 = (wall.bbox[1], wall.bbox[3]) if wall.axis == "horizontal" else (
        wall.bbox[0], wall.bbox[2]
    )
    dentro = todas[
        bisect_left(todas, a0 - tol, key=lambda c: c[1]) :
        bisect_right(todas, a1 + tol, key=lambda c: c[1])
    ]
    propias = [c[1] for c in dentro if c[0] in suyas]
    if not propias:
        return []
    lo, hi = wall.span
    desde, hasta = min(propias) - banda - tol, max(propias) + banda + tol
    caras = todas[
        bisect_left(todas, desde - tol, key=lambda c: c[1]) :
        bisect_right(todas, hasta + tol, key=lambda c: c[1])
    ]
    posiciones = sorted(
        pos for _eid, pos, ini, fin, _capa, larga in caras
        if larga and desde <= pos <= hasta and fin > lo + tol and ini < hi - tol
    )
    grupos: list[list[float]] = []
    for pos in posiciones:
        if grupos and pos - grupos[-1][-1] <= tol:
            grupos[-1].append(pos)
        else:
            grupos.append([pos])
    niveles: list[_Nivel] = []
    for grupo in grupos:
        a, b = grupo[0] - tol, grupo[-1] + tol
        tramos: list[_Tramo] = []
        capas: set[str] = set()
        for _eid, pos, ini, fin, capa, _larga in caras:
            if a <= pos <= b and fin >= lo - tol and ini <= hi + tol:
                tramos.append((max(ini, lo), min(fin, hi)))
                capas.add(capa)
        tramos = [t for t in _union(tramos) if t[1] > t[0]]
        if tramos:
            niveles.append(_Nivel(posicion=sum(grupo) / len(grupo), tramos=tramos, capas=capas))
    return niveles


def _es_aplanado(
    exterior: _Nivel, interior: _Nivel, config: WallDetectorConfig, tol: float
) -> bool:
    """``exterior`` is the finish boundary of the face ``interior``: on the same single layer,
    ``finish_max`` or less away, overlapping it ``finish_min_overlap`` or more of the shorter."""
    distancia = abs(interior.posicion - exterior.posicion)
    if not (tol < distancia <= config.finish_max + tol):
        return False
    if len(exterior.capas) != 1 or exterior.capas != interior.capas:
        return False
    corto = min(_largo(exterior.tramos), _largo(interior.tramos))
    return corto > 0 and _cruce(exterior.tramos, interior.tramos) >= (
        config.finish_min_overlap * corto - 1e-9
    )


def _leer_caras(
    wall: _WallPair, por_eje: dict[str, list[_Cara]], config: WallDetectorConfig
) -> None:
    """Tarea 15f: what the wall's drawn faces say. With a finish outline around a core: the
    core's thickness, centreline length and shared gaps (its openings). With two faces only:
    the outline's centreline, kept aside (``centreline``); the measured length stays."""
    if wall.axis == "oblique":
        return
    tol = config.face_tolerance or 1e-9
    niveles = _niveles(wall, por_eje, tol, config.finish_max)
    nucleo = list(niveles)
    aplanados: list[float] = []
    if config.finish_max > 0:
        if len(nucleo) >= 3 and _es_aplanado(nucleo[0], nucleo[1], config, tol):
            aplanados.append(nucleo[1].posicion - nucleo[0].posicion)
            nucleo = nucleo[1:]
        if len(nucleo) >= 3 and _es_aplanado(nucleo[-1], nucleo[-2], config, tol):
            aplanados.append(nucleo[-1].posicion - nucleo[-2].posicion)
            nucleo = nucleo[:-1]
    if len(nucleo) != 2:
        return
    a, b = nucleo
    espesor = b.posicion - a.posicion
    eje = (a.extension + b.extension) / 2
    if not aplanados:
        wall.thickness_from = "outline"
        wall.centreline = eje
        return
    if not (config.min_thickness <= espesor <= config.max_thickness):
        return
    wall.thickness_from = "core"
    wall.finish = sum(aplanados) / len(aplanados)
    wall.outline = niveles[-1].posicion - niveles[0].posicion
    wall.thickness = espesor
    wall.coordinate = (a.posicion + b.posicion) / 2
    wall.length = eje
    wall.centreline = eje
    if config.opening_gap_max > 0:
        minimo = max(config.merge_gap, espesor * config.merge_gap_thickness_factor)
        vanos: list[float] = []
        for ia, fa in _huecos(a.tramos):
            for ib, fb in _huecos(b.tramos):
                ancho = min(fa, fb) - max(ia, ib)
                if minimo < ancho <= config.opening_gap_max:
                    vanos.append(ancho)
        wall.openings = vanos


def _lo_leido_de_las_caras(wall: _WallPair) -> dict[str, float | str]:
    leido: dict[str, float | str] = {}
    if wall.thickness_from is not None:
        leido["thickness_from"] = wall.thickness_from
    if wall.centreline is not None:
        leido["centreline_length"] = round(wall.centreline, 3)
    if wall.finish is not None:
        leido["finish_thickness"] = round(wall.finish, 3)
    if wall.outline is not None:
        leido["outline_thickness"] = round(wall.outline, 3)
    return leido


def detect_walls(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    config: WallDetectorConfig | None = None,
    detection_ids: IdGenerator | None = None,
) -> DetectorOutput:
    config = config or WallDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="wall_detector")
    model = model_for("wall")

    candidates: dict[str, tuple[NormalizedEntity, Segment, float]] = {
        e.entity_id: (e, (e.points[0], e.points[1]),
                      segment_angle_degrees(e.points[0], e.points[1]))
        for e in entities
        if e.entity_type == EntityType.line
        and e.points
        and line_length(e.points[0], e.points[1]) >= config.min_length
        and not layer_matches(e.layer, config.avoid_layer_hints)
        and not es_trazo_de_simbolo(e)
    }
    # Authority: with wall layers on the sheet, other layers do not pair.
    solo_semanticas = False
    if config.prefer_semantic_layers:
        semantic_ids = {
            eid for eid, (e, _s, _a) in candidates.items()
            if layer_matches(e.layer, config.layer_hints)
        }
        if semantic_ids:
            solo_semanticas = True
            dropped = len(candidates) - len(semantic_ids)
            candidates = {eid: v for eid, v in candidates.items() if eid in semantic_ids}
            if dropped:
                output.warnings.append(
                    f"{dropped} líneas largas fuera de las capas de muros se ignoraron "
                    "al buscar muros."
                )

    used: set[str] = set()
    pairs: list[_WallPair] = []
    for first, first_segment, angle_a in candidates.values():
        if first.entity_id in used:
            continue
        for hit in index.entities_near_entity(first.entity_id, config.max_thickness):
            partner = candidates.get(hit.entity_id)
            if partner is None:
                continue
            second, second_segment, angle_b = partner
            if second.entity_id in used:
                continue
            if not angles_parallel(angle_a, angle_b, config.angle_tolerance_deg):
                continue
            gap = float(LineString(first_segment).distance(LineString(second_segment)))
            if gap < config.min_thickness or gap <= 0 or gap > config.max_thickness:
                continue
            overlap = _projection_overlap(first_segment, second_segment)
            min_len = min(line_length(*first_segment), line_length(*second_segment))
            if min_len == 0 or overlap / min_len < config.min_overlap_ratio:
                continue
            axis = _orientation(angle_a, config.angle_tolerance_deg)
            box = bbox_union(first.bbox, second.bbox)
            if axis == "horizontal":
                coordinate, span = (box[1] + box[3]) / 2, (box[0], box[2])
            elif axis == "vertical":
                coordinate, span = (box[0] + box[2]) / 2, (box[1], box[3])
            else:
                coordinate, span = 0.0, (0.0, overlap)
            pairs.append(
                _WallPair(
                    entity_ids=[first.entity_id, second.entity_id],
                    source_file=first.source_file,
                    layer=first.layer,
                    axis=axis,
                    angle=angle_a,
                    coordinate=coordinate,
                    span=span,
                    thickness=gap,
                    length=overlap,
                    bbox=box,
                    semantic=layer_matches(first.layer, config.layer_hints)
                    or layer_matches(second.layer, config.layer_hints),
                )
            )
            used.update([first.entity_id, second.entity_id])
            break

    walls = _merge_pairs(pairs, config)
    # Tarea 15f: a face is drawn by every line on it, the short fragments too (between two
    # doors, a castillo, a joint): the long ones pair, all of them say where the face runs.
    lineas_de_muro = {
        e.entity_id: (e, (e.points[0], e.points[1]),
                      segment_angle_degrees(e.points[0], e.points[1]))
        for e in entities
        if e.entity_type == EntityType.line
        and e.points
        and (not solo_semanticas or layer_matches(e.layer, config.layer_hints))
        and not layer_matches(e.layer, config.avoid_layer_hints)
        and line_length(e.points[0], e.points[1]) > 0
        and not es_trazo_de_simbolo(e)
    }
    por_eje = _caras_por_eje(lineas_de_muro, set(candidates), config)
    for wall in walls:
        _leer_caras(wall, por_eje, config)
    for counter, wall in enumerate(walls, start=1):
        features: dict[str, float] = {GEOM_PLAUSIBLE: 1.0}
        if wall.semantic:
            features[SEMANTIC_LAYER] = 1.0
        confidence = round(model.score(features), 4)
        segments = len(wall.entity_ids) // 2
        notes = [
            f"Parallel line pair with gap {wall.thickness:.3f} and overlap {wall.length:.1f}",
        ]
        if segments > 1:
            notes.append(f"Muro unido a partir de {segments} tramos colineales")
        if wall.thickness_from == "core" and wall.finish is not None:
            notes.append(
                f"Núcleo de {wall.thickness:.3f} entre las líneas del aplanado "
                f"({wall.finish:.3f} por cara; el contorno de {wall.outline or 0.0:.3f} lo "
                f"incluye): largo al eje del núcleo {wall.length:.3f}"
            )
        if wall.openings:
            notes.append(
                f"{len(wall.openings)} vanos (puerta/ventana) de "
                + ", ".join(f"{gap:.2f}" for gap in wall.openings)
                + " a lo largo del muro"
            )
        notes.extend(model.explain(features))
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.wall,
                f"W{counter}",
                wall.bbox,
                confidence,
                wall.entity_ids,
                "wall_paired_parallel_lines",
                notes,
                {
                    "estimated_length": round(wall.length, 3),
                    "estimated_thickness": round(wall.thickness, 3),
                    "segment_count": segments,
                    # Door/window widths bridged along this wall (drawing units).
                    "openings": [round(gap, 3) for gap in wall.openings],
                    "opening_length": round(sum(wall.openings), 3),
                    "layer": wall.layer,
                    "wall_kind": (
                        "concreto" if layer_matches(wall.layer, config.concrete_layer_hints)
                        else "block"
                    ),
                    **_lo_leido_de_las_caras(wall),
                },
                wall.source_file,
            )
        )
    # Concrete walls are often drawn as their closed outline (a long thin
    # polyline on the concrete-wall layer) rather than two parallel lines.
    for entity in entities:
        if (
            entity.entity_type != EntityType.polyline or not entity.is_closed
            or not entity.points or not layer_matches(entity.layer, config.concrete_layer_hints)
        ):
            continue
        if any(entity.entity_id in d.source_entities for d in output.detections):
            continue
        w = entity.bbox[2] - entity.bbox[0]
        h = entity.bbox[3] - entity.bbox[1]
        length, thickness = max(w, h), min(w, h)
        if thickness < config.min_thickness or thickness > config.max_thickness:
            continue
        if length < config.min_length or length < 3 * thickness:
            continue
        counter += 1
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.wall,
                f"W{counter}",
                entity.bbox,
                0.8,
                [entity.entity_id],
                "wall_concrete_outline",
                [
                    f"Contorno cerrado en capa de muro de concreto {entity.layer}: "
                    f"{length:.2f} × {thickness:.2f}",
                ],
                {
                    "estimated_length": round(length, 3),
                    "estimated_thickness": round(thickness, 3),
                    "segment_count": 1,
                    "layer": entity.layer,
                    "wall_kind": "concreto",
                },
                entity.source_file,
            )
        )
    return output
