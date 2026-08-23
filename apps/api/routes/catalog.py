"""Workspace catalog API: insumos, APU matrices, and rendimientos.

Edits here change the workspace baseline used by every future (re)compute;
per-project price overrides in costing_overrides.json still apply on top.
A global ``catalog_updated`` event tells open projects to offer a recompute.
"""

import csv
import hashlib
import io
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from klave_engine.common.config import Settings
from klave_engine.costing.catalog import PHASE_ORDER
from klave_engine.costing.catalog_services import apply_equipment, apply_labor, labor_state
from klave_engine.costing.catalog_store import CatalogStore, get_catalog_store
from klave_engine.costing.equipment import EquipmentParameters, compute_costo_horario
from klave_engine.costing.labor import (
    REGION_PRESETS,
    FsrParameters,
    LaborCategory,
    apply_preset,
    preset_by_key,
)
from klave_engine.costing.sources.custom import (
    CustomCatalogError,
    parse_concept_workbook,
    source_key_for,
)
from klave_engine.costing.sources.matrices import parse_matrices_workbook
from klave_engine.costing.sources.registry import SOURCES, available_sources, sources_dir
from pydantic import BaseModel, Field

from apps.api.dependencies import get_settings
from apps.api.events import BUS, clean_actor

router = APIRouter(prefix="/catalog", tags=["catalog"])

MAX_IMPORT_BYTES = 1_000_000


def get_catalog(settings: Settings = Depends(get_settings)) -> CatalogStore:
    return get_catalog_store(settings.data_dir)


class InsumoUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=200)
    unit: str | None = Field(default=None, min_length=1, max_length=12)
    resource_type: str | None = None
    unit_cost: float | None = Field(default=None, gt=0)
    source: str | None = Field(default=None, max_length=200)
    source_type: Literal["referencia", "cotizacion", "publicacion", "calculado"] | None = None
    region: str | None = Field(default=None, max_length=12)
    vigencia: str | None = Field(default=None, max_length=7)


class ConceptCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    description: str = Field(min_length=3, max_length=200)
    unit: str = Field(min_length=1, max_length=12)
    phase: str = Field(min_length=2, max_length=40)
    production_rate_per_day: float = Field(gt=0)
    components: list["ApuComponentInput"] = Field(min_length=1)


class ConceptUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=3, max_length=200)
    unit: str | None = Field(default=None, min_length=1, max_length=12)
    phase: str | None = Field(default=None, min_length=2, max_length=40)
    production_rate_per_day: float | None = Field(default=None, gt=0)
    active: bool | None = None


class InsumoCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    description: str = Field(min_length=1, max_length=200)
    unit: str = Field(min_length=1, max_length=12)
    resource_type: str
    unit_cost: float = Field(gt=0)
    source: str = Field(default="", max_length=200)


class ApuComponentInput(BaseModel):
    resource_code: str
    quantity: float = Field(gt=0)


class ApuUpdate(BaseModel):
    components: list[ApuComponentInput] = Field(min_length=1)


class RendimientoUpdate(BaseModel):
    production_rate_per_day: float = Field(gt=0)


def _publish_catalog_updated(actor: str | None, action: str, detail: str) -> None:
    BUS.publish(
        "catalog_updated",
        actor=clean_actor(actor),
        data={"action": action, "detail": detail},
    )


@router.get("")
def get_catalog_state(catalog: CatalogStore = Depends(get_catalog)) -> dict:
    templates = catalog.load_templates()
    return {
        "insumos": catalog.list_insumos(),
        "concepts": [
            {
                "code": row["code"],
                "description": row["description"],
                "unit": row["unit"],
                "phase": row["phase"],
                "production_rate_per_day": row["production_rate_per_day"],
                # rule_key marks detection-backed concepts; without one the
                # concept is manual and quantities come from adjustments.
                "detection_backed": bool(row.get("rule_key")),
                # A P.U. adopted from a reference row replaces the matrix.
                "price_override": row.get("price_override"),
                "price_source": row.get("price_source"),
                "price_clave": row.get("price_clave"),
                "price_vigencia": row.get("price_vigencia"),
            }
            for row in catalog.load_concepts()
        ],
        "apus": {
            code: [
                {"resource_code": resource_code, "quantity": quantity}
                for resource_code, quantity in components
            ]
            for code, components in templates.items()
        },
        "phase_order": PHASE_ORDER,
    }


