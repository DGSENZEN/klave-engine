"""Conversions from normalized entities to Shapely geometries."""

from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry

from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import BBox, bbox_center


def bbox_to_polygon(bounds: BBox) -> Polygon:
    return box(*bounds)


def entity_to_shapely(entity: NormalizedEntity) -> BaseGeometry:
    """Best-effort Shapely geometry for an entity; falls back to its bbox."""
    if entity.entity_type == EntityType.circle:
        center = entity.properties.get("center")
        radius = entity.properties.get("radius")
        if center and radius:
            return Point(center).buffer(float(radius), quad_segs=16)
    if entity.points and len(entity.points) >= 2:
        if entity.is_closed and len(entity.points) >= 3:
            polygon = Polygon(entity.points)
            if polygon.is_valid:
                return polygon
        return LineString(entity.points)
    if entity.bbox[0] == entity.bbox[2] and entity.bbox[1] == entity.bbox[3]:
        return Point(bbox_center(entity.bbox))
    return bbox_to_polygon(entity.bbox)
