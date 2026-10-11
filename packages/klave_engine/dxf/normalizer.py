
"""Normalize ezdxf entities into NormalizedEntity records.

Every supported entity gets a bbox. A text's bbox is its real extent (R146): the anchor its
alignment or attachment fixes, its lines, its width (the CAD's own for an aligned TEXT, else
estimated per character) and its rotation — ``klave_engine.dxf.text_extent``; the estimate is
noted in the evidence packet.
"""

import re
from typing import Any

from ezdxf import bbox as ezdxf_bbox

from klave_engine.common.ids import IdGenerator
from klave_engine.dxf.entities import EntityType, NormalizedEntity, ParseWarning
from klave_engine.dxf.text_extent import ANCHO_POR_CARACTER, extension_de_texto
from klave_engine.geometry.bbox import BBox, Point, bbox_from_points
from klave_engine.graph.evidence import EvidencePacket

SUPPORTED_DXF_TYPES = {
    "LINE",
    "LWPOLYLINE",
    "POLYLINE",
    "ARC",
    "CIRCLE",
    "ELLIPSE",
    "SPLINE",
    "SOLID",
    "TRACE",
    "3DFACE",
    "LEADER",
    "HATCH",
    "TEXT",
    "MTEXT",
    "INSERT",
    "DIMENSION",
}

# Curves flatten into at most this many segments; enough for detection and
# rendering without letting one dense spline dominate the entity budget.
MAX_FLATTEN_POINTS = 200


# What the evidence says of a text's box.
_TEXT_EXTENT_NOTE = (
    "Caja del texto: donde lo ponen su alineación y su giro; su ancho, el del CAD en un texto "
    f"alineado, si no {ANCHO_POR_CARACTER:g} × alto por carácter"
)

_DISPLAY_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")
# The paragraph alignment an MTEXT sets inline (``\pxqc;`` = centred in its column).
# Lowercase only: ``\P`` is a paragraph break, not a paragraph property.
_MTEXT_PARAGRAPH_ALIGN = re.compile(r"\\p[^;\\]*?q([lrcjd])")


def _dimension_display_text(entity: Any) -> str | None:
    override = str(entity.dxf.get("text", "") or "").strip()
    if override and override != "<>":
        return override.replace("<>", "").strip() or None
    try:
        block = entity.get_geometry_block()
    except Exception:
        return None
    if block is None:
        return None
    for child in block:
        kind = child.dxftype()
        if kind == "MTEXT":
            text = child.plain_text()
        elif kind == "TEXT":
            text = str(child.dxf.text)
        else:
            continue
        text = " ".join(text.split())
        if text:
            return text
    return None


def _parse_display_value(text: str) -> float | None:
    match = _DISPLAY_NUMBER.search(text.replace("%%C", "").replace("Ø", ""))
    if not match:
        return None
    try:
        return abs(float(match.group(0).replace(",", ".")))
    except ValueError:
        return None


def _flatten_curve(entity: Any) -> list[Point]:
    """Approximate a SPLINE/ELLIPSE with line segments sized to the curve."""
    try:
        extents = ezdxf_bbox.extents([entity], fast=True)
        span = (
            max(extents.extmax.x - extents.extmin.x, extents.extmax.y - extents.extmin.y)
            if extents.has_data
            else 1.0
        )
        distance = max(span / 200.0, 1e-6)
        points = [(float(p.x), float(p.y)) for p in entity.flattening(distance)]
    except Exception:
        return []
    if len(points) > MAX_FLATTEN_POINTS:
        step = len(points) / MAX_FLATTEN_POINTS
        points = [points[int(i * step)] for i in range(MAX_FLATTEN_POINTS)] + [points[-1]]
    return points


def _corner_points(entity: Any) -> list[Point]:
    """SOLID/TRACE/3DFACE corners (DXF stores the third pair swapped)."""
    corners: list[Point] = []
    for attr in ("vtx0", "vtx1", "vtx3", "vtx2"):
        if entity.dxf.hasattr(attr):
            vertex = entity.dxf.get(attr)
            corners.append((float(vertex.x), float(vertex.y)))
    # Drop the duplicate closing corner SOLIDs use for triangles.
    deduped: list[Point] = []
    for corner in corners:
        if not deduped or corner != deduped[-1]:
            deduped.append(corner)
    return deduped


