"""Bill of quantities: detections × catalog rules × unit prices."""

from collections import defaultdict

from klave_engine.common.logging import get_logger, log_stage
from klave_engine.costing.insumos import REFERENCE_PRICE_DISCLAIMER
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    Concept,
    QuantityKind,
    UnitPriceAnalysis,
)
from klave_engine.detection.results import Detection
from klave_engine.dxf.units import DrawingUnits

logger = get_logger(__name__)


def _raw_quantity(
    concept: Concept, detections: list[Detection], meters_factor: float
) -> float:
    rule = concept.rule
    if rule.kind == QuantityKind.COUNT:
        return float(len(detections))
    total = 0.0
    for detection in detections:
        value = detection.properties.get(rule.source_property or "")
        if value is None:
            continue
        total += float(value)
    if rule.kind == QuantityKind.LENGTH:
        return total * meters_factor
    return total * meters_factor * meters_factor  # area


def generate_bill_of_quantities(
    project_id: str,
    detections: list[Detection],
    units: DrawingUnits,
    catalog: list[Concept],
    apus: dict[str, UnitPriceAnalysis],
    currency: str = "MXN",
) -> BillOfQuantities:
    boq = BillOfQuantities(project_id=project_id, currency=currency)
    boq.assumptions.append(REFERENCE_PRICE_DISCLAIMER)

    meters_factor = units.to_meters()
    if meters_factor is None:
        meters_factor = 1.0
        boq.warnings.append(
            "Unidades del plano desconocidas: las cantidades asumen metros. "
            "Verificar la escala antes de usar el presupuesto."
        )
    else:
        boq.assumptions.append(
            f"Unidades del plano: {units.unit} (fuente: {units.source}, "
            f"confianza {units.confidence:.0%})"
        )

    by_type = defaultdict(list)
    for detection in detections:
        by_type[detection.detection_type].append(detection)

    for concept in catalog:
        matched = by_type.get(concept.rule.detection_type, [])
        raw = _raw_quantity(concept, matched, meters_factor)
        quantity = round(raw * concept.quantity_factor, 6)
        if quantity <= 0:
            boq.warnings.append(
                f"Concepto {concept.code} ({concept.description[:40]}…) sin "
                "cantidades: no hubo detecciones aplicables."
            )
            continue
        apu = apus[concept.code]
        contributing = [
            d
            for d in matched
            if concept.rule.kind == QuantityKind.COUNT
            or (concept.rule.source_property or "") in d.properties
        ]
        confidence = (
            sum(d.confidence for d in contributing) / len(contributing)
            if contributing
            else 0.0
        )
        boq.lines.append(
            BoqLine(
                concept_code=concept.code,
                description=concept.description,
                unit=concept.unit,
                quantity=quantity,
                unit_price=apu.direct_unit_cost,
                amount=round(quantity * apu.direct_unit_cost, 2),
                phase=concept.phase,
                raw_quantity=round(raw, 3),
                raw_kind=concept.rule.kind,
                source_detection_count=len(contributing),
                source_detections=[d.detection_id for d in contributing][:200],
                confidence=round(confidence, 3),
                assumptions=concept.assumptions,
            )
        )

    review_threshold = 0.6
    for line in boq.lines:
        if line.confidence < review_threshold:
            boq.warnings.append(
                f"Concepto {line.concept_code}: confianza de detección baja "
                f"({line.confidence:.0%}); revisar la cantidad en el visor del "
                "plano antes de usar este importe."
            )

    boq.direct_cost_total = round(sum(line.amount for line in boq.lines), 2)
    totals: dict[str, float] = defaultdict(float)
    for line in boq.lines:
        totals[line.phase] += line.amount
    boq.totals_by_phase = {phase: round(total, 2) for phase, total in totals.items()}

    log_stage(
        logger,
        "boq_generated",
        project_id=project_id,
        line_count=len(boq.lines),
        direct_cost_total=boq.direct_cost_total,
        warning_count=len(boq.warnings),
    )
    return boq
