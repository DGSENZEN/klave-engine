"""Spatial index over normalized entity bboxes using Shapely STRtree.

Public query methods return project-level SpatialHit results, never raw
library objects.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from shapely.geometry import Point as ShapelyPoint
from shapely.strtree import STRtree

from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.geometry.bbox import BBox, Point, bbox_union_all
from klave_engine.geometry.primitives import bbox_to_polygon


@dataclass(frozen=True)
class SpatialHit:
    entity_id: str
    distance: float
    relationship: str  # "intersects" | "near" | "nearest"


class SpatialIndex:
    def __init__(self, entities: Iterable[NormalizedEntity]) -> None:
        self._entities = list(entities)
        self._by_id = {e.entity_id: e for e in self._entities}
        self._geometries = [bbox_to_polygon(e.bbox) for e in self._entities]
        self._tree = STRtree(self._geometries) if self._geometries else None

    def __len__(self) -> int:
        return len(self._entities)

    def get(self, entity_id: str) -> NormalizedEntity:
        return self._by_id[entity_id]

    def extent(self) -> BBox | None:
        if not self._entities:
            return None
        return bbox_union_all(e.bbox for e in self._entities)

    def entities_in_bbox(self, bounds: BBox) -> list[SpatialHit]:
        """Entities whose bbox intersects the given bbox."""
        if self._tree is None:
            return []
        query_geom = bbox_to_polygon(bounds)
        indices = self._tree.query(query_geom, predicate="intersects")
        return [
            SpatialHit(self._entities[i].entity_id, 0.0, "intersects")
            for i in sorted(indices)
        ]

    def entities_near_point(self, point: Point, radius: float) -> list[SpatialHit]:
        """Entities whose bbox is within radius of the point, sorted by distance."""
        if self._tree is None:
            return []
        probe = ShapelyPoint(point).buffer(radius)
        indices = self._tree.query(probe, predicate="intersects")
        hits = []
        for i in indices:
            distance = float(self._geometries[i].distance(ShapelyPoint(point)))
            if distance <= radius:
                relationship = "intersects" if distance == 0.0 else "near"
                hits.append(SpatialHit(self._entities[i].entity_id, distance, relationship))
        return sorted(hits, key=lambda h: h.distance)

    def entities_near_entity(
        self, entity_id: str, radius: float, exclude_self: bool = True
    ) -> list[SpatialHit]:
        entity = self._by_id[entity_id]
        if self._tree is None:
            return []
        probe = bbox_to_polygon(entity.bbox).buffer(radius)
        indices = self._tree.query(probe, predicate="intersects")
        hits = []
        for i in indices:
            other = self._entities[i]
            if exclude_self and other.entity_id == entity_id:
                continue
            distance = float(self._geometries[i].distance(bbox_to_polygon(entity.bbox)))
            if distance <= radius:
                relationship = "intersects" if distance == 0.0 else "near"
                hits.append(SpatialHit(other.entity_id, distance, relationship))
        return sorted(hits, key=lambda h: h.distance)

    def nearest_entity(
        self, point: Point, exclude: set[str] | None = None
    ) -> SpatialHit | None:
        if self._tree is None:
            return None
        exclude = exclude or set()
        probe = ShapelyPoint(point)
        candidates = sorted(
            (
                (float(self._geometries[i].distance(probe)), self._entities[i].entity_id)
                for i in range(len(self._entities))
                if self._entities[i].entity_id not in exclude
            ),
        )
        if not candidates:
            return None
        distance, entity_id = candidates[0]
        return SpatialHit(entity_id, distance, "nearest")

    def summary(self) -> dict:
        from collections import Counter

        type_counts = Counter(e.entity_type.value for e in self._entities)
        return {
            "entity_count": len(self._entities),
            "extent": self.extent(),
            "entity_counts_by_type": dict(sorted(type_counts.items())),
        }
