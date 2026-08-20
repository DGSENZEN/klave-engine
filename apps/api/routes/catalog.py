"""Workspace catalog API: insumos, APU matrices, and rendimientos.

Edits here change the workspace baseline used by every future (re)compute;
per-project price overrides in costing_overrides.json still apply on top.
A global ``catalog_updated`` event tells open projects to offer a recompute.
"""

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from klave_engine.common.config import Settings
from klave_engine.costing.catalog import PHASE_ORDER, build_default_catalog
from klave_engine.costing.catalog_store import CatalogStore, get_catalog_store
from klave_engine.costing.models import CostingAssumptions
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
    concepts = build_default_catalog(CostingAssumptions())
    rendimientos = catalog.load_rendimientos()
    templates = catalog.load_templates()
    return {
        "insumos": catalog.list_insumos(),
        "concepts": [
            {
                "code": concept.code,
                "description": concept.description,
                "unit": concept.unit,
                "phase": concept.phase,
                "production_rate_per_day": rendimientos.get(
                    concept.code, concept.production_rate_per_day
                ),
            }
            for concept in concepts
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
    known = {concept.code for concept in build_default_catalog(CostingAssumptions())}
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
    known = {concept.code for concept in build_default_catalog(CostingAssumptions())}
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
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error_type": "invalid_encoding",
                "message": "El CSV debe estar codificado en UTF-8.",
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
