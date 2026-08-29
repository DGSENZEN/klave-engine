"""Wall detection from paired parallel lines, merged into walls.

A wall on a sheet is two parallel lines a wall-thickness apart. But so are
a grid axis and its neighbour, a dimension line and its extension, and two
copies of the same line (from a block and from model space, 0.0 apart). So
the detector works by authority: lines on grid, dimension, or text layers
never pair; when the sheet has wall layers (A-WALL, MUROS, TABIQUE) only
those pair; the gap must be a real thickness; and the fragments that CAD
draws for one wall — broken at every door, axis and block boundary — are
merged into one wall per run of collinear pairs.
"""

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
    if config.prefer_semantic_layers:
        semantic_ids = {
            eid for eid, (e, _s, _a) in candidates.items()
            if layer_matches(e.layer, config.layer_hints)
        }
        if semantic_ids:
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