@router.post("/insumos", status_code=201)
def create_insumo(
    body: InsumoCreate,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    if body.code in catalog.load_price_book():
        raise HTTPException(
            status_code=409,
            detail={"error_type": "insumo_exists", "code": body.code},
        )
    try:
        row = catalog.upsert_insumo(
            body.code,
            description=body.description,
            unit=body.unit,
            resource_type=body.resource_type,
            unit_cost=body.unit_cost,
            source=body.source,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"error_type": "invalid_insumo", "message": str(exc)}
        ) from exc
    _publish_catalog_updated(x_actor, "insumo_created", body.code)
    return row


@router.put("/insumos/{code}")
def update_insumo(
    code: str,
    body: InsumoUpdate,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    if code not in catalog.load_price_book():
        raise HTTPException(
            status_code=404, detail={"error_type": "insumo_not_found", "code": code}
        )
    try:
        row = catalog.upsert_insumo(
            code,
            description=body.description,
            unit=body.unit,
            resource_type=body.resource_type,
            unit_cost=body.unit_cost,
            source=body.source,
            source_type=body.source_type,
            region=body.region,
            vigencia=body.vigencia,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"error_type": "invalid_insumo", "message": str(exc)}
        ) from exc
    _publish_catalog_updated(x_actor, "insumo_updated", code)
    return row


@router.put("/apus/{concept_code}")
def update_apu(
    concept_code: str,
    body: ApuUpdate,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    known = {row["code"] for row in catalog.load_concepts(include_inactive=True)}
    if concept_code not in known:
        raise HTTPException(
            status_code=404,
            detail={"error_type": "concept_not_found", "code": concept_code},
        )
    try:
        catalog.set_apu_components(
            concept_code,
            [(component.resource_code, component.quantity) for component in body.components],
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"error_type": "invalid_apu", "message": str(exc)}
        ) from exc
    _publish_catalog_updated(x_actor, "apu_updated", concept_code)
    return {"concept_code": concept_code, "components": len(body.components)}


@router.put("/rendimientos/{concept_code}")
def update_rendimiento(
    concept_code: str,
    body: RendimientoUpdate,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    known = {row["code"] for row in catalog.load_concepts(include_inactive=True)}
    if concept_code not in known:
        raise HTTPException(
            status_code=404,
            detail={"error_type": "concept_not_found", "code": concept_code},
        )
    catalog.set_rendimiento(concept_code, body.production_rate_per_day)
    _publish_catalog_updated(x_actor, "rendimiento_updated", concept_code)
    return {
        "concept_code": concept_code,
        "production_rate_per_day": body.production_rate_per_day,
    }


@router.post("/concepts", status_code=201)
def create_concept(
    body: ConceptCreate,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    try:
        row = catalog.create_concept(
            code=body.code.upper(),
            description=body.description,
            unit=body.unit.upper(),
            phase=body.phase,
            production_rate_per_day=body.production_rate_per_day,
            components=[(c.resource_code, c.quantity) for c in body.components],
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"error_type": "invalid_concept", "message": str(exc)}
        ) from exc
    _publish_catalog_updated(x_actor, "concept_created", body.code.upper())
    return row


@router.put("/concepts/{concept_code}")
def update_concept(
    concept_code: str,
    body: ConceptUpdate,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    try:
        row = catalog.update_concept(
            concept_code,
            description=body.description,
            unit=body.unit,
            phase=body.phase,
            production_rate_per_day=body.production_rate_per_day,
            active=body.active,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404 if "no existe" in str(exc) else 422,
            detail={"error_type": "invalid_concept", "message": str(exc)},
        ) from exc
    _publish_catalog_updated(x_actor, "concept_updated", concept_code)
    return row


@router.post("/import-prices")
async def import_prices(
    file: UploadFile,
    x_actor: Annotated[str | None, Header()] = None,
    source: str = "Importación CSV",
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    """Bulk price update from a UTF-8 CSV with columns code,unit_cost (or
    clave,costo_unitario). Only existing insumo codes are updated."""
    raw = await file.read()
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error_type": "import_too_large", "max_bytes": MAX_IMPORT_BYTES},
        )
    filename = (file.filename or "").lower()
    if filename.endswith((".xlsx", ".xlsm")) or raw[:2] == b"PK":
        rows = _rows_from_xlsx(raw)
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = raw.decode("cp1252")
            except UnicodeDecodeError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error_type": "invalid_encoding",
                        "message": "El archivo debe ser CSV UTF-8/CP1252 o XLSX.",
                    },
                ) from exc
        delimiter = ";" if text.count(";") > text.count(",") else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        rows = [
            {(key or "").strip().lower(): (value or "") for key, value in row.items()}
            for row in reader
        ]
    if not rows:
        raise HTTPException(
            status_code=422,
            detail={
                "error_type": "empty_import",
                "message": "El CSV no contiene filas de datos.",
            },
        )
    result = catalog.import_prices(rows, source=source.strip() or "Importación CSV")
    _publish_catalog_updated(x_actor, "prices_imported", f"{result['updated']} precios")
    return result


