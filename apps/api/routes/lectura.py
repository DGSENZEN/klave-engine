"""Lectura del plano: one legible answer to "what did Klave read?".

Aggregates the inspection artifacts (conversion, parse summary, layers,
blocks, units, warnings, detections) into a single Spanish-language payload
the web can render without knowing artifact file names. Every section is
optional so partially processed or older runs still return what exists —
failure stays useful.
"""

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request
from klave_engine.common.config import Settings
from klave_engine.costing.instalaciones import sugerir_mapeos

from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.tenancy import store_for_project

router = APIRouter(prefix="/projects")

UNITS_SOURCE_LABELS = {
    "dxf_header": "declaradas en el encabezado del archivo ($INSUNITS)",
    "text_height_heuristic": "inferidas por la altura típica de los textos",
    "dimensions": "deducidas de las cotas del plano (valor mostrado ÷ longitud medida)",
    "heuristics": "inferidas por extensión del modelo y alturas de texto",
    "unknown": "no se pudieron determinar; se asume la unidad del dibujo",
    "confirmed": "confirmadas por el ingeniero en la verificación",
}

WARNING_TYPE_LABELS = {
    "unsupported_dxf_entity": "Entidades no soportadas omitidas",
    "bbox_unavailable": "Entidades sin extensión calculable omitidas",
    "dxf_recovered": "Archivo leído en modo de recuperación",
    "block_explosion_capped": "Expansión de bloques limitada",
    "block_explosion_failed": "Bloques que no se pudieron expandir",
    "xref_missing": "Referencias externas faltantes",
    "xref_embedded": "Referencias externas incorporadas",
    "xref_failed": "Referencias externas que no se pudieron incorporar",
    "non_graphical_in_entities": "Objetos sin geometría entre las entidades (omitidos)",
    "entity_unreadable": "Entidades ilegibles omitidas",
}

ENTITY_TYPE_LABELS = {
    "line": "Líneas",
    "polyline": "Polilíneas",
    "arc": "Arcos",
    "circle": "Círculos",
    "hatch": "Achurados",
    "text": "Textos",
    "mtext": "Textos multilínea",
    "insert": "Bloques (inserciones)",
    "dimension": "Cotas",
}


def _optional(store: ProjectStore, project_id: str, name: str):
    try:
        return store.read_artifact(project_id, name)
    except HTTPException:
        return None


def _frames_summary(store: ProjectStore, project_id: str) -> dict:
    """How many sheet frames the drawing tiles in model space, and how many
    are plantas: the 'Hojas' a person counts, distinct from the files."""
    try:
        frames = store.read_artifact(project_id, "frames.json")
    except HTTPException:
        return {"total": 0, "plan": 0}
    return {
        "total": len(frames),
        "plan": sum(1 for f in frames if f.get("kind") == "plan"),
    }


def _mapeos_sugeridos(
    inventory: dict | None, settings: Settings, project_id: str
) -> list[dict]:
    """Capas y bloques de instalaciones que la biblioteca reconoce.

    Son propuestas: traen la cantidad que producirían y la razón por la que
    se proponen, y nadie las aplica hasta que alguien las confirma. Una capa
    ya asignada no vuelve a proponerse — la asignación del taller manda."""
    if not inventory:
        return []
    try:
        catalog = store_for_project(settings, project_id)
        existentes = catalog.list_inventory_mappings()
        codigos = {row["code"] for row in catalog.load_concepts()}
    except Exception:  # noqa: BLE001 — sin catálogo, se propone sin filtrar
        existentes, codigos = [], None
    return [
        {
            "kind": s.kind,
            "pattern": s.patron,
            "concept_code": s.concepto,
            "unit": s.unidad,
            "quantity": s.cantidad,
            "reason": s.razon,
            "discipline": s.disciplina,
            "sheets": s.hojas,
        }
        for s in sugerir_mapeos(inventory, existentes, codigos)
    ]


