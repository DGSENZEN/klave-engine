"""Dimension → element association: the engineer's own cotas, attached to
the element they measure.

A DIMENSION entity is the most explicit statement a drawing makes. The
inventory counts them; this module gives them an owner. A cota that runs
along a footing's edge and spans it is that footing's width or length; two
short perpendicular cotas around a column marker are its section; a short
cota crossing a wall is its thickness. Each link replaces a geometric
estimate with the drawn value and says so — except a section already
declared by a cuadro for the mark, which stays (a cota beside a symbol may
be a spacing, not a section).
"""

from pydantic import BaseModel

from klave_engine.detection.results import Detection, DetectionType
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import BBox, bbox_center, bbox_height, bbox_width

_MIN_SECTION_M, _MAX_SECTION_M = 0.08, 1.2
_MIN_THICKNESS_M, _MAX_THICKNESS_M = 0.08, 0.45
_MIN_FOOTING_M, _MAX_FOOTING_M = 0.4, 6.0


class DimensionLinkStats(BaseModel):
    footings: int = 0
    columns: int = 0
    walls: int = 0

    @property
    def total(self) -> int:
        return self.footings + self.columns + self.walls


class _Cota(BaseModel):
    entity_id: str
    measurement: float  # drawing units
    start: tuple[float, float]
    end: tuple[float, float]

    @property
    def horizontal(self) -> bool:
        return abs(self.end[1] - self.start[1]) <= abs(self.end[0] - self.start[0]) * 0.1

    @property
    def vertical(self) -> bool:
        return abs(self.end[0] - self.start[0]) <= abs(self.end[1] - self.start[1]) * 0.1

    @property
    def midpoint(self) -> tuple[float, float]:
        return ((self.start[0] + self.end[0]) / 2, (self.start[1] + self.end[1]) / 2)

    def interval(self, horizontal: bool) -> tuple[float, float]:
        index = 0 if horizontal else 1
        a, b = self.start[index], self.end[index]
        return (a, b) if a <= b else (b, a)


def _cotas(entities: list[NormalizedEntity]) -> list[_Cota]:
    cotas: list[_Cota] = []
    for entity in entities:
        if entity.entity_type != EntityType.dimension:
            continue
        measurement = entity.properties.get("measurement")
        segment = entity.properties.get("measured_segment")
        if not measurement or not segment or len(segment) != 2:
            continue
        cotas.append(
            _Cota(
                entity_id=entity.entity_id,
                measurement=float(measurement),
                start=(float(segment[0][0]), float(segment[0][1])),
                end=(float(segment[1][0]), float(segment[1][1])),
            )
        )
    return cotas


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def _edge_cota(
    box: BBox, cotas: list[_Cota], horizontal: bool, margin: float
) -> _Cota | None:
    """A cota parallel to one pair of edges, hugging the box, spanning it."""
    extent = (box[0], box[2]) if horizontal else (box[1], box[3])
    size = extent[1] - extent[0]
    if size <= 0:
        return None
    best: tuple[float, _Cota] | None = None
    for cota in cotas:
        if not (cota.horizontal if horizontal else cota.vertical):
            continue
        # Cross-axis distance from the cota line to the nearest parallel edge.
        across = cota.midpoint[1] if horizontal else cota.midpoint[0]
        edges = (box[1], box[3]) if horizontal else (box[0], box[2])
        inside = edges[0] - margin <= across <= edges[1] + margin
        if not inside:
            continue
        covered = _overlap(extent, cota.interval(horizontal)) / size
        if covered < 0.6:
            continue
        # The cota should measure the box, not a neighbour: within 35 %.
        if abs(cota.measurement - size) > 0.35 * size:
            continue
        score = abs(cota.measurement - size)
        if best is None or score < best[0]:
            best = (score, cota)
    return best[1] if best else None


