
"""Normalize ezdxf entities into NormalizedEntity records.

Every supported entity gets a bbox. Where an exact bbox is impractical (text),
a conservative approximation is used and noted in the evidence packet.
"""

import re
from typing import Any

from ezdxf import bbox as ezdxf_bbox

from klave_engine.common.ids import IdGenerator
from klave_engine.dxf.entities import EntityType, NormalizedEntity, ParseWarning
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

# Approximate average glyph width as a fraction of text height.
TEXT_WIDTH_FACTOR = 0.6

# Curves flatten into at most this many segments; enough for detection and
# rendering without letting one dense spline dominate the entity budget.
MAX_FLATTEN_POINTS = 200


_DISPLAY_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


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


def _approximate_text_bbox(insert: Point, text: str, height: float) -> BBox:
    width = max(height * TEXT_WIDTH_FACTOR * max(len(text), 1), height)
    return (insert[0], insert[1], insert[0] + width, insert[1] + height)


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
            points = [(float(v.x), float(v.y)) for v in entity.vertices]
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
        properties.update(height=height, insert=insert)
        bbox = _approximate_text_bbox(insert, text, height)
        notes.append("Text bbox approximated from insert point and height")
    elif dxf_type == "MTEXT":
        entity_type = EntityType.mtext
        text = str(entity.plain_text())
        rotation = float(entity.dxf.rotation)
        height = float(entity.dxf.char_height)
        insert = (float(entity.dxf.insert.x), float(entity.dxf.insert.y))
        properties.update(height=height, insert=insert)
        bbox = _approximate_text_bbox(insert, text, height)
        notes.append("MText bbox approximated from insert point and char height")
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
