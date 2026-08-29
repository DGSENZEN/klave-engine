"""Grid detection: long axis-aligned lines merged into labeled axes, plus
their intersections.

Real sheets do not draw an axis as one line. It arrives as fragments broken
by bubbles and dimension gaps, sometimes as several parallel strokes, and —
on a structural sheet with an architectural background — surrounded by long
wall lines that are not axes at all. So the detector works in layers of
authority: lines on a semantic grid layer (S-GRID, EJE, AXIS) are trusted;
lines elsewhere count only when a grid bubble sits at an endpoint; collinear
fragments of one axis are merged (a gap small enough to be a bubble, not a
neighbouring plan view); and an unlabeled axis between "A" and "C" is
called "B" with a note saying why. Every axis keeps all its fragments as
evidence.
"""

from collections import Counter

from pydantic import BaseModel, Field
from shapely.geometry import LineString

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.confidence import GRID_LABEL, SEMANTIC_LAYER, model_for
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import (
    DetectionType,
    DetectorOutput,
    layer_matches,
    make_detection,
)
from klave_engine.detection.text_patterns import TextPatternConfig, match_category
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import (
    BBox,
    bbox_center,
    bbox_diagonal,
    bbox_expand,
    bbox_height,
    bbox_union_all,
    bbox_width,
)
from klave_engine.geometry.measurements import (
    angles_parallel,
    line_length,
    segment_angle_degrees,
)
from klave_engine.geometry.spatial_index import SpatialIndex

AUTO_LABEL_NOTE = "No grid label found near line endpoints"


class GridDetectorConfig(BaseModel):
    min_relative_length: float = 0.5
    angle_tolerance_deg: float = 2.0
    label_search_radius_factor: float = 0.05  # fraction of drawing extent diagonal
    layer_hints: list[str] = Field(default_factory=lambda: ["GRID", "EJE", "EJES", "AXIS"])
    # When the sheet has a grid layer, lines elsewhere need a bubble to count.
    prefer_semantic_layers: bool = True
    # Fragments within this perpendicular distance (× extent) share an axis.
    collinear_tolerance_factor: float = 0.002
    # Fragments merge across a gap up to max(extent × this, shorter × that):
    # a bubble gap merges, the gap to the next plan view does not.
    merge_gap_extent_factor: float = 0.02
    merge_gap_length_factor: float = 0.15


class _Fragment(BaseModel):
    entity_id: str
    source_file: str
    layer: str
    axis: str  # "horizontal" | "vertical"
    # The sheet frame this fragment lives in: thresholds, label radius and
    # merging are measured against the frame, never against a tiled file.
    frame_id: str | None = None
    start: tuple[float, float]
    end: tuple[float, float]
    length: float
    label: str | None = None
    label_entity_id: str | None = None

    @property
    def coordinate(self) -> float:
        """Position across the axis direction (y for horizontal lines)."""
        return (self.start[1] + self.end[1]) / 2 if self.axis == "horizontal" else (
            self.start[0] + self.end[0]
        ) / 2

    @property
    def span(self) -> tuple[float, float]:
        """Interval along the axis direction."""
        index = 0 if self.axis == "horizontal" else 1
        a, b = self.start[index], self.end[index]
        return (a, b) if a <= b else (b, a)


class _Axis(BaseModel):
    source_file: str
    axis: str
    coordinate: float
    span: tuple[float, float]
    fragments: list[_Fragment]
    label: str | None = None
    label_source: str = "auto"  # bubble | sequence | auto
    label_entity_ids: list[str] = Field(default_factory=list)
    detection_id: str | None = None
    confidence: float = 0.0

    @property
    def start(self) -> tuple[float, float]:
        return (
            (self.span[0], self.coordinate)
            if self.axis == "horizontal"
            else (self.coordinate, self.span[0])
        )

    @property
    def end(self) -> tuple[float, float]:
        return (
            (self.span[1], self.coordinate)
            if self.axis == "horizontal"
            else (self.coordinate, self.span[1])
        )

    @property
    def length(self) -> float:
        return self.span[1] - self.span[0]


def _line_endpoints(entity: NormalizedEntity) -> tuple | None:
    if entity.entity_type == EntityType.line and entity.points:
        return entity.points[0], entity.points[1]
    if (
        entity.entity_type == EntityType.polyline
        and entity.points
        and len(entity.points) == 2
        and not entity.is_closed
    ):
        return entity.points[0], entity.points[1]
    return None


