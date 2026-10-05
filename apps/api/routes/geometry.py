"""Compact drawing geometry for the web canvas viewer.

Returns lightweight renderable primitives (per layer) plus detection overlays,
so the frontend can draw the plano without shipping the full entity records.
"""

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from klave_engine.common.config import Settings
from klave_engine.costing.reviews import load_reviews
from klave_engine.dxf.units import DrawingUnits

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
    """What the engineer sees on the sheet: linework, arcs, hatches, texts and
    cotas. Each shape keeps its layer so the visor can toggle it."""
    etype = entity["entity_type"]
    bbox = entity["bbox"]
    props = entity.get("properties") or {}
    layer = entity["layer"]
    if etype in ("line", "polyline") and entity.get("points"):
        return {"t": "path", "layer": layer, "pts": entity["points"],
                "closed": bool(props.get("closed"))}
    if etype == "hatch":
        if entity.get("points") and len(entity["points"]) >= 3:
            return {"t": "hatch", "layer": layer, "pts": entity["points"]}
        return {"t": "box", "layer": layer, "bbox": bbox}
    if etype == "circle":
        center, radius = props.get("center"), props.get("radius")
        if center and radius:
            return {"t": "circle", "layer": layer, "c": center, "r": radius}
    if etype == "arc":
        center, radius = props.get("center"), props.get("radius")
        if center and radius:
            return {"t": "arc", "layer": layer, "c": center, "r": radius,
                    "a0": props.get("start_angle", 0.0), "a1": props.get("end_angle", 360.0)}
        return {"t": "box", "layer": layer, "bbox": bbox}
    if etype in ("text", "mtext") and entity.get("text"):
        insert = props.get("insert") or [bbox[0], bbox[1]]
        height = props.get("height") or max(bbox[3] - bbox[1], 1e-6)
        return {"t": "text", "layer": layer, "p": insert, "h": height,
                "rot": entity.get("rotation") or 0.0,
                "s": " ".join(str(entity["text"]).split())[:200],
                "multi": etype == "mtext"}
    if etype == "dimension":
        segment = props.get("measured_segment")
        label = props.get("display_text") or (
            f"{props['measurement']:.2f}" if props.get("measurement") else ""
        )
        if segment and len(segment) == 2:
            return {"t": "dim", "layer": layer, "pts": segment, "label": label}
        return {"t": "dim", "layer": layer,
                "pts": [[bbox[0], (bbox[1] + bbox[3]) / 2], [bbox[2], (bbox[1] + bbox[3]) / 2]],
                "label": label}
    return None



# Medidas legibles por elemento para el visor: solo lo que tiene unidad
# honesta — metros nativos siempre; unidades de dibujo solo cuando el factor
# a metros es confiable. Nada se inventa: sin factor, el dato no aparece.
_MEDIDAS_M = [("length_m", "Longitud"), ("vertical_length_m", "Bajada (vertical)")]
_MEDIDAS_DU = [
    ("length", "Longitud"),
    ("estimated_length", "Longitud estimada"),
    ("estimated_span_length", "Claro estimado"),
    ("opening_length", "Ancho de vano"),
    ("estimated_thickness", "Espesor estimado"),
]
_MEDIDAS_DU2 = [
    ("estimated_area", "Área estimada"),
    ("section_area_du2", "Área de sección"),
    ("void_area", "Área de vanos"),
]


def _medidas(props: dict, to_meters: float | None) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()

    def _num(key: str) -> float | None:
        value = props.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value) if value > 0 else None

    for key, label in _MEDIDAS_M:
        value = _num(key)
        if value is not None and label not in seen:
            out.append({"label": label, "value": f"{value:,.2f} m"})
            seen.add(label)
    if to_meters:
        for key, label in _MEDIDAS_DU:
            value = _num(key)
            if value is not None and label not in seen:
                out.append({"label": label, "value": f"{value * to_meters:,.2f} m"})
                seen.add(label)
        for key, label in _MEDIDAS_DU2:
            value = _num(key)
            if value is not None and label not in seen:
                out.append({"label": label, "value": f"{value * to_meters**2:,.2f} m²"})
                seen.add(label)
    return out[:4]


# El dibujo de una corrida no cambia: se arma una vez y se guarda en memoria
# (las últimas corridas abiertas). Marina: 76 mil figuras, 18 MB de JSON y
# ~0.8 s por visita antes de esto; sólo las detecciones con su veredicto se
# rehacen en cada petición.
_STATIC_CACHE: dict[tuple, dict] = {}
_STATIC_CACHE_MAX = 3  # ~60 MB por plano grande (Marina) en memoria
# Cuatro decimales: una décima de milímetro en un plano en metros. Las
# coordenadas venían con quince y eran la mitad del peso de la respuesta.
_DECIMALS = 4


def _r(value: float) -> float:
    return round(float(value), _DECIMALS)


def _round_shape(shape: dict) -> dict:
    if "pts" in shape:
        shape["pts"] = [[_r(x), _r(y)] for x, y, *_rest in shape["pts"]]
    for key in ("c", "p"):
        if key in shape and shape[key]:
            shape[key] = [_r(v) for v in shape[key][:2]]
    if "bbox" in shape and shape["bbox"]:
        shape["bbox"] = [_r(v) for v in shape["bbox"]]
    if "r" in shape:
        shape["r"] = _r(shape["r"])
    if "h" in shape:
        shape["h"] = _r(shape["h"])
    return shape