def _exact_bbox(entity: Any) -> BBox | None:
    # Computing an INSERT's extents explodes its block into virtual entities;
    # real-world files often reference missing/anonymous block definitions,
    # which raises DXFStructureError. Treat any such failure as "no bbox".
    try:
        extents = ezdxf_bbox.extents([entity], fast=True)
    except Exception:
        return None
    if not extents.has_data:
        return None
    return (
        float(extents.extmin.x),
        float(extents.extmin.y),
        float(extents.extmax.x),
        float(extents.extmax.y),
    )


def _shoelace(points: list[Point]) -> float:
    return abs(
        sum(
            points[i][0] * points[(i + 1) % len(points)][1]
            - points[(i + 1) % len(points)][0] * points[i][1]
            for i in range(len(points))
        )
    ) / 2.0


def _hatch_boundary_points(entity: Any) -> list[Point]:
    """Outer boundary of a hatch as a vertex ring.

    Polyline paths carry vertices; edge paths (lines, arcs, splines — what
    AutoCAD writes for most slab and wall hatches) are flattened through
    ezdxf's path module. With several loops, the largest is the outline.
    """
    try:
        from ezdxf.path import make_path

        full = make_path(entity)
        extent = full.bbox()
        tolerance = max(extent.size.x, extent.size.y, 1e-9) * 0.005
        best: list[Point] = []
        for sub in full.sub_paths():
            ring = [(float(v.x), float(v.y)) for v in sub.flattening(tolerance)]
            if len(ring) >= 3 and _shoelace(ring) > _shoelace(best):
                best = ring
        if best:
            return best
    except Exception:  # noqa: BLE001 — fall back to raw polyline vertices
        pass
    points: list[Point] = []
    for path in entity.paths:
        vertices = getattr(path, "vertices", None)
        if vertices:
            points.extend((float(v[0]), float(v[1])) for v in vertices)
    return points