def _nearest_label(
    start: tuple[float, float],
    end: tuple[float, float],
    texts: list[NormalizedEntity],
    radius: float,
    exclude: set[str] | None = None,
) -> tuple[float, NormalizedEntity] | None:
    best: tuple[float, NormalizedEntity] | None = None
    for text_entity in texts:
        if exclude and text_entity.entity_id in exclude:
            continue
        center = bbox_center(text_entity.bbox)
        distance = min(line_length(center, start), line_length(center, end))
        if distance <= radius and (best is None or distance < best[0]):
            best = (distance, text_entity)
    return best


def _merge_fragments(
    fragments: list[_Fragment], extent_dim: float, config: GridDetectorConfig
) -> list[_Axis]:
    """Collinear fragments → axes. Clusters by cross-axis coordinate, then
    merges along the axis while gaps stay bubble-sized."""
    tolerance = extent_dim * config.collinear_tolerance_factor
    gap_floor = extent_dim * config.merge_gap_extent_factor
    axes: list[_Axis] = []
    ordered = sorted(fragments, key=lambda f: f.coordinate)
    cluster: list[_Fragment] = []

    def flush() -> None:
        if not cluster:
            return
        coordinate = sum(f.coordinate for f in cluster) / len(cluster)
        along = sorted(cluster, key=lambda f: f.span[0])
        run: list[_Fragment] = [along[0]]
        for fragment in along[1:]:
            previous_end = max(f.span[1] for f in run)
            gap = fragment.span[0] - previous_end
            shorter = min(fragment.length, max(f.length for f in run))
            if gap <= max(gap_floor, shorter * config.merge_gap_length_factor):
                run.append(fragment)
                continue
            axes.append(_axis_from(run, coordinate))
            run = [fragment]
        axes.append(_axis_from(run, coordinate))
        cluster.clear()

    for fragment in ordered:
        if cluster and abs(fragment.coordinate - cluster[-1].coordinate) > tolerance:
            flush()
        cluster.append(fragment)
    flush()
    return axes


def _axis_from(run: list[_Fragment], coordinate: float) -> _Axis:
    span = (min(f.span[0] for f in run), max(f.span[1] for f in run))
    labels = Counter(f.label for f in run if f.label)
    label = labels.most_common(1)[0][0] if labels else None
    return _Axis(
        source_file=run[0].source_file,
        axis=run[0].axis,
        coordinate=coordinate,
        span=span,
        fragments=run,
        label=label,
        label_source="bubble" if label else "auto",
        label_entity_ids=sorted({f.label_entity_id for f in run if f.label_entity_id}),
    )


def _successor(label: str) -> str | None:
    """'A'→'B', '1'→'2', "A'"→None (primed axes are not sequenced)."""
    if label.isdigit():
        return str(int(label) + 1)
    if len(label) == 1 and label.isalpha() and label.upper() != "Z":
        return chr(ord(label.upper()) + 1)
    return None


def _infer_sequence_labels(axes: list[_Axis]) -> None:
    """Name an unlabeled axis sitting exactly between 'A' and 'C'."""
    ordered = sorted(axes, key=lambda a: a.coordinate)
    for index in range(1, len(ordered) - 1):
        axis = ordered[index]
        if axis.label is not None:
            continue
        before, after = ordered[index - 1], ordered[index + 1]
        if before.label is None or after.label is None:
            continue
        for low, high in ((before.label, after.label), (after.label, before.label)):
            middle = _successor(low)
            if middle is not None and _successor(middle) == high:
                axis.label = middle
                axis.label_source = "sequence"
                break