def _cache_key(store: ProjectStore, project_id: str) -> tuple:
    path = store.artifact_root(project_id) / "normalized_entities.json"
    try:
        stat = path.stat()
    except OSError:
        return (str(path), 0, 0)
    return (str(path), stat.st_mtime_ns, stat.st_size)


def static_geometry(store: ProjectStore, project_id: str, settings: Settings) -> dict:
    """Lo que no cambia en una corrida: extensión, marcos, capas, figuras,
    hojas y unidades. ``_etag`` identifica la corrida para el navegador."""
    key = _cache_key(store, project_id)
    cached = _STATIC_CACHE.get(key)
    if cached is not None:
        return cached
    entities = store.read_artifact(project_id, "normalized_entities.json")
    try:
        frames = store.read_artifact(project_id, "frames.json")
    except HTTPException:
        frames = []
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
            shapes.append(_round_shape(shape))
    try:
        units_read = DrawingUnits.model_validate(
            store.read_artifact(project_id, "drawing_units.json")
        )
        units_payload = {"unit": units_read.unit, "to_meters": units_read.to_meters()}
    except (HTTPException, ValueError):
        units_payload = None
    to_meters = units_payload["to_meters"] if units_payload else None

    extent = (
        [minx, miny, maxx, maxy]
        if shapes or entities
        else [0.0, 0.0, 1.0, 1.0]
    )
    layers = [
        {"name": name, "count": count}
        for name, count in sorted(layer_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    payload = {
        "extent": extent,
        # Sheet frames (plantas, detalles) so the visor can jump to a sheet.
        "frames": [
            {
                "code": f.get("code", ""), "title": f.get("title", ""), "kind": f.get("kind", ""),
                "bbox": f.get("bbox"), "source_file": f.get("source_file", ""),
            }
            for f in (frames or []) if f.get("bbox")
        ],
        "layers": layers,
        "shapes": shapes,
        "sheets": sheets,
        "units": units_payload,
        "_etag": hashlib.sha1(repr(key).encode()).hexdigest()[:16],
        "_to_meters": to_meters,
    }
    if len(_STATIC_CACHE) >= _STATIC_CACHE_MAX:
        _STATIC_CACHE.pop(next(iter(_STATIC_CACHE)))
    _STATIC_CACHE[key] = payload
    return payload


def detection_overlay(
    store: ProjectStore, project_id: str, settings: Settings, to_meters: float | None
) -> list[dict]:
    """Las detecciones con el veredicto vigente de cada una: lo que sí cambia."""
    detections = store.read_artifact(project_id, "detections.json")
    reviews = load_reviews(store.get_root(project_id) / settings.processed_dir_name)
    _sheets, sheet_index = _sheet_index(store, project_id)
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
                # Tableros carry their real outline (L-shapes, voids subtracted).
                "polygon": (d.get("properties") or {}).get("polygon"),
                # Taxonomy (empty for runs older than the enrichment step).
                "mark": d.get("mark", ""),
                "family": d.get("family", ""),
                "family_label": d.get("family_label", ""),
                # Labels that ARE a cuadro (not elements on the planta) get
                # their own family in the visor, hidden by default.
                "role": (d.get("properties") or {}).get("role") or "",
                "display_label": d.get("display_label", ""),
                "description": d.get("description", ""),
                # Correction loop: key the client uses for review calls, plus
                # the current human verdict for this element.
                "review_key": key,
                "review": review.status if review else "",
                "review_note": review.note if review else "",
                "medidas": _medidas(d.get("properties") or {}, to_meters),
            }
        )
    return overlay


def _public(static: dict, sheet: int | None = None) -> dict:
    out = {k: v for k, v in static.items() if not k.startswith("_")}
    if sheet is not None:
        # El visor dibuja una hoja a la vez: sólo baja la que va a dibujar.
        out["shapes"] = [s for s in static["shapes"] if s.get("sheet") == sheet]
    return out


def _of_sheet(overlay: list[dict], sheet: int | None) -> list[dict]:
    return overlay if sheet is None else [d for d in overlay if d.get("sheet") == sheet]


@router.get("/{project_id}/geometry")
def get_geometry(
    project_id: str,
    sheet: int | None = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    static = static_geometry(store, project_id, settings)
    return {
        **_public(static, sheet),
        "detections": _of_sheet(
            detection_overlay(store, project_id, settings, static["_to_meters"]), sheet
        ),
    }


@router.get("/{project_id}/geometry/shapes")
def get_geometry_shapes(
    project_id: str,
    request: Request,
    sheet: int | None = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    """El dibujo de la corrida, con ETag: si no cambió, el navegador no lo
    vuelve a bajar."""
    static = static_geometry(store, project_id, settings)
    etag = f'"{static["_etag"]}-{sheet if sheet is not None else "all"}"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(_public(static, sheet), headers=headers)


@router.get("/{project_id}/geometry/detections")
def get_geometry_detections(
    project_id: str,
    sheet: int | None = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Sólo las detecciones y sus veredictos: lo que una revisión mueve."""
    static = static_geometry(store, project_id, settings)
    overlay = detection_overlay(store, project_id, settings, static["_to_meters"])
    return {"detections": _of_sheet(overlay, sheet)}