def normalize_entity(
    entity: Any,
    source_file: str,
    ids: IdGenerator,
) -> tuple[NormalizedEntity | None, list[ParseWarning]]:
    """Map one ezdxf entity into a NormalizedEntity, or None with warnings."""
    dxf_type = entity.dxftype()
    layer = str(entity.dxf.layer)
    handle = str(entity.dxf.handle)
    warnings: list[ParseWarning] = []

    if dxf_type not in SUPPORTED_DXF_TYPES:
        warnings.append(
            ParseWarning(
                warning_type="unsupported_dxf_entity",
                message=f"Skipped unsupported entity type {dxf_type}",
                entity_type=dxf_type,
                handle=handle,
                layer=layer,
                source_file=source_file,
            )
        )
        return None, warnings

    text: str | None = None
    points: list[Point] | None = None
    block_name: str | None = None
    rotation: float | None = None
    properties: dict[str, Any] = {}
    bbox: BBox | None = None
    notes: list[str] = []

    if dxf_type == "LINE":
        entity_type = EntityType.line
        points = [
            (float(entity.dxf.start.x), float(entity.dxf.start.y)),
            (float(entity.dxf.end.x), float(entity.dxf.end.y)),
        ]
        bbox = bbox_from_points(points)
    elif dxf_type == "LWPOLYLINE":
        entity_type = EntityType.polyline
        points = [(float(x), float(y)) for x, y in entity.get_points(format="xy")]
        properties["closed"] = bool(entity.closed)
        # A contour line carries its level as the polyline's elevation.
        elevation = float(getattr(entity.dxf, "elevation", 0.0) or 0.0)
        if elevation:
            properties["elevation"] = round(elevation, 4)
        bbox = bbox_from_points(points) if points else None
    elif dxf_type == "POLYLINE":
        entity_type = EntityType.polyline
        points = [
            (float(v.dxf.location.x), float(v.dxf.location.y)) for v in entity.vertices
        ]
        zs = [float(v.dxf.location.z) for v in entity.vertices if v.dxf.location.z]
        if zs and len(zs) == len(points):
            properties["elevation"] = round(sum(zs) / len(zs), 4)  # 3D polyline: its level
        properties["closed"] = bool(entity.is_closed)
        bbox = bbox_from_points(points) if points else None
    elif dxf_type in ("SPLINE", "ELLIPSE"):
        # Flattened into a polyline: detectors and the viewer treat curves as
        # segment chains, so nothing downstream needs a special case.
        entity_type = EntityType.polyline
        points = _flatten_curve(entity)
        if points:
            closed = bool(getattr(entity, "closed", False))
            properties["closed"] = closed
            properties["derived_from"] = dxf_type
            try:
                zs = [float(cp[2]) for cp in getattr(entity, "control_points", []) if cp[2]]
                if zs:
                    properties["elevation"] = round(sum(zs) / len(zs), 4)
            except (TypeError, IndexError):
                pass
            bbox = bbox_from_points(points)
            notes.append(f"{dxf_type} aplanado en {len(points)} segmentos")
        else:
            bbox = None
    elif dxf_type in ("SOLID", "TRACE", "3DFACE"):
        entity_type = EntityType.polyline
        points = _corner_points(entity)
        if len(points) >= 3:
            properties["closed"] = True
            properties["derived_from"] = dxf_type
            bbox = bbox_from_points(points)
            notes.append(f"{dxf_type} normalizado como polígono relleno")
        else:
            bbox = None
    elif dxf_type == "LEADER":
        entity_type = EntityType.polyline
        try:
            # A LEADER read from the file keeps its vertices as tuples, one from a block as
            # vectors: both index (R127; before, every model-space LEADER was dropped).
            points = [(float(v[0]), float(v[1])) for v in entity.vertices]
        except Exception:
            points = []
        if points:
            properties["closed"] = False
            properties["derived_from"] = dxf_type
            bbox = bbox_from_points(points)
        else:
            bbox = None
    elif dxf_type == "ARC":
        entity_type = EntityType.arc
        properties.update(
            center=(float(entity.dxf.center.x), float(entity.dxf.center.y)),
            radius=float(entity.dxf.radius),
            start_angle=float(entity.dxf.start_angle),
            end_angle=float(entity.dxf.end_angle),
        )
        bbox = _exact_bbox(entity)
    elif dxf_type == "CIRCLE":
        entity_type = EntityType.circle
        cx, cy = float(entity.dxf.center.x), float(entity.dxf.center.y)
        radius = float(entity.dxf.radius)
        properties.update(center=(cx, cy), radius=radius)
        bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
    elif dxf_type == "HATCH":
        entity_type = EntityType.hatch
        properties["pattern_name"] = str(entity.dxf.pattern_name)
        boundary = _hatch_boundary_points(entity)
        if boundary:
            points = boundary
            properties["closed"] = True
            bbox = bbox_from_points(boundary)
        else:
            bbox = _exact_bbox(entity)
            notes.append("Hatch boundary not extracted; bbox from ezdxf extents")
    elif dxf_type == "TEXT":
        entity_type = EntityType.text
        text = str(entity.dxf.text)
        rotation = float(entity.dxf.rotation)
        height = float(entity.dxf.height)
        insert = (float(entity.dxf.insert.x), float(entity.dxf.insert.y))
        # A text with another alignment than left-baseline is placed by its
        # alignment point (group 11), not by ``insert``; keep both: the bbox is
        # where the text really lies (R146, ``text_extent``).
        align_point: tuple[float, float] | None = None
        if entity.dxf.hasattr("align_point"):
            align_point = (float(entity.dxf.align_point.x), float(entity.dxf.align_point.y))
        properties.update(
            height=height,
            insert=insert,
            halign=int(entity.dxf.get("halign", 0)),
            valign=int(entity.dxf.get("valign", 0)),
            align_point=align_point,
        )
        # What else changes where the glyphs go: the width factor, the slant and the mirror.
        width_factor = float(entity.dxf.get("width", 1.0) or 1.0)
        if abs(width_factor - 1.0) > 1e-9:
            properties["width_factor"] = width_factor
        oblique = float(entity.dxf.get("oblique", 0.0) or 0.0)
        if oblique:
            properties["oblique"] = oblique
        generation = int(entity.dxf.get("text_generation_flag", 0) or 0)
        if generation & 2:
            properties["mirror_x"] = True
        if generation & 4:
            properties["mirror_y"] = True
        notes.append(_TEXT_EXTENT_NOTE)
    elif dxf_type == "MTEXT":
        entity_type = EntityType.mtext
        text = str(entity.plain_text())
        # Its rotation may be stored as a direction vector (group 11), not as group 50: a MTEXT
        # in a turned block always is (R146).
        rotation = float(entity.get_rotation())
        height = float(entity.dxf.char_height)
        insert = (float(entity.dxf.insert.x), float(entity.dxf.insert.y))
        properties.update(
            height=height,
            insert=insert,
            attachment_point=int(entity.dxf.get("attachment_point", 1)),
        )
        # Where the text really sits: paragraphs centred in a wide column are drawn far
        # from the insert point, so keep the column width and the paragraph alignment.
        column_width = float(entity.dxf.get("width", 0.0) or 0.0)
        if column_width > 0:
            properties["column_width"] = column_width
        paragraph = _MTEXT_PARAGRAPH_ALIGN.search(str(entity.text))
        if paragraph is not None:
            properties["paragraph_align"] = paragraph.group(1).lower()
        line_spacing = float(entity.dxf.get("line_spacing_factor", 1.0) or 1.0)
        if abs(line_spacing - 1.0) > 1e-9:
            properties["line_spacing"] = line_spacing
        notes.append(_TEXT_EXTENT_NOTE)
    elif dxf_type == "DIMENSION":
        entity_type = EntityType.dimension
        try:
            measurement = float(entity.get_measurement())
        except Exception:
            measurement = None
        properties["measurement"] = measurement
        # What the engineer reads: the override text, else the rendered text
        # of the dimension block; with the style's linear factor (details are
        # often drawn at another scale and display the real value).
        display_text = _dimension_display_text(entity)
        if display_text is not None:
            properties["display_text"] = display_text
            value = _parse_display_value(display_text)
            if value is not None:
                properties["display_value"] = value
        try:
            style = entity.doc.dimstyles.get(entity.dxf.get("dimstyle", "Standard"))
            properties["dimlfac"] = float(style.dxf.get("dimlfac", 1.0)) if style else 1.0
        except Exception:
            properties["dimlfac"] = 1.0
        # What it measures along: a linear dimension (type 0) the distance on its angle
        # (0 = x, 90 = y) whatever its points; an aligned one (type 1) between its points.
        try:
            properties["dimtype"] = int(entity.dimtype)
            properties["angle"] = float(entity.dxf.get("angle", 0.0) or 0.0)
        except Exception:
            pass
        # Extension-line origins: the two points the dimension actually measures.
        span: list[Point] | None = None
        if entity.dxf.hasattr("defpoint2") and entity.dxf.hasattr("defpoint3"):
            span = [
                (float(entity.dxf.defpoint2.x), float(entity.dxf.defpoint2.y)),
                (float(entity.dxf.defpoint3.x), float(entity.dxf.defpoint3.y)),
            ]
            properties["measured_segment"] = span
            points = span
        bbox = _exact_bbox(entity)
        if bbox is None and span is not None:
            bbox = bbox_from_points(span)
        elif bbox is None and entity.dxf.hasattr("text_midpoint"):
            mid = (float(entity.dxf.text_midpoint.x), float(entity.dxf.text_midpoint.y))
            bbox = (mid[0], mid[1], mid[0], mid[1])
        if measurement is not None:
            notes.append(f"Dimensión medida del plano = {measurement:.3f} u.dib.")
    else:  # INSERT
        entity_type = EntityType.insert
        block_name = str(entity.dxf.name)
        rotation = float(entity.dxf.rotation)
        insert = (float(entity.dxf.insert.x), float(entity.dxf.insert.y))
        properties["insert"] = insert
        # Attribute values travel with the insert: a nomenclature bubble's
        # tag (V-3), an equipment label, a door number.
        attributes: dict[str, str] = {}
        for attrib in getattr(entity, "attribs", None) or []:
            try:
                attr_text = str(attrib.dxf.text).strip()
            except AttributeError:
                continue
            if attr_text:
                attributes[str(attrib.dxf.tag)] = attr_text
        if attributes:
            properties["attributes"] = attributes
        bbox = _exact_bbox(entity)
        if bbox is None:
            bbox = (insert[0], insert[1], insert[0], insert[1])
            notes.append("Insert bbox approximated as insertion point")

    if entity_type in (EntityType.text, EntityType.mtext):
        # Its real extent, from what the entity says (R146): computed on a provisional record.
        bbox = extension_de_texto(
            NormalizedEntity(
                entity_id="",
                entity_type=entity_type,
                source_file=source_file,
                layer=layer,
                bbox=(0.0, 0.0, 0.0, 0.0),
                raw_handle=handle,
                properties=properties,
                text=text,
                rotation=rotation,
                evidence=EvidencePacket(source=source_file, method="", bbox=None, notes=[]),
            )
        )

    if bbox is None:
        warnings.append(
            ParseWarning(
                warning_type="bbox_unavailable",
                message=f"Could not compute bbox for {dxf_type}; entity skipped",
                entity_type=dxf_type,
                handle=handle,
                layer=layer,
                source_file=source_file,
            )
        )
        return None, warnings

    normalized = NormalizedEntity(
        entity_id=ids.next(),
        entity_type=entity_type,
        source_file=source_file,
        layer=layer,
        bbox=bbox,
        raw_handle=handle,
        properties=properties,
        text=text,
        points=points,
        block_name=block_name,
        rotation=rotation,
        color=int(entity.dxf.color) if entity.dxf.hasattr("color") else None,
        line_type=str(entity.dxf.linetype) if entity.dxf.hasattr("linetype") else None,
        evidence=EvidencePacket(
            source=source_file,
            method=f"ezdxf_{dxf_type.lower()}_extraction",
            bbox=bbox,
            notes=notes,
        ),
    )
    return normalized, warnings


