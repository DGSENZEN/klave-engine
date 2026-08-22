"""Per-sheet units: every file declares (or betrays) its own unit; the
project works in one.

A set of sheets rarely agrees: the índice is in inches, the structural plan
in metres, a detail file in centimetres. Each file gets its own unit read
(header, then the cotas and heuristics of that file alone); the unit of
the file with the most geometry becomes the project's, and every other
file whose unit is reliable and different is scaled into it — bboxes,
points, radii, text heights, dimension measurements — with the scaling
recorded on the project. A file whose unit cannot be read is assumed to
share the project's, and that assumption is written down too.
"""

from dataclasses import dataclass

from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.dxf.units import METERS_FACTOR, DrawingUnits, detect_units
from klave_engine.geometry.bbox import BBox, bbox_union_all

_POINT_PROPS = ("insert", "center")
_LENGTH_PROPS = ("radius", "height", "measurement")
_POINTS_PROPS = ("measured_segment", "span")


@dataclass
class FileUnits:
    source_file: str
    units: DrawingUnits
    entity_count: int
    scale: float = 1.0  # factor applied to bring the file into the project unit


def _extent(entities: list[NormalizedEntity]) -> BBox | None:
    boxes = [e.bbox for e in entities]
    return bbox_union_all(boxes) if boxes else None


def scale_entity(entity: NormalizedEntity, k: float) -> None:
    """Scale one entity's geometry in place by k (drawing units → drawing
    units of the project). Displayed cota text is what the engineer wrote
    and stays; dimlfac follows so display = measurement × dimlfac still holds."""
    if k == 1.0:
        return
    x0, y0, x1, y1 = entity.bbox
    entity.bbox = (x0 * k, y0 * k, x1 * k, y1 * k)
    if entity.points:
        entity.points = [(p[0] * k, p[1] * k) for p in entity.points]
    ev = entity.evidence
    if ev is not None and ev.bbox is not None:
        bx0, by0, bx1, by1 = ev.bbox
        ev.bbox = (bx0 * k, by0 * k, bx1 * k, by1 * k)
    props = entity.properties
    if not props:
        return
    for key in _POINT_PROPS:
        value = props.get(key)
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            props[key] = (float(value[0]) * k, float(value[1]) * k)
    for key in _LENGTH_PROPS:
        value = props.get(key)
        if isinstance(value, (int, float)):
            props[key] = float(value) * k
    for key in _POINTS_PROPS:
        value = props.get(key)
        if isinstance(value, list):
            props[key] = [(float(p[0]) * k, float(p[1]) * k) for p in value if len(p) >= 2]
    dimlfac = props.get("dimlfac")
    if isinstance(dimlfac, (int, float)) and "measurement" in props:
        props["dimlfac"] = float(dimlfac) / k


def harmonize_units(
    files: list[tuple[str, int | None, list[NormalizedEntity]]],
) -> tuple[DrawingUnits, list[FileUnits]]:
    """Read each file's unit, pick the project's, scale the others in place.

    `files` is (source_file, $INSUNITS, entities). Returns the project units
    (with per-file notes) and the per-file record.
    """
    per_file: list[FileUnits] = []
    for source, insunits, entities in files:
        per_file.append(
            FileUnits(source, detect_units(insunits, entities, _extent(entities)), len(entities))
        )
    if not per_file:
        return DrawingUnits(), []
    reliable = [f for f in per_file if f.units.reliable]
    leader = max(reliable or per_file, key=lambda f: f.entity_count)
    project = leader.units.model_copy(deep=True)
    project_m = METERS_FACTOR.get(project.unit)
    for record in per_file:
        name = record.source_file.rsplit("/", 1)[-1]
        unit = record.units
        if record is leader:
            if len(per_file) > 1:
                project.notes.append(
                    f"Unidad del proyecto tomada de «{name}» ({unit.unit}, {unit.source}), "
                    "la hoja con más geometría."
                )
            continue
        if not unit.reliable or project_m is None:
            project.notes.append(
                f"«{name}»: unidad no determinable ({unit.unit}, {unit.source}); se asume "
                f"{project.unit} como el proyecto."
            )
            continue
        file_m = METERS_FACTOR.get(unit.unit)
        if file_m is None or unit.unit == project.unit:
            continue
        record.scale = file_m / project_m
        for entity in [e for _s, _i, ents in files if _s == record.source_file for e in ents]:
            scale_entity(entity, record.scale)
        project.notes.append(
            f"«{name}» está en {unit.unit} ({unit.source}); su geometría se escaló "
            f"×{record.scale:g} a {project.unit}."
        )
    return project, per_file
