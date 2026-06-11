"""Spatial index query tests against the demo fixture."""

from klave_engine.geometry.spatial_index import SpatialIndex


def test_index_summary(demo_index: SpatialIndex) -> None:
    summary = demo_index.summary()
    assert summary["entity_count"] == len(demo_index)
    assert summary["extent"] is not None


def test_entities_in_bbox_finds_column_area(demo_index: SpatialIndex, demo_entities) -> None:
    hits = demo_index.entities_in_bbox((150.0, 550.0, 250.0, 650.0))
    found_ids = {h.entity_id for h in hits}
    c1_text = next(e for e in demo_entities if e.text == "C1" and e.bbox[0] == 210.0)
    circle = next(
        e
        for e in demo_entities
        if e.entity_type.value == "circle" and e.properties["center"] == (200.0, 600.0)
    )
    assert c1_text.entity_id in found_ids
    assert circle.entity_id in found_ids


def test_entities_near_point_sorted_by_distance(demo_index: SpatialIndex) -> None:
    hits = demo_index.entities_near_point((200.0, 600.0), radius=30.0)
    assert hits
    distances = [h.distance for h in hits]
    assert distances == sorted(distances)
    assert all(h.relationship in ("intersects", "near") for h in hits)


def test_nearest_entity(demo_index: SpatialIndex, demo_entities) -> None:
    hit = demo_index.nearest_entity((690.0, 406.0))
    assert hit is not None
    nearest = demo_index.get(hit.entity_id)
    # The beam tag text or beam line is closest to this probe point.
    assert nearest.layer == "S-BEAM"


def test_empty_index() -> None:
    index = SpatialIndex([])
    assert index.extent() is None
    assert index.entities_in_bbox((0, 0, 1, 1)) == []
    assert index.nearest_entity((0, 0)) is None
