"""Compact drawing geometry for the web canvas viewer.

Returns lightweight renderable primitives (per layer) plus detection overlays,
so the frontend can draw the plano without shipping the full entity records.
"""

from pathlib import Path

from fastapi import APIRouter, Depends
from klave_engine.common.config import Settings
from klave_engine.costing.reviews import load_reviews

from apps.api.dependencies import ProjectStore, get_settings, get_store

router = APIRouter(prefix="/projects")


def _sheet_index(store: ProjectStore, project_id: str) -> tuple[list[dict], dict[str, int]]:
    """Sheets in manifest order plus a parsed-file-basename → index lookup.

    Entities carry the parsed file's relative path and detection evidence
    carries its basename, so the basename is the join key for both.
    """
    try:
        manifest = store.get_manifest(project_id)
    except Exception:
        return [], {}
    converted_by_source = {c.source_file_id: c.path for c in manifest.converted_files}
    sheets: list[dict] = []
    index: dict[str, int] = {}
    for source in manifest.source_files:
        parsed = (
            converted_by_source.get(source.file_id, source.path)
            if source.file_type.value == "dwg"
            else source.path
        )
        index[Path(parsed).name] = len(sheets)
        sheets.append(
            {
                "name": Path(source.path).name,
                "sheet_number": source.sheet_number,
                "count": 0,
            }
        )
    return sheets, index


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
    settings: Settings = Depends(get_settings),
) -> dict:
    entities = store.read_artifact(project_id, "normalized_entities.json")
    detections = store.read_artifact(project_id, "detections.json")
    reviews = load_reviews(store.get_root(project_id) / settings.processed_dir_name)
    sheets, sheet_index = _sheet_index(store, project_id)

    shapes: list[dict] = []
    layer_counts: dict[str, int] = {}
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for entity in entities:
        layer_counts[entity["layer"]] = layer_counts.get(entity["layer"], 0) + 1
        bbox = entity["bbox"]
        minx, miny = min(minx, bbox[0]), min(miny, bbox[1])
        maxx, maxy = max(maxx, bbox[2]), max(maxy, bbox[3])
        sheet = sheet_index.get(Path(entity.get("source_file", "")).name)
        if sheet is not None:
            sheets[sheet]["count"] += 1
        shape = _renderable(entity)
        if shape is not None:
            if sheet is not None:
                shape["sheet"] = sheet
            shapes.append(shape)

    overlay = []
    for d in detections:
        key = d.get("display_label") or d["detection_id"]
        review = reviews.detections.get(key)
        detection_sheet = sheet_index.get(
            Path(d.get("evidence", {}).get("source", "")).name
        )
        overlay.append(
            {
                "sheet": detection_sheet,
                "id": d["detection_id"],
                "type": d["detection_type"],
                "label": d["label"],
                "confidence": d["confidence"],
                "bbox": d["bbox"],
                # Taxonomy (empty for runs older than the enrichment step).
                "mark": d.get("mark", ""),
                "family": d.get("family", ""),
                "family_label": d.get("family_label", ""),
                "display_label": d.get("display_label", ""),
                "description": d.get("description", ""),
                # Correction loop: key the client uses for review calls, plus
                # the current human verdict for this element.
                "review_key": key,
                "review": review.status if review else "",
                "review_note": review.note if review else "",
            }
        )
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
        "sheets": sheets,
    }
