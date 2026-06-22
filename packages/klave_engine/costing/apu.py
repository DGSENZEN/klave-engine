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
    concepts: list[Concept], resources: dict[str, Resource] | None = None
) -> dict[str, UnitPriceAnalysis]:
    return {concept.code: build_apu(concept, resources=resources) for concept in concepts}
