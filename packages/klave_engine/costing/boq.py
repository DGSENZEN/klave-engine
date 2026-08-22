"""Bill of quantities: detections × catalog rules × unit prices.

When the sheet is segmented into plan views, quantities are computed
view-aware: detail/table detections are excluded, foundation work is taken
only from the foundation plan, level elements are summed across plans, the
footprint is counted once, and columns are counted once (max over plans) with
their real measured sections × the building height from N.P.T. levels.

Without segmentation (a single implicit plan, e.g. simple sheets and the test
fixture) the flat count/sum computation is used unchanged.
"""

from collections import defaultdict

from klave_engine.common.logging import get_logger, log_stage
from klave_engine.costing.insumos import REFERENCE_PRICE_DISCLAIMER
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    Concept,
    CostingAssumptions,
    QuantityKind,
    UnitPriceAnalysis,
    ViewScope,
)
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation
from klave_engine.dxf.units import DrawingUnits

logger = get_logger(__name__)

REVIEW_THRESHOLD = 0.6
# Plausible column/castillo cross-section bounds (m²); measured marker sections
# outside this range (e.g. an ID bubble or grid circle) are rejected as
# implausible and the assumed section is used instead.
MIN_COLUMN_SECTION_M2 = 0.01  # 10×10 cm castillo
MAX_COLUMN_SECTION_M2 = 1.00  # 1×1 m large column


def _raw_over(concept: Concept, detections: list[Detection], meters_factor: float) -> float:
    """Count, or summed length/area (converted to metres), over a detection set."""
    rule = concept.rule
    assert rule is not None  # callers skip manual (rule-less) concepts
    if rule.kind == QuantityKind.COUNT:
        return float(len(detections))
    total = sum(
        float(d.properties[rule.source_property])
        for d in detections
        if rule.source_property and rule.source_property in d.properties
    )
    if rule.kind == QuantityKind.LENGTH:
        return total * meters_factor
    return total * meters_factor * meters_factor  # area


def _contributing(concept: Concept, detections: list[Detection]) -> list[Detection]:
    rule = concept.rule
    assert rule is not None  # callers skip manual (rule-less) concepts
    if rule.kind == QuantityKind.COUNT:
        return list(detections)
    prop = rule.source_property or ""
    return [d for d in detections if prop in d.properties]


class _LineResult:
    def __init__(self, quantity: float, raw: float, dets: list[Detection],
                 notes: list[str]) -> None:
        self.quantity = quantity
        self.raw = raw
        self.dets = dets
        self.notes = notes


def _column_volume(
    columns: list[Detection],
    meters_factor: float,
    assumptions: CostingAssumptions,
    total_height: float | None,
) -> _LineResult:
    """Volume = (columns of the most complete plan) × section × building height.

    Section is the real measured marker section when available, otherwise the
    assumed default; height is the top N.P.T. level when known.
    """
    height = total_height if total_height else assumptions.column_height_m
    measured = 0
    declared = 0
    volume = 0.0
    for column in columns:
        section_du2 = column.properties.get("section_area_du2")
        if section_du2 is not None and column.properties.get("section_source") == "cuadro":
            declared += 1
        section_m2 = (
            float(section_du2) * meters_factor * meters_factor
            if section_du2 is not None
            else None
        )
        # Only trust a measured section within plausible physical bounds;
        # otherwise the marker was an ID bubble / grid circle, not the section.
        if section_m2 is not None and MIN_COLUMN_SECTION_M2 <= section_m2 <= MAX_COLUMN_SECTION_M2:
            volume += section_m2 * height
            measured += 1
        else:
            volume += assumptions.column_section_m2 * height
    notes = [
        f"{len(columns)} columnas (vista de planta más completa) × altura "
        f"{height:.2f} m"
        + (" (de niveles N.P.T.)" if total_height else " (supuesta)"),
        f"Sección: {declared} declaradas en el plano (cuadro/detalle), "
        f"{measured - declared} medidas del marcador, "
        f"{len(columns) - measured} supuestas ({assumptions.column_section_m2:.3f} m²)",
    ]
    return _LineResult(round(volume, 6), float(len(columns)), columns, notes)


