"""Compact drawing geometry for the web canvas viewer.

Returns lightweight renderable primitives (per layer) plus detection overlays,
so the frontend can draw the plano without shipping the full entity records.
"""

from fastapi import APIRouter, Depends

from apps.api.dependencies import ProjectStore, get_store

router = APIRouter(prefix="/projects")


def _renderable(entity: dict) -> dict | None:
    etype = entity["entity_type"]
    bbox = entity["bbox"]
    if etype in ("line", "polyline") and entity.get("points"):
        return {
            "t": "path",
            "layer": entity["layer"],
            "pts": entity["points"],
            "closed": bool(entity.get("properties", {}).get("closed")),
        }
    if etype == "circle":
        props = entity.get("properties", {})
        center = props.get("center")
        radius = props.get("radius")
        if center and radius:
            return {"t": "circle", "layer": entity["layer"], "c": center, "r": radius}
    if etype == "arc":
        return {"t": "box", "layer": entity["layer"], "bbox": bbox}
    return None


@router.get("/{project_id}/geometry")
def get_geometry(
    project_id: str,
    store: ProjectStore = Depends(get_store),
) -> dict:
    entities = store.read_artifact(project_id, "normalized_entities.json")
    detections = store.read_artifact(project_id, "detections.json")

    shapes: list[dict] = []
    layer_counts: dict[str, int] = {}
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for entity in entities:
        layer_counts[entity["layer"]] = layer_counts.get(entity["layer"], 0) + 1
        bbox = entity["bbox"]
        minx, miny = min(minx, bbox[0]), min(miny, bbox[1])
        maxx, maxy = max(maxx, bbox[2]), max(maxy, bbox[3])
        shape = _renderable(entity)
        if shape is not None:
            shapes.append(shape)

    overlay = [
        {
            "id": d["detection_id"],
            "type": d["detection_type"],
            "label": d["label"],
            "confidence": d["confidence"],
            "bbox": d["bbox"],
        }
        for d in detections
    ]
    extent = (
        [minx, miny, maxx, maxy]
        if shapes or entities
        else [0.0, 0.0, 1.0, 1.0]
    )
    layers = [
        {"name": name, "count": count}
        for name, count in sorted(layer_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "extent": extent,
        "layers": layers,
        "shapes": shapes,
        "detections": overlay,
    }