# Column aliases across OPUS/Neodata/plain exports: the import maps whichever
# pair of code+price headers the workbook uses.
_CODE_HEADERS = ("code", "clave", "código", "codigo", "key")
_COST_HEADERS = (
    "unit_cost", "costo_unitario", "costo", "precio", "precio unitario",
    "p.u.", "pu", "precio_unitario",
)


def _rows_from_xlsx(raw: bytes) -> list[dict[str, str]]:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={"error_type": "invalid_xlsx", "message": "No se pudo leer el XLSX."},
        ) from exc
    ws = workbook.active
    header_row: list[str] | None = None
    code_index = cost_index = -1
    rows: list[dict[str, str]] = []
    for row in ws.iter_rows(values_only=True):
        values = ["" if v is None else str(v).strip() for v in row]
        if header_row is None:
            lowered = [v.lower() for v in values]
            code_candidates = [i for i, v in enumerate(lowered) if v in _CODE_HEADERS]
            cost_candidates = [i for i, v in enumerate(lowered) if v in _COST_HEADERS]
            if code_candidates and cost_candidates:
                header_row = values
                code_index, cost_index = code_candidates[0], cost_candidates[0]
            continue
        if code_index < len(values) and cost_index < len(values):
            rows.append({"code": values[code_index], "unit_cost": values[cost_index]})
    if header_row is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error_type": "headers_not_found",
                "message": (
                    "No se encontró un encabezado con clave/código y precio; "
                    "exporta desde OPUS/Neodata con esas columnas."
                ),
            },
        )
    return rows


# ------------------------------------------------------------ reference library

class AdoptInput(BaseModel):
    ref_id: int


class LaborInput(BaseModel):
    params: FsrParameters
    categories: list[LaborCategory] = Field(min_length=1, max_length=40)


class EquipmentInput(BaseModel):
    description: str | None = Field(default=None, max_length=200)
    params: EquipmentParameters