def link_dimensions(
    detections: list[Detection],
    entities: list[NormalizedEntity],
    meters_factor: float | None,
) -> DimensionLinkStats:
    stats = DimensionLinkStats()
    if not meters_factor or meters_factor <= 0:
        return stats
    cotas = _cotas(entities)
    if not cotas:
        return stats
    factor = meters_factor

    def du(meters: float) -> float:
        return meters / factor

    for detection in detections:
        props = detection.properties
        box = detection.bbox
        if detection.detection_type == DetectionType.footing:
            margin = max(du(0.6), 0.3 * min(bbox_width(box), bbox_height(box)))
            candidates = [
                c for c in cotas if _MIN_FOOTING_M <= c.measurement * factor <= _MAX_FOOTING_M
            ]
            width = _edge_cota(box, candidates, True, margin)
            length = _edge_cota(box, candidates, False, margin)
            if width is None or length is None:
                continue
            props["estimated_area_geometry"] = props.get("estimated_area")
            props["dimensioned_width"] = round(width.measurement, 4)
            props["dimensioned_length"] = round(length.measurement, 4)
            props["estimated_area"] = round(width.measurement * length.measurement, 6)
            props["area_source"] = "cota"
            detection.source_entities.extend([width.entity_id, length.entity_id])
            detection.evidence.notes.append(
                f"Acotada en el plano: {width.measurement * factor:.2f} × "
                f"{length.measurement * factor:.2f} m (cotas del plano)"
            )
            stats.footings += 1
        elif detection.detection_type == DetectionType.column_tag:
            if props.get("section_source") == "cuadro":
                continue
            cx, cy = bbox_center(box)
            # Castillos are small; a cota of 40–100 cm beside a K mark is the
            # zapata or a spacing, never the castillo's section.
            max_side = 0.45 if detection.label.strip().upper().startswith("K") else _MAX_SECTION_M
            radius = du(0.5)
            near = [
                c
                for c in cotas
                if _MIN_SECTION_M <= c.measurement * factor <= max_side
                and abs(c.midpoint[0] - cx) <= radius
                and abs(c.midpoint[1] - cy) <= radius
            ]
            horizontal = min(
                (c for c in near if c.horizontal),
                key=lambda c: abs(c.midpoint[0] - cx) + abs(c.midpoint[1] - cy),
                default=None,
            )
            vertical = min(
                (c for c in near if c.vertical),
                key=lambda c: abs(c.midpoint[0] - cx) + abs(c.midpoint[1] - cy),
                default=None,
            )
            if horizontal is None or vertical is None:
                continue
            marker_du2 = props.get("section_area_du2")
            candidate_du2 = horizontal.measurement * vertical.measurement
            # A cota refines the marker it sits on; it does not contradict it.
            if marker_du2 and not (0.5 <= candidate_du2 / float(marker_du2) <= 2.0):
                continue
            a_cm = round(horizontal.measurement * factor * 100)
            b_cm = round(vertical.measurement * factor * 100)
            if "section_area_du2" in props:
                props["section_marker_du2"] = props["section_area_du2"]
            props["section_area_du2"] = round(horizontal.measurement * vertical.measurement, 6)
            props["section_source"] = "cota"
            props["section_cm"] = f"{min(a_cm, b_cm)}x{max(a_cm, b_cm)}"
            detection.source_entities.extend([horizontal.entity_id, vertical.entity_id])
            detection.evidence.notes.append(
                f"Sección acotada en el plano: {min(a_cm, b_cm)}×{max(a_cm, b_cm)} cm"
            )
            stats.columns += 1
        elif detection.detection_type == DetectionType.wall:
            wide = bbox_width(box) >= bbox_height(box)
            candidates = [
                c
                for c in cotas
                if _MIN_THICKNESS_M <= c.measurement * factor <= _MAX_THICKNESS_M
                and (c.vertical if wide else c.horizontal)
                and box[0] - du(0.3) <= c.midpoint[0] <= box[2] + du(0.3)
                and box[1] - du(0.3) <= c.midpoint[1] <= box[3] + du(0.3)
            ]
            if not candidates:
                continue
            current = float(props.get("estimated_thickness") or 0.0)
            cota = min(candidates, key=lambda c: abs(c.measurement - (current or c.measurement)))
            props["estimated_thickness_geometry"] = props.get("estimated_thickness")
            props["estimated_thickness"] = round(cota.measurement, 4)
            props["thickness_source"] = "cota"
            detection.source_entities.append(cota.entity_id)
            detection.evidence.notes.append(
                f"Espesor acotado en el plano: {cota.measurement * factor * 100:.0f} cm"
            )
            stats.walls += 1
    return stats