def detect_grid(
    entities: list[NormalizedEntity],
    index: SpatialIndex,
    config: GridDetectorConfig | None = None,
    text_config: TextPatternConfig | None = None,
    detection_ids: IdGenerator | None = None,
    frames: list[SheetFrame] | None = None,
) -> DetectorOutput:
    config = config or GridDetectorConfig()
    text_config = text_config or TextPatternConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="grid_detector")

    extent = index.extent()
    if extent is None:
        output.warnings.append("Empty drawing: no entities to detect grid lines in")
        return output

    # On a file of tiled sheet frames the file extent is the mosaic, not the
    # sheet: every relative threshold reads against the fragment's own frame.
    frame_list = list(frames or [])

    def _local_extent(frame_id: str | None) -> BBox:
        for f in frame_list:
            if f.frame_id == frame_id:
                return f.bbox
        return extent

    def _frame_of(start: tuple[float, float], end: tuple[float, float]) -> str | None:
        mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        for f in frame_list:
            if f.contains(mid):
                return f.frame_id
        return None

    def _radius(frame_id: str | None) -> float:
        return bbox_diagonal(_local_extent(frame_id)) * config.label_search_radius_factor

    # Within a frame, "long enough to be an axis" se juzga contra el span que
    # la propia malla dibuja (sus líneas en capa semántica), no contra el
    # marco: el contenido nunca llena la hoja, y medir un eje real contra el
    # ancho del cajetín mata la malla horizontal. Sin marcos no aplica.
    grid_span: dict[tuple[str, str], tuple[float, float]] = {}
    if frame_list:
        for entity in entities:
            endpoints = _line_endpoints(entity)
            if endpoints is None or not layer_matches(entity.layer, config.layer_hints):
                continue
            start, end = endpoints
            angle = segment_angle_degrees(start, end)
            if angles_parallel(angle, 0.0, config.angle_tolerance_deg):
                orientation, lo, hi = "horizontal", min(start[0], end[0]), max(start[0], end[0])
            elif angles_parallel(angle, 90.0, config.angle_tolerance_deg):
                orientation, lo, hi = "vertical", min(start[1], end[1]), max(start[1], end[1])
            else:
                continue
            span_frame = _frame_of(start, end)
            if span_frame is None:
                continue
            key = (span_frame, orientation)
            span = grid_span.get(key)
            grid_span[key] = (
                (lo, hi) if span is None else (min(span[0], lo), max(span[1], hi))
            )
    grid_label_texts = [
        e
        for e in entities
        if e.is_textual and e.text and match_category(e.text, text_config, "grid_label")
    ]

    fragments: list[_Fragment] = []
    for entity in entities:
        endpoints = _line_endpoints(entity)
        if endpoints is None:
            continue
        start, end = endpoints
        angle = segment_angle_degrees(start, end)
        length = line_length(start, end)
        frame_id = _frame_of(start, end)
        local = _local_extent(frame_id)
        if angles_parallel(angle, 0.0, config.angle_tolerance_deg):
            orientation, extent_dim = "horizontal", bbox_width(local)
        elif angles_parallel(angle, 90.0, config.angle_tolerance_deg):
            orientation, extent_dim = "vertical", bbox_height(local)
        else:
            continue
        if frame_id is not None:
            span = grid_span.get((frame_id, orientation))
            if span is not None and span[1] - span[0] > 0:
                extent_dim = span[1] - span[0]
        if extent_dim <= 0 or length < config.min_relative_length * extent_dim:
            continue
        fragments.append(
            _Fragment(
                entity_id=entity.entity_id,
                source_file=entity.source_file,
                layer=entity.layer,
                axis=orientation,
                start=start,
                end=end,
                length=length,
                frame_id=frame_id,
            )
        )

    # A bubble names one line: the nearest fragment wins it, so a wall drawn
    # beside an axis cannot borrow the axis's letter.
    claims: dict[str, tuple[float, _Fragment, NormalizedEntity]] = {}
    for fragment in fragments:
        found = _nearest_label(
            fragment.start, fragment.end, grid_label_texts, _radius(fragment.frame_id)
        )
        if found is None or not found[1].text:
            continue
        distance, text_entity = found
        current = claims.get(text_entity.entity_id)
        if current is None or distance < current[0]:
            claims[text_entity.entity_id] = (distance, fragment, text_entity)
    used_labels: set[str] = set()
    for _distance, fragment, text_entity in claims.values():
        fragment.label = (text_entity.text or "").strip()
        fragment.label_entity_id = text_entity.entity_id
        used_labels.add(text_entity.entity_id)

    # Authority: with a grid layer present, unlabeled lines elsewhere are
    # walls, dimensions, or borders — not axes.
    on_grid_layer = [f for f in fragments if layer_matches(f.layer, config.layer_hints)]
    if config.prefer_semantic_layers and on_grid_layer:
        kept = [f for f in fragments if f.label or layer_matches(f.layer, config.layer_hints)]
        dropped = len(fragments) - len(kept)
        if dropped:
            output.warnings.append(
                f"{dropped} líneas largas fuera de la capa de ejes y sin etiqueta "
                "se descartaron como ejes."
            )
        fragments = kept

    # Merge per sheet and orientation, then label the gaps by sequence.
    axes: list[_Axis] = []
    groups: dict[tuple[str, str, str | None], list[_Fragment]] = {}
    for fragment in fragments:
        groups.setdefault(
            (fragment.source_file, fragment.axis, fragment.frame_id), []
        ).append(fragment)
    for (_source, axis_kind, frame_id), members in groups.items():
        local = _local_extent(frame_id)
        extent_dim = bbox_width(local) if axis_kind == "horizontal" else bbox_height(local)
        merged = _merge_fragments(members, extent_dim, config)
        for axis in merged:
            if axis.label is None:
                found = _nearest_label(
                    axis.start, axis.end, grid_label_texts, _radius(frame_id),
                    exclude=used_labels,
                )
                if found is not None and found[1].text:
                    axis.label = found[1].text.strip()
                    axis.label_source = "bubble"
                    axis.label_entity_ids = [found[1].entity_id]
                    used_labels.add(found[1].entity_id)
        _infer_sequence_labels(merged)
        axes.extend(merged)

    model = model_for("grid_line")
    auto_counter: dict[tuple[str, str], int] = {}
    for axis in axes:
        features: dict[str, float] = {}
        if any(layer_matches(f.layer, config.layer_hints) for f in axis.fragments):
            features[SEMANTIC_LAYER] = 1.0
        notes: list[str]
        if axis.label is None:
            key = (axis.source_file, axis.axis)
            auto_counter[key] = auto_counter.get(key, 0) + 1
            prefix = "H" if axis.axis == "horizontal" else "V"
            axis.label = f"{prefix}{auto_counter[key]}"
            notes = [AUTO_LABEL_NOTE, "Sin burbuja de eje cerca de los extremos"]
        elif axis.label_source == "sequence":
            features[GRID_LABEL] = 0.6
            notes = [f"Etiqueta '{axis.label}' inferida por la secuencia de ejes vecinos"]
        else:
            features[GRID_LABEL] = 1.0
            notes = [f"Grid label '{axis.label}' found near line endpoint"]
        if len(axis.fragments) > 1:
            notes.append(f"Eje unido a partir de {len(axis.fragments)} tramos colineales")
        axis.confidence = round(model.score(features), 4)
        notes.extend(model.explain(features))

        detection_id = detection_ids.next()
        axis.detection_id = detection_id
        fragment_ids = [f.entity_id for f in axis.fragments]
        boxes: list[BBox] = [index.get(entity_id).bbox for entity_id in fragment_ids]
        output.detections.append(
            make_detection(
                detection_id,
                DetectionType.grid_line,
                axis.label,
                bbox_union_all(boxes),
                axis.confidence,
                fragment_ids + axis.label_entity_ids,
                "grid_line_axis_aligned_long_line",
                notes,
                {
                    "axis": axis.axis,
                    "length": round(axis.length, 3),
                    "coordinate": round(axis.coordinate, 3),
                    "fragment_count": len(axis.fragments),
                    "label_source": axis.label_source,
                },
                axis.source_file,
            )
        )

    # Intersections of horizontal × vertical axes of the same sheet.
    for source_file in {a.source_file for a in axes}:
        horizontals = [a for a in axes if a.source_file == source_file and a.axis == "horizontal"]
        verticals = [a for a in axes if a.source_file == source_file and a.axis == "vertical"]
        for h in horizontals:
            h_geom = LineString([h.start, h.end])
            for v in verticals:
                point = h_geom.intersection(LineString([v.start, v.end]))
                if point.is_empty or point.geom_type != "Point":
                    continue
                label = f"{h.label}/{v.label}"
                confidence = min(h.confidence, v.confidence)
                point_bbox = bbox_expand((point.x, point.y, point.x, point.y), 1.0)
                output.detections.append(
                    make_detection(
                        detection_ids.next(),
                        DetectionType.grid_intersection,
                        label,
                        point_bbox,
                        confidence,
                        [h.fragments[0].entity_id, v.fragments[0].entity_id],
                        "grid_intersection_of_grid_lines",
                        [f"Intersection of grid lines {h.label} and {v.label}"],
                        {"point": (point.x, point.y)},
                        source_file,
                    )
                )
    return output
