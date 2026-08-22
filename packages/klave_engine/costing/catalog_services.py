"""Catalog operations that compose calculators with the store: salario real
for labor insumos and costo horario for equipment, each leaving its full
analysis behind so the number can always be re-derived."""

from klave_engine.costing.catalog_store import CatalogStore
from klave_engine.costing.equipment import EquipmentParameters, compute_costo_horario
from klave_engine.costing.labor import (
    DEFAULT_CATEGORIES,
    FsrParameters,
    LaborCategory,
    compute_fsr,
    labor_provenance,
    now_month,
)

LABOR_SETTINGS_KEY = "labor_fsr"


def labor_state(store: CatalogStore) -> dict:
    """Current FSR parameters, categories, and their computed breakdowns."""
    saved = store.get_setting(LABOR_SETTINGS_KEY) or {}
    params = FsrParameters.model_validate(saved.get("params") or {})
    categories = [
        LaborCategory.model_validate(c) for c in saved.get("categories") or []
    ] or list(DEFAULT_CATEGORIES)
    return {
        "params": params.model_dump(),
        "categories": [
            {**c.model_dump(), "breakdown": compute_fsr(c.salario_nominal, params).model_dump()}
            for c in categories
        ],
        "applied_at": saved.get("applied_at"),
    }


def apply_labor(
    store: CatalogStore, params: FsrParameters, categories: list[LaborCategory]
) -> list[dict]:
    """Persist the parameters and price every labor category at Sn × Fsr."""
    applied: list[dict] = []
    vigencia = now_month()
    for category in categories:
        breakdown = compute_fsr(category.salario_nominal, params)
        row = store.upsert_insumo(
            category.code,
            description=category.description,
            unit="JOR",
            resource_type="mano_de_obra",
            unit_cost=breakdown.salario_real,
            source=labor_provenance(params),
            source_type="calculado",
            region="MX",
            vigencia=vigencia,
        )
        store.set_analysis(
            category.code, "fsr",
            {"salario_nominal": category.salario_nominal, "params": params.model_dump()},
            breakdown.model_dump(),
        )
        applied.append({**row, "breakdown": breakdown.model_dump()})
    store.set_setting(
        LABOR_SETTINGS_KEY,
        {
            "params": params.model_dump(),
            "categories": [c.model_dump() for c in categories],
            "applied_at": vigencia,
        },
    )
    return applied


def apply_equipment(
    store: CatalogStore, code: str, description: str | None, params: EquipmentParameters
) -> dict:
    """Price an equipment insumo per hour from its RLOPSRM analysis."""
    breakdown = compute_costo_horario(params)
    row = store.upsert_insumo(
        code,
        description=description,
        unit="HR",
        resource_type="equipo",
        unit_cost=breakdown.costo_horario,
        source="Costo horario calculado (RLOPSRM art. 194–206)",
        source_type="calculado",
        region="MX",
        vigencia=now_month(),
    )
    store.set_analysis(code, "costo_horario", params.model_dump(), breakdown.model_dump())
    return {**row, "breakdown": breakdown.model_dump()}
