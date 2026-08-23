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


# ------------------------------------------------------------ plantillas

PLANTILLA_MATCH_MIN = 0.75


def import_plantilla(
    store: CatalogStore,
    raw: bytes,
    filename: str,
    *,
    name: str,
    tipologia: str,
    area_m2: float,
    actor: str = "",
) -> dict:
    """A past presupuesto becomes a plantilla: its rows enter the library as
    the taller's prices, each row maps to a Klave concept (by alias clave,
    else by description match) or becomes a manual concept priced by its
    own row, and every concept gets a per-m² rule. Concepts the engine reads
    from the plan keep a comparison-only rule (never a proposed line)."""
    import hashlib

    from klave_engine.costing.indicadores import phase_shares_from_rows
    from klave_engine.costing.matching import Candidate, rank
    from klave_engine.costing.sources.custom import source_key_for
    from klave_engine.costing.sources.presupuesto import parse_presupuesto_file

    if area_m2 <= 0:
        raise ValueError("El área construida del proyecto debe ser positiva.")
    rows = parse_presupuesto_file(raw, filename)
    key = "plantilla-" + source_key_for(name)[:60]
    source_key = key
    priced = [r for r in rows if r.price]
    store.import_reference(
        {
            "key": source_key, "name": f"Plantilla {name}", "publisher": "Catálogo propio",
            "region": "MX", "vigencia": "", "kind": "precios_unitarios", "url": "",
        },
        [
            {
                "clave": r.clave, "description": r.description, "unit": r.unit,
                "price": float(r.price or 0.0), "group_clave": "", "group_description": r.group,
            }
            for r in priced
        ],
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    store.save_plantilla(
        key=key, name=name, tipologia=tipologia, area_m2=area_m2, source_key=source_key,
        rows=len(rows), actor=actor, phase_shares=phase_shares_from_rows(rows),
    )
    references = {r["clave"].upper(): r for r in store.list_reference_rows([source_key])}
    aliases = store.load_concept_aliases()
    by_alias_clave = {a["clave"].upper(): code for code, a in aliases.items()}
    concepts = store.load_concepts()
    by_code = {c["code"]: c for c in concepts}
    candidates = [
        Candidate(kind="concept", key=c["code"], clave=c["code"], description=c["description"],
                  unit=c["unit"], price=None, phase=c["phase"])
        for c in concepts
    ]
    mapped = created = compared = 0
    problems: list[str] = []
    for row in rows:
        target = by_alias_clave.get(row.clave) or (row.clave if row.clave in by_code else None)
        how = "alias" if target else ""
        if target is None:
            best = rank(row.description, row.unit, candidates, phase=row.group, limit=1)
            if best and best[0].score >= PLANTILLA_MATCH_MIN:
                target = best[0].candidate.key
                how = f"coincidencia {best[0].score:.0%}"
        if target is None:
            reference = references.get(row.clave)
            if reference is None:
                problems.append(
                    f"{row.clave}: sin precio en el presupuesto y sin concepto equivalente; "
                    "no se crea."
                )
                continue
            try:
                store.create_priced_concept(
                    code=row.clave, description=row.description, unit=row.unit,
                    phase=row.group or "Plantilla", production_rate_per_day=10.0,
                    ref_id=int(reference["ref_id"]),
                )
                created += 1
            except ValueError as exc:
                problems.append(f"{row.clave}: {exc}")
                continue
            target = row.clave
            how = "concepto nuevo con su precio"
        concept = by_code.get(target) or {"rule_key": None}
        engine_read = bool(concept.get("rule_key"))
        store.add_parametric_rule(
            concept_code=target, basis="m2_construida", factor=row.quantity / area_m2,
            source=f"{name} ({area_m2:g} m²)", plantilla_key=key,
            note=f"{row.clave} · {how}" if how else row.clave, engine_read=engine_read,
        )
        if engine_read:
            compared += 1
        else:
            mapped += 1
    return {
        "plantilla_key": key, "rows": len(rows), "priced_rows": len(priced),
        "rules": mapped, "comparison_rules": compared, "concepts_created": created,
        "problems": problems,
    }