@router.get("/{project_id}/lectura")
def get_lectura(
    project_id: str,
    request: Request,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    manifest = store.get_manifest(project_id)
    parse_summary = _optional(store, project_id, "parse_summary.json") or []
    conversions = _optional(store, project_id, "conversion_results.json") or []
    units = _optional(store, project_id, "drawing_units.json")
    layers = _optional(store, project_id, "layer_summary.json") or []
    blocks = _optional(store, project_id, "block_summary.json") or []
    warnings = _optional(store, project_id, "parse_warnings.json") or []
    detections = _optional(store, project_id, "detections.json") or []
    schedules = _optional(store, project_id, "schedules.json") or {}
    inventory = _optional(store, project_id, "inventory.json")
    prefabs = _optional(store, project_id, "prefab_index.json") or []

    conversion_by_source = {c.get("source_path", ""): c for c in conversions}
    summary_by_file = {s.get("source_file", ""): s for s in parse_summary}
    converted_paths = {c.source_file_id: c.path for c in manifest.converted_files}

    sheets = []
    for source in manifest.source_files:
        parsed_path = (
            converted_paths.get(source.file_id, source.path)
            if source.file_type.value == "dwg"
            else source.path
        )
        conversion = None
        if source.file_type.value == "dwg":
            record = next(
                (c for key, c in conversion_by_source.items() if source.path in key),
                None,
            )
            conversion = (
                {
                    "status": record.get("status"),
                    "message": record.get("error_message") or "Conversión exitosa.",
                    "duration_seconds": record.get("duration_seconds"),
                }
                if record
                else {"status": "unknown", "message": "Sin registro de conversión."}
            )
        sheets.append(
            {
                "name": source.path.split("/")[-1],
                "sheet_number": source.sheet_number,
                "discipline": source.discipline,
                "file_type": source.file_type.value,
                "conversion": conversion,
                "parse": summary_by_file.get(parsed_path),
            }
        )

    warning_groups: dict[str, dict] = {}
    for warning in warnings:
        wtype = warning.get("warning_type", "otro")
        group = warning_groups.setdefault(
            wtype,
            {
                "type": wtype,
                "label": WARNING_TYPE_LABELS.get(wtype, wtype),
                "count": 0,
                "samples": [],
            },
        )
        group["count"] += 1
        if len(group["samples"]) < 3:
            group["samples"].append(warning.get("message", ""))

    family_counts = Counter(
        (d.get("family") or d.get("detection_type") or "otro") for d in detections
    )

    return {
        "project_id": project_id,
        "inventory": inventory,
        "mapeos_sugeridos": _mapeos_sugeridos(inventory, settings, project_id),
        "project_name": manifest.project_name,
        "frames": _frames_summary(store, project_id),
        "sheets": sheets,
        "units": (
            {
                **units,
                "source_label": UNITS_SOURCE_LABELS.get(
                    units.get("source", ""), units.get("source", "")
                ),
            }
            if units
            else None
        ),
        "layers": layers[:20],
        "layer_total": len(layers),
        "blocks": blocks[:12],
        # El índice de prefabricados, resumido: qué definiciones trae el
        # plano, cuántas veces se colocan, y qué reconoce la tabla.
        "prefabs": [
            {
                "name": p.get("name"),
                "familia": p.get("familia"),
                "que_es": p.get("que_es"),
                "disciplina": p.get("disciplina"),
                "clase": p.get("clase"),
                "es_anotacion": p.get("es_anotacion", False),
                "attdefs": p.get("attdefs", []),
                "instance_count": len(p.get("instances", [])),
            }
            for p in prefabs
        ],
        "warning_groups": sorted(
            warning_groups.values(), key=lambda g: -g["count"]
        ),
        "schedules": {
            "by_mark": [
                {"mark": mark, **spec} for mark, spec in sorted(
                    (schedules.get("by_mark") or {}).items()
                )
            ],
            "by_family": [
                {"family": family, **spec} for family, spec in sorted(
                    (schedules.get("by_family") or {}).items()
                )
            ],
            "tables_found": schedules.get("tables_found", 0),
            "concrete_fc": schedules.get("concrete_fc", {}),
            "notes": schedules.get("notes", []),
        },
        "detection_total": len(detections),
        "detections_by_family": dict(family_counts.most_common()),
        "entity_type_labels": ENTITY_TYPE_LABELS,
    }
