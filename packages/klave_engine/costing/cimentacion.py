"""Relleno and acarreo derived from what the excavation and the concrete say.

The pit is measured in banco (CIM-001). What the concrete and the plantilla
do not occupy gets filled back compacted (CIM-004, priced with imported
tepetate); everything excavated leaves the site bulked by the swell factor
(CIM-005). Both lines state their arithmetic; an adjustment overrides them.
"""

from __future__ import annotations

from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    CostingAssumptions,
    QuantityKind,
)

CODE_EXCAVATION = "CIM-001"
CODE_FILL = "CIM-004"
CODE_HAUL = "CIM-005"
# Volumes that stay in the pit: foundation concrete and the plantilla slab.
BURIED_CONCRETE = ("CIM-002", "CIM-007", "CIM-008", "CIM-011")
PLANTILLA_CODE = "CIM-003"
PLANTILLA_THICKNESS_M = 0.05


def apply_cimentacion_earthmoving(
    boq: BillOfQuantities, catalog: list, apus: dict, assumptions: CostingAssumptions
) -> int:
    """Add relleno and acarreo lines when there is an excavation to derive
    them from. Returns how many lines were added."""
    lines = {line.concept_code: line for line in boq.lines}
    excavation = lines.get(CODE_EXCAVATION)
    if excavation is None or excavation.quantity <= 0:
        return 0
    concepts = {concept.code: concept for concept in catalog}
    buried = sum(lines[code].quantity for code in BURIED_CONCRETE if code in lines)
    plantilla_line = lines.get(PLANTILLA_CODE)
    if plantilla_line is not None:
        buried += plantilla_line.quantity * PLANTILLA_THICKNESS_M
    added = 0

    def emit(code: str, quantity: float, note: str) -> None:
        nonlocal added
        concept = concepts.get(code)
        apu = apus.get(code)
        if concept is None or quantity <= 0 or code in lines:
            return
        unit_price = apu.direct_unit_cost if apu else 0.0
        boq.lines.append(
            BoqLine(
                concept_code=code,
                description=concept.description,
                unit=concept.unit,
                quantity=round(quantity, 3),
                unit_price=unit_price,
                amount=round(quantity * unit_price, 2),
                unpriced=apu is None,
                phase=concept.phase,
                raw_quantity=round(quantity, 3),
                raw_kind=QuantityKind.VOLUME,
                source_detection_count=excavation.source_detection_count,
                source_detections=list(excavation.source_detections)[:200],
                confidence=excavation.confidence,
                assumptions=list(concept.assumptions) + [note],
            )
        )
        added += 1

    fill = excavation.quantity - buried
    emit(
        CODE_FILL,
        fill,
        f"Excavación {excavation.quantity:,.2f} m³ (banco) − {buried:,.2f} m³ enterrados "
        "(concreto de cimentación y plantilla)",
    )
    haul = excavation.quantity * assumptions.excavation_swell_factor
    emit(
        CODE_HAUL,
        haul,
        f"Excavación {excavation.quantity:,.2f} m³ (banco) × abundamiento "
        f"{assumptions.excavation_swell_factor:.2f} (volumen suelto en camión)",
    )
    if added:
        boq.direct_cost_total = round(sum(line.amount for line in boq.lines), 2)
        totals: dict[str, float] = {}
        for line in boq.lines:
            totals[line.phase] = round(totals.get(line.phase, 0.0) + line.amount, 2)
        boq.totals_by_phase = totals
    return added
