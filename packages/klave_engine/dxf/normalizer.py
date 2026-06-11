"""Normalize ezdxf entities into NormalizedEntity records.

Every supported entity gets a bbox. Where an exact bbox is impractical (text),
a conservative approximation is used and noted in the evidence packet.
"""

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
    "HATCH",
    "TEXT",
    "MTEXT",
    "INSERT",
}

# Approximate average glyph width as a fraction of text height.
TEXT_WIDTH_FACTOR = 0.6


def _exact_bbox(entity: Any) -> BBox | None:
    extents = ezdxf_bbox.extents([entity], fast=True)
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


def _hatch_boundary_points(entity: Any) -> list[Point]:
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
        bbox = bbox_from_points(points) if points else None
    elif dxf_type == "POLYLINE":
        entity_type = EntityType.polyline
        points = [
            (float(v.dxf.location.x), float(v.dxf.location.y)) for v in entity.vertices
        ]
        properties["closed"] = bool(entity.is_closed)
        bbox = bbox_from_points(points) if points else None
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
    else:  # INSERT
        entity_type = EntityType.insert
        block_name = str(entity.dxf.name)
        rotation = float(entity.dxf.rotation)
        insert = (float(entity.dxf.insert.x), float(entity.dxf.insert.y))
        properties["insert"] = insert
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
