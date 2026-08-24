"""Explosión de insumos: every resource the presupuesto consumes, totalled.

APU × cantidad, summed per insumo across concepts: how much cemento,
cuántas jornadas de albañil, cuántas horas de retro. The document a
taller builds by hand in Excel to buy, to hire and to schedule deliveries
— and the requisición por partida that follows from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from klave_engine.costing.models import CostReport, ResourceType


@dataclass
class ResourceTotal:
    code: str
    description: str
    unit: str
    resource_type: str
    unit_cost: float
    quantity: float = 0.0
    amount: float = 0.0
    by_phase: dict[str, float] = field(default_factory=dict)
    by_concept: dict[str, float] = field(default_factory=dict)
    is_percentage: bool = False


@dataclass
class Explosion:
    resources: list[ResourceTotal]
    total: float
    by_type: dict[str, float]
    notes: list[str] = field(default_factory=list)


def explode(report: CostReport) -> Explosion:
    apus = {apu.concept_code: apu for apu in report.apus}
    totals: dict[str, ResourceTotal] = {}
    adopted: list[str] = []
    for line in report.boq.lines:
        apu = apus.get(line.concept_code)
        if apu is None:
            continue
        if not apu.lines:
            adopted.append(line.taller_clave or line.concept_code)
            continue
        for component in apu.lines:
            total = totals.get(component.resource_code)
            if total is None:
                total = totals[component.resource_code] = ResourceTotal(
                    code=component.resource_code, description=component.description,
                    unit=component.unit, resource_type=str(component.resource_type),
                    unit_cost=component.unit_cost,
                    # A percentage insumo (herramienta menor = %MO) rides on the
                    # matrix's labour; the flag lives on the Resource, not on the
                    # APU line, so it is read from the unit the line carries.
                    is_percentage=component.unit.strip().startswith("%"),
                )
            quantity = component.quantity * line.quantity
            amount = component.amount * line.quantity
            total.quantity += quantity
            total.amount += amount
            total.by_phase[line.phase] = total.by_phase.get(line.phase, 0.0) + quantity
            key = line.taller_clave or line.concept_code
            total.by_concept[key] = total.by_concept.get(key, 0.0) + quantity
    resources = sorted(totals.values(), key=lambda r: (r.resource_type, -r.amount))
    for r in resources:
        r.quantity = round(r.quantity, 4)
        r.amount = round(r.amount, 2)
        r.by_phase = {k: round(v, 4) for k, v in r.by_phase.items()}
        r.by_concept = {k: round(v, 4) for k, v in r.by_concept.items()}
    by_type: dict[str, float] = {rt.value: 0.0 for rt in ResourceType}
    for r in resources:
        by_type[r.resource_type] = round(by_type.get(r.resource_type, 0.0) + r.amount, 2)
    notes: list[str] = []
    if adopted:
        notes.append(
            f"{len(adopted)} concepto(s) con P.U. adoptado sin matriz no se explotan: "
            f"{', '.join(adopted[:8])}{'…' if len(adopted) > 8 else ''}."
        )
    return Explosion(
        resources=resources, total=round(sum(r.amount for r in resources), 2),
        by_type=by_type, notes=notes,
    )