@router.get("/sources")
def list_reference_sources(
    catalog: CatalogStore = Depends(get_catalog),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Known publications, whether their file is on this server, and whether
    they are imported into the library; then the taller's own catálogos."""
    imported = {row["source_key"]: row for row in catalog.list_sources()}
    known = available_sources(settings.data_dir)
    known_keys = {spec["key"] for spec in known}
    own = [
        {
            "key": row["source_key"], "name": row["name"], "publisher": row["publisher"],
            "region": row["region"], "vigencia": row["vigencia"], "kind": row["kind"],
            "filename": "", "url": "", "available": True, "custom": True, "imported": row,
        }
        for key, row in imported.items() if key not in known_keys
    ]
    return {
        "sources": [{**spec, "imported": imported.get(spec["key"])} for spec in known] + own
    }


@router.post("/sources/custom", status_code=201)
async def import_custom_source(
    file: UploadFile,
    x_actor: Annotated[str | None, Header()] = None,
    name: str = "",
    vigencia: str = "",
    publisher: str = "",
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    """The taller's own catálogo de conceptos (XLSX/CSV with clave,
    descripción, unidad, precio unitario) as a reference source, labeled as
    the taller's, never as a publication."""
    raw = await file.read()
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error_type": "import_too_large", "max_bytes": MAX_IMPORT_BYTES},
        )
    title = name.strip() or Path(file.filename or "catalogo").stem[:80]
    try:
        rows = parse_concept_workbook(raw, file.filename or "")
    except CustomCatalogError as exc:
        raise HTTPException(
            status_code=422, detail={"error_type": "headers_not_found", "message": str(exc)}
        ) from exc
    key = source_key_for(title)
    count = catalog.import_reference(
        {
            "key": key, "name": title, "publisher": publisher.strip() or "Catálogo propio",
            "region": "MX", "vigencia": vigencia.strip(), "kind": "precios_unitarios", "url": "",
        },
        rows,
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    _publish_catalog_updated(x_actor, "reference_imported", f"{title}: {count} renglones")
    return {"source_key": key, "rows": count, "name": title}


@router.post("/import-matrices", status_code=201)
async def import_matrices(
    file: UploadFile,
    x_actor: Annotated[str | None, Header()] = None,
    source: str = "",
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    """Conceptos con sus matrices from an OPUS/Neodata Excel export (or the
    documented Tipo/Clave/Descripción/Unidad/Cantidad/Costo layout)."""
    raw = await file.read()
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error_type": "import_too_large", "max_bytes": MAX_IMPORT_BYTES},
        )
    label = source.strip() or Path(file.filename or "matrices").stem[:80]
    try:
        parse = parse_matrices_workbook(raw, file.filename or "")
    except CustomCatalogError as exc:
        raise HTTPException(
            status_code=422, detail={"error_type": "headers_not_found", "message": str(exc)}
        ) from exc
    result = catalog.import_matrices(parse, label)
    _publish_catalog_updated(
        x_actor, "matrices_imported",
        f"{label}: {result['concepts_created']} nuevos, {result['concepts_updated']} actualizados",
    )
    return result


@router.post("/sources/{source_key}/import")
def import_reference_source(
    source_key: str,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
    settings: Settings = Depends(get_settings),
) -> dict:
    spec = SOURCES.get(source_key)
    if spec is None:
        raise HTTPException(status_code=404, detail={"error_type": "source_not_found"})
    path = sources_dir(settings.data_dir) / spec.filename
    if not path.exists():
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": "source_file_missing",
                "message": f"Descarga {spec.filename} en data/sources antes de importar.",
                "url": spec.url,
            },
        )
    manifest = next(
        (e for e in available_sources(settings.data_dir) if e["key"] == source_key), {}
    )
    count = catalog.import_reference(
        {
            "key": spec.key, "name": spec.name, "publisher": spec.publisher,
            "region": spec.region, "vigencia": spec.vigencia, "kind": spec.kind, "url": spec.url,
        },
        spec.parser(path),
        sha256=manifest.get("sha256"),
    )
    _publish_catalog_updated(x_actor, "reference_imported", f"{spec.name}: {count} renglones")
    return {"source_key": source_key, "rows": count}


