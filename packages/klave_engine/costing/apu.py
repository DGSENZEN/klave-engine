"""Análisis de Precios Unitarios: build the direct unit cost of each concept."""

from klave_engine.common.errors import ReportGenerationError
from klave_engine.costing.insumos import APU_TEMPLATES, RESOURCES
from klave_engine.costing.models import (
    ApuLine,
    Concept,
    Resource,
    ResourceType,
    UnitPriceAnalysis,
)


def build_apu(
    concept: Concept,
    resources: dict[str, Resource] | None = None,
    templates: dict[str, list[tuple[str, float]]] | None = None,
) -> UnitPriceAnalysis:
    resources = resources or RESOURCES
    templates = templates or APU_TEMPLATES
    template = templates.get(concept.code)
    if not template:
        raise ReportGenerationError(f"No APU template for concept {concept.code}")

    lines: list[ApuLine] = []
    percentage_entries: list[tuple[Resource, float]] = []
    for resource_code, quantity in template:
        resource = resources.get(resource_code)
        if resource is None:
            raise ReportGenerationError(f"Unknown resource {resource_code}")
        if resource.is_labor_percentage:
            percentage_entries.append((resource, quantity))
            continue
        if resource.unit_cost <= 0:
            # Un insumo sin precio no vale cero: vale lo que nadie ha dicho
            # todavía. Sumarlo como cero daría un P.U. más barato que la obra
            # y con cara de estar completo, que es la peor forma de estar mal.
            # El concepto se queda sin matriz y el presupuesto lo dice.
            raise ReportGenerationError(
                f"{concept.code}: el insumo {resource.code} ({resource.description[:40]}) "
                "no tiene precio; carga tu lista de insumos o adopta un P.U. publicado."
            )
        lines.append(
            ApuLine(
                resource_code=resource.code,
                description=resource.description,
                unit=resource.unit,
                quantity=quantity,
                unit_cost=resource.unit_cost,
                amount=round(quantity * resource.unit_cost, 2),
                resource_type=resource.resource_type,
            )
        )

    labor_subtotal = sum(
        line.amount for line in lines if line.resource_type == ResourceType.labor
    )
    for resource, quantity in percentage_entries:
        fraction = resource.unit_cost * quantity
        lines.append(
            ApuLine(
                resource_code=resource.code,
                description=resource.description,
                unit=resource.unit,
                quantity=round(fraction * 100, 2),  # shown as percentage
                unit_cost=round(labor_subtotal, 2),
                amount=round(fraction * labor_subtotal, 2),
                resource_type=resource.resource_type,
            )
        )

    breakdown = {rt.value: 0.0 for rt in ResourceType}
    for line in lines:
        breakdown[line.resource_type.value] = round(
            breakdown[line.resource_type.value] + line.amount, 2
        )
    return UnitPriceAnalysis(
        concept_code=concept.code,
        concept_description=concept.description,
        unit=concept.unit,
        lines=lines,
        breakdown=breakdown,
        direct_unit_cost=round(sum(line.amount for line in lines), 2),
    )


def build_all_apus(
    concepts: list[Concept],
    resources: dict[str, Resource] | None = None,
    templates: dict[str, list[tuple[str, float]]] | None = None,
) -> dict[str, UnitPriceAnalysis]:
    """APUs for every concept that has a matrix; a concept without one is
    skipped (it cannot be priced — never silently priced at zero)."""
    effective = templates or APU_TEMPLATES
    salida: dict[str, UnitPriceAnalysis] = {}
    for concept in concepts:
        if concept.code not in effective:
            continue
        try:
            salida[concept.code] = build_apu(concept, resources=resources, templates=templates)
        except ReportGenerationError:
            # Le falta el precio de algún insumo: el concepto queda sin
            # matriz, que es exactamente lo que ya sabe manejar el
            # presupuesto — cantidad real, «sin precio», y nunca un cero.
            continue
    return salida