MULTILEADER_TYPES = ("MULTILEADER", "MLEADER")


def normalize_multileader(
    entity: Any,
    source_file: str,
    ids: IdGenerator,
) -> tuple[list[NormalizedEntity], list[ParseWarning]]:
    """A MULTILEADER as what it draws (R127): each leader line as an open polyline from its
    arrow tip through its last point and along its landing (``derived_from: MULTILEADER``),
    and its text, if any, as an MTEXT. Its arrowheads and block content are not kept."""
    layer = str(entity.dxf.layer)
    handle = str(entity.dxf.handle)
    salida: list[NormalizedEntity] = []
    warnings: list[ParseWarning] = []
    try:
        lideres = list(entity.context.leaders)
    except Exception:
        lideres = []
    for lider in lideres:
        final = lider.last_leader_point
        apoyo: list[Point] = []
        if lider.has_dogleg_vector and float(lider.dogleg_length or 0.0) > 0:
            fin = final + lider.dogleg_vector.normalize(float(lider.dogleg_length))
            apoyo = [(float(fin[0]), float(fin[1]))]
        for linea in lider.lines:
            points = [(float(v[0]), float(v[1])) for v in linea.vertices]
            points += [(float(final[0]), float(final[1])), *apoyo]
            if len(points) < 2:
                continue
            bbox = bbox_from_points(points)
            salida.append(
                NormalizedEntity(
                    entity_id=ids.next(),
                    entity_type=EntityType.polyline,
                    source_file=source_file,
                    layer=layer,
                    bbox=bbox,
                    raw_handle=handle,
                    properties={"closed": False, "derived_from": "MULTILEADER"},
                    points=points,
                    color=int(entity.dxf.color) if entity.dxf.hasattr("color") else None,
                    evidence=EvidencePacket(
                        source=source_file,
                        method="ezdxf_multileader_extraction",
                        bbox=bbox,
                        notes=["Línea de una directriz múltiple (MULTILEADER)"],
                    ),
                )
            )
    try:
        textos = [v for v in entity.virtual_entities() if v.dxftype() == "MTEXT"]
    except Exception:
        textos = []
    for mtext in textos:
        if not str(mtext.plain_text()).strip():
            continue
        normalizado, avisos = normalize_entity(mtext, source_file, ids)
        warnings.extend(avisos)
        if normalizado is not None:
            normalizado.raw_handle = handle
            normalizado.properties["derived_from"] = "MULTILEADER"
            salida.append(normalizado)
    if not salida:
        warnings.append(
            ParseWarning(
                warning_type="bbox_unavailable",
                message="MULTILEADER sin líneas ni texto; se omitió",
                entity_type=str(entity.dxftype()),
                handle=handle,
                layer=layer,
                source_file=source_file,
            )
        )
    return salida, warnings