@router.get("/reference")
def search_reference(
    q: str = "",
    source: str | None = None,
    limit: int = 50,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    if len(q.strip()) < 2:
        return {"rows": []}
    return {"rows": catalog.search_reference(q, source_key=source, limit=limit)}


@router.post("/insumos/{code}/adopt")
def adopt_reference_price(
    code: str,
    body: AdoptInput,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    if code not in catalog.load_price_book():
        raise HTTPException(status_code=404, detail={"error_type": "insumo_not_found"})
    try:
        row = catalog.adopt_reference(code, body.ref_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail={"error_type": "reference_not_found", "message": str(exc)}
        ) from exc
    _publish_catalog_updated(x_actor, "insumo_updated", code)
    return row


@router.post("/concepts/{code}/adopt")
def adopt_concept_price(
    code: str,
    body: AdoptInput,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    """The concept's P.U. becomes the reference row's price (catálogo propio
    or publication), replacing its matrix until cleared."""
    try:
        row = catalog.adopt_concept_reference(code, body.ref_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail={"error_type": "not_found", "message": str(exc)}
        ) from exc
    _publish_catalog_updated(x_actor, "concept_updated", code)
    return row


@router.delete("/concepts/{code}/price")
def clear_concept_price(
    code: str,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    try:
        row = catalog.clear_concept_price(code)
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail={"error_type": "concept_not_found", "message": str(exc)}
        ) from exc
    _publish_catalog_updated(x_actor, "concept_updated", code)
    return row


class InventoryMappingInput(BaseModel):
    kind: Literal["block", "layer", "tag", "area"]
    pattern: str = Field(min_length=1, max_length=200)
    concept_code: str = Field(min_length=1, max_length=40)
    factor: float = Field(default=1.0, gt=0)


@router.get("/inventory-mappings")
def list_inventory_mappings(catalog: CatalogStore = Depends(get_catalog)) -> dict:
    """Symbol/layer → concept rules: how a levantamiento count becomes a quantity."""
    return {"mappings": catalog.list_inventory_mappings()}


@router.post("/inventory-mappings", status_code=201)
def add_inventory_mapping(
    body: InventoryMappingInput,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    try:
        row = catalog.add_inventory_mapping(
            kind=body.kind, pattern=body.pattern, concept_code=body.concept_code,
            factor=body.factor,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"error_type": "invalid_mapping", "message": str(exc)}
        ) from exc
    _publish_catalog_updated(
        x_actor, "inventory_mapping", f"{body.pattern} → {body.concept_code}"
    )
    return row


@router.delete("/inventory-mappings/{mapping_id}")
def delete_inventory_mapping(
    mapping_id: int,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    if not catalog.delete_inventory_mapping(mapping_id):
        raise HTTPException(status_code=404, detail={"error_type": "mapping_not_found"})
    _publish_catalog_updated(x_actor, "inventory_mapping", f"#{mapping_id} eliminada")
    return {"deleted": mapping_id}


@router.get("/labor")
def get_labor(catalog: CatalogStore = Depends(get_catalog)) -> dict:
    return labor_state(catalog)


@router.get("/labor/presets")
def get_labor_presets() -> dict:
    """Regional presets: minimum-wage zone and ISN per state, with sources."""
    return {"presets": [p.model_dump() for p in REGION_PRESETS]}


@router.post("/labor/presets/{key}")
def apply_labor_preset(
    key: str,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    """Apply a state's ISN and minimum wage to the saved parameters and
    categories, and reprice labor."""
    preset = preset_by_key(key)
    if preset is None:
        raise HTTPException(status_code=404, detail={"error_type": "preset_not_found"})
    state = labor_state(catalog)
    params = FsrParameters.model_validate(state["params"])
    categories = [
        LaborCategory.model_validate({k: v for k, v in c.items() if k != "breakdown"})
        for c in state["categories"]
    ]
    params, categories = apply_preset(params, categories, preset)
    applied = apply_labor(catalog, params, categories)
    _publish_catalog_updated(x_actor, "labor_preset_applied", preset.label)
    return {"preset": preset.model_dump(), "applied": applied, **labor_state(catalog)}


@router.put("/labor")
def put_labor(
    body: LaborInput,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    applied = apply_labor(catalog, body.params, body.categories)
    _publish_catalog_updated(x_actor, "labor_applied", f"{len(applied)} categorías")
    return {"applied": applied, **labor_state(catalog)}


@router.get("/equipment/{code}")
def get_equipment(code: str, catalog: CatalogStore = Depends(get_catalog)) -> dict:
    analysis = catalog.get_analysis(code)
    if analysis and analysis["kind"] == "costo_horario":
        params = EquipmentParameters.model_validate(analysis["params"])
        return {"code": code, "params": params.model_dump(),
                "breakdown": compute_costo_horario(params).model_dump(), "saved": True}
    return {"code": code, "params": None, "breakdown": None, "saved": False}


@router.put("/equipment/{code}")
def put_equipment(
    code: str,
    body: EquipmentInput,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    try:
        row = apply_equipment(catalog, code, body.description, body.params)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"error_type": "invalid_insumo", "message": str(exc)}
        ) from exc
    _publish_catalog_updated(x_actor, "insumo_updated", code)
    return row