def _scoped_result(
    concept: Concept,
    matched_plan: list[Detection],
    segmentation: SheetSegmentation,
    meters_factor: float,
    assumptions: CostingAssumptions,
) -> _LineResult:
    """Compute a BoQ line for a concept on a segmented sheet, per its view scope."""
    assignment = segmentation.assignment
    foundation_ids = {v.view_id for v in segmentation.foundation_views()}
    superstructure_ids = {v.view_id for v in segmentation.superstructure_views()}
    plan_ids = {v.view_id for v in segmentation.plan_views()}

    def in_views(dets: list[Detection], view_ids: set[str]) -> list[Detection]:
        return [d for d in dets if assignment.get(d.detection_id) in view_ids]

    scope = concept.view_scope

    if scope == ViewScope.COLUMN_VOLUME:
        by_view: dict[str, list[Detection]] = defaultdict(list)
        for d in matched_plan:
            by_view[assignment[d.detection_id]].append(d)
        canonical = max(by_view.values(), key=len, default=[])
        return _column_volume(canonical, meters_factor, assumptions, segmentation.total_height())

    if scope == ViewScope.FOUNDATION_ONLY:
        dets = in_views(matched_plan, foundation_ids) or matched_plan
        raw = _raw_over(concept, dets, meters_factor)
        note = (
            f"Solo planta de cimentación ({len(dets)} detecciones)"
            if foundation_ids
            else "Sin planta de cimentación identificada; se usan todas las vistas de planta"
        )
        return _LineResult(round(raw * concept.quantity_factor, 6), raw,
                           _contributing(concept, dets), [note])

    if scope == ViewScope.SUPERSTRUCTURE_SUM:
        dets = in_views(matched_plan, superstructure_ids) or matched_plan
        raw = _raw_over(concept, dets, meters_factor)
        return _LineResult(round(raw * concept.quantity_factor, 6), raw,
                           _contributing(concept, dets),
                           [f"Suma de plantas de superestructura ({len(dets)} detecciones)"])

    if scope == ViewScope.FOOTPRINT_ONCE:
        best_raw = 0.0
        best_dets: list[Detection] = []
        for view_id in plan_ids:
            dets = in_views(matched_plan, {view_id})
            raw = _raw_over(concept, dets, meters_factor)
            if raw > best_raw:
                best_raw, best_dets = raw, dets
        return _LineResult(round(best_raw * concept.quantity_factor, 6), best_raw,
                           _contributing(concept, best_dets),
                           ["Huella de la planta más grande (una sola vez)"])

    raw = _raw_over(concept, matched_plan, meters_factor)
    return _LineResult(round(raw * concept.quantity_factor, 6), raw,
                       _contributing(concept, matched_plan), [])


def generate_bill_of_quantities(
    project_id: str,
    detections: list[Detection],
    units: DrawingUnits,
    catalog: list[Concept],
    apus: dict[str, UnitPriceAnalysis],
    currency: str = "MXN",
    segmentation: SheetSegmentation | None = None,
    assumptions: CostingAssumptions | None = None,
) -> BillOfQuantities:
    boq = BillOfQuantities(project_id=project_id, currency=currency)
    boq.assumptions.append(REFERENCE_PRICE_DISCLAIMER)
    assumptions = assumptions or CostingAssumptions()

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

    seg = segmentation if (segmentation is not None and segmentation.is_segmented) else None
    if seg is not None:
        plan_ids = {v.view_id for v in seg.plan_views()}
        boq.assumptions.append(
            f"Plano segmentado en {len(plan_ids)} vistas de planta; las cantidades "
            "deduplican elementos repetidos entre vistas y excluyen detalles/tablas."
        )
        height = seg.total_height()
        if height:
            boq.assumptions.append(
                f"Altura total del edificio {height:.2f} m (de niveles N.P.T.: "
                f"{', '.join(f'+{lvl:.2f}' for lvl in seg.npt_levels)})"
            )

    by_type: dict = defaultdict(list)
    for detection in detections:
        by_type[detection.detection_type].append(detection)

    for concept in catalog:
        if concept.rule is None:
            # Manual concept: only documented adjustments give it quantity.
            continue
        matched = by_type.get(concept.rule.detection_type, [])
        if seg is not None:
            matched_plan = [
                d for d in matched if seg.assignment.get(d.detection_id) in plan_ids
            ]
            result = _scoped_result(
                concept, matched_plan, seg, meters_factor, assumptions
            )
        else:
            raw = _raw_over(concept, matched, meters_factor)
            # Columns fold section×height into quantity_factor on a flat sheet.
            quantity = round(raw * concept.quantity_factor, 6)
            result = _LineResult(quantity, raw, _contributing(concept, matched), [])

        if result.quantity <= 0:
            boq.warnings.append(
                f"Concepto {concept.code} ({concept.description[:40]}…) sin "
                "cantidades: no hubo detecciones aplicables."
            )
            continue

        apu = apus[concept.code]
        contributing = result.dets
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
                quantity=result.quantity,
                unit_price=apu.direct_unit_cost,
                amount=round(result.quantity * apu.direct_unit_cost, 2),
                phase=concept.phase,
                raw_quantity=round(result.raw, 3),
                raw_kind=concept.rule.kind,
                source_detection_count=len(contributing),
                source_detections=[d.detection_id for d in contributing][:200],
                confidence=round(confidence, 3),
                assumptions=concept.assumptions + result.notes,
            )
        )

    for line in boq.lines:
        if line.confidence < REVIEW_THRESHOLD:
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
        segmented=seg is not None,
        line_count=len(boq.lines),
        direct_cost_total=boq.direct_cost_total,
        warning_count=len(boq.warnings),
    )
    return boq
