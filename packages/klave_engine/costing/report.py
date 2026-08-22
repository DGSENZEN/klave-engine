"""Cost report assembly: the full workflow in one artifact, plus exports."""

import csv
import io
from pathlib import Path

from klave_engine.common.io import write_text
from klave_engine.common.logging import get_logger, log_stage
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import (
    PHASE_ORDER,
    build_catalog_from_store,
    build_default_catalog,
)
from klave_engine.costing.financial import build_financial_plan
from klave_engine.costing.formwork import apply_formwork, compute_formwork
from klave_engine.costing.integration import integrate_costs
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    Concept,
    CostingAssumptions,
    CostingConfig,
    CostReport,
    QuantityKind,
    Resource,
    ResourceType,
    UnitPriceAnalysis,
)
from klave_engine.costing.reviews import ManualAdjustment
from klave_engine.costing.schedule import build_schedule
from klave_engine.costing.steel import SteelAssumptions, apply_steel, compute_steel
from klave_engine.detection.dimensions import DimensionInventory
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation
from klave_engine.dxf.units import DrawingUnits

logger = get_logger(__name__)


def _calibrate_assumptions(
    base: CostingAssumptions, dimensions: DimensionInventory | None
) -> tuple[CostingAssumptions, list[str]]:
    """Override assumed geometry with dimensions measured from the drawing."""
    if dimensions is None:
        return base, []
    calibrated = base.model_copy(deep=True)
    notes: list[str] = []
    section = dimensions.typical_section_m2
    if section is not None:
        a, b = dimensions.typical_section_cm  # type: ignore[misc]
        calibrated.column_section_m2 = section
        notes.append(
            f"Sección de columna/castillo {a}x{b} cm = {section:.4f} m² tomada del "
            "plano (verificar contra el cuadro de castillos)."
        )
    if dimensions.typical_wall_thickness_cm is not None:
        notes.append(
            f"Espesor de muro {dimensions.typical_wall_thickness_cm} cm detectado en el plano."
        )
    if dimensions.vigueta_system is not None:
        notes.append(f"Sistema de losa detectado: vigueta y bovedilla {dimensions.vigueta_system}.")
    return calibrated, notes


def adopted_price_apu(concept: Concept, adopted: dict) -> UnitPriceAnalysis:
    """A concept priced by an adopted reference row: no matrix, the row's
    P.U. as direct unit cost, and its provenance on the analysis."""
    vigencia = f" · vigencia {adopted['vigencia']}" if adopted.get("vigencia") else ""
    return UnitPriceAnalysis(
        concept_code=concept.code,
        concept_description=concept.description,
        unit=concept.unit,
        lines=[],
        breakdown={rt.value: 0.0 for rt in ResourceType},
        direct_unit_cost=round(float(adopted["price"]), 2),
        price_source=f"{adopted.get('source') or 'referencia'} · {adopted.get('clave') or ''}"
        f"{vigencia}",
    )


def generate_cost_report(
    project_id: str,
    detections: list[Detection],
    units: DrawingUnits,
    config: CostingConfig | None = None,
    segmentation: SheetSegmentation | None = None,
    dimensions: DimensionInventory | None = None,
    price_book: dict[str, Resource] | None = None,
    apu_templates: dict[str, list[tuple[str, float]]] | None = None,
    rendimientos: dict[str, float] | None = None,
    adjustments: list[ManualAdjustment] | None = None,
    store_concepts: list[dict] | None = None,
    schedule_specs: dict | None = None,
    concept_prices: dict[str, dict] | None = None,
) -> CostReport:
    config = config or CostingConfig()
    assumptions, calibration_notes = _calibrate_assumptions(config.assumptions, dimensions)
    catalog = (
        build_catalog_from_store(store_concepts, assumptions)
        if store_concepts
        else build_default_catalog(assumptions)
    )
    # Rendimiento overrides come from the workspace catalog; they drive the
    # schedule durations without touching the detection→quantity rules.
    if rendimientos:
        for concept in catalog:
            override = rendimientos.get(concept.code)
            if override is not None and override > 0:
                concept.production_rate_per_day = override
    apus = build_all_apus(catalog, price_book, templates=apu_templates)
    for concept in catalog:
        adopted = (concept_prices or {}).get(concept.code)
        if adopted:
            apus[concept.code] = adopted_price_apu(concept, adopted)
    boq = generate_bill_of_quantities(
        project_id, detections, units, catalog, apus, config.currency,
        segmentation=segmentation, assumptions=assumptions,
    )
    boq.assumptions.extend(calibration_notes)
    # Acero de refuerzo derives from the counted elements and the sheet's
    # armados; it runs before human adjustments so they can correct it too.
    steel = compute_steel(
        boq, detections, schedule_specs, segmentation, units.to_meters(),
        assumptions.column_height_m,
        SteelAssumptions(wall_height_m=assumptions.wall_height_m),
    )
    apply_steel(boq, catalog, apus, steel)
    formwork = compute_formwork(
        boq, detections, schedule_specs, dimensions, assumptions, units.to_meters(),
        segmentation.total_height() if segmentation is not None else None,
    )
    apply_formwork(boq, catalog, apus, formwork)
    if adjustments:
        _apply_adjustments(boq, catalog, apus, adjustments)
    integration = integrate_costs(boq.direct_cost_total, config.indirects)
    levels = (
        max(len(segmentation.superstructure_views()), 1)
        if segmentation is not None and segmentation.is_segmented
        else 1
    )
    schedule = build_schedule(boq, catalog, config.schedule, levels=levels)
    financial = build_financial_plan(schedule, integration, config.financial, config.currency)

    report = CostReport(
        project_id=project_id,
        currency=config.currency,
        drawing_units=units,
        boq=boq,
        apus=[apus[line.concept_code] for line in boq.lines],
        integration=integration,
        schedule=schedule,
        financial=financial,
        warnings=list(boq.warnings),
    )
    log_stage(
        logger,
        "cost_report_generated",
        project_id=project_id,
        direct_cost=boq.direct_cost_total,
        sale_price=integration.sale_price,
        grand_total=integration.grand_total,
        duration_days=schedule.total_duration_days,
    )
    return report


def _apply_adjustments(
    boq: BillOfQuantities,
    catalog: list[Concept],
    apus: dict[str, UnitPriceAnalysis],
    adjustments: list[ManualAdjustment],
) -> None:
    """Concept-level human corrections, applied before integration so every
    downstream figure (indirects, schedule, cashflow) stays consistent."""
    concepts_by_code = {concept.code: concept for concept in catalog}
    catalog_order = {concept.code: index for index, concept in enumerate(catalog)}
    lines_by_code = {line.concept_code: line for line in boq.lines}

    for adjustment in adjustments:
        concept = concepts_by_code.get(adjustment.concept_code)
        if concept is None:
            boq.warnings.append(
                f"Ajuste manual ignorado: concepto desconocido {adjustment.concept_code}."
            )
            continue
        note = f"Ajuste manual {adjustment.quantity_delta:+,.2f} {concept.unit}"
        if adjustment.note:
            note += f": {adjustment.note}"
        if adjustment.actor:
            note += f" — {adjustment.actor}"

        line = lines_by_code.get(adjustment.concept_code)
        if line is None:
            if adjustment.quantity_delta <= 0:
                boq.warnings.append(
                    "Ajuste manual negativo ignorado: el concepto "
                    f"{adjustment.concept_code} no tiene cantidad detectada."
                )
                continue
            apu = apus.get(adjustment.concept_code)
            if apu is None:
                boq.warnings.append(
                    f"Ajuste manual en {adjustment.concept_code} ignorado: el "
                    "concepto no tiene matriz de APU y no puede tener precio."
                )
                continue
            line = BoqLine(
                concept_code=concept.code,
                description=concept.description,
                unit=concept.unit,
                quantity=0.0,
                unit_price=apu.direct_unit_cost,
                amount=0.0,
                phase=concept.phase,
                raw_quantity=0.0,
                raw_kind=QuantityKind.COUNT,
                source_detection_count=0,
                confidence=1.0,
            )
            boq.lines.append(line)
            lines_by_code[concept.code] = line

        new_quantity = line.quantity + adjustment.quantity_delta
        if new_quantity < 0:
            boq.warnings.append(
                f"Ajuste manual en {concept.code} limitado a cantidad cero "
                f"(pedía {new_quantity:,.2f} {concept.unit})."
            )
            new_quantity = 0.0
        line.quantity = round(new_quantity, 4)
        line.amount = round(line.quantity * line.unit_price, 2)
        line.assumptions.append(note)

    boq.lines.sort(
        key=lambda line: (
            PHASE_ORDER.index(line.phase) if line.phase in PHASE_ORDER else len(PHASE_ORDER),
            catalog_order.get(line.concept_code, len(catalog_order)),
        )
    )
    boq.direct_cost_total = round(sum(line.amount for line in boq.lines), 2)
    totals: dict[str, float] = {}
    for line in boq.lines:
        totals[line.phase] = round(totals.get(line.phase, 0.0) + line.amount, 2)
    boq.totals_by_phase = totals


def _money(value: float) -> str:
    return f"${value:,.2f}"


def boq_to_csv(report: CostReport, path: Path) -> Path:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["clave", "concepto", "unidad", "cantidad", "p_unitario_cd", "importe_cd",
         "fase", "confianza", "detecciones_origen"]
    )
    for line in report.boq.lines:
        writer.writerow(
            [line.concept_code, line.description, line.unit, line.quantity,
             line.unit_price, line.amount, line.phase, line.confidence,
             line.source_detection_count]
        )
    writer.writerow([])
    writer.writerow(["", "COSTO DIRECTO TOTAL", "", "", "", report.boq.direct_cost_total])
    for integration_line in report.integration.lines:
        writer.writerow(
            ["", integration_line.description, f"{integration_line.percentage}%",
             "", "", integration_line.amount]
        )
    writer.writerow(["", "PRECIO DE VENTA", "", "", "", report.integration.sale_price])
    writer.writerow(["", "CONTINGENCIA", "", "", "", report.integration.contingency])
    writer.writerow(["", "TOTAL", "", "", "", report.integration.grand_total])
    return write_text(path, buffer.getvalue())


def cost_report_to_markdown(report: CostReport) -> str:
    integration = report.integration
    months = len(report.financial.periods)
    lines = [
        "# Resumen Ejecutivo de Costos",
        "",
        f"Proyecto: `{report.project_id}` — Moneda: {report.currency}",
        f"Unidades del plano: **{report.drawing_units.unit}** "
        f"({report.drawing_units.source}, confianza {report.drawing_units.confidence:.0%})",
        "",
        "## Presupuesto",
        "",
        "| Clave | Concepto | Unidad | Cantidad | P.U. (CD) | Importe |",
        "|---|---|---|---|---|---|",
    ]
    for line in report.boq.lines:
        lines.append(
            f"| {line.concept_code} | {line.description} | {line.unit} "
            f"| {line.quantity:,.2f} | {_money(line.unit_price)} | {_money(line.amount)} |"
        )
    lines += [
        "",
        "## Integración del precio",
        "",
        f"- Costo directo: **{_money(integration.direct_cost)}**",
    ]
    for integration_line in integration.lines:
        lines.append(
            f"- {integration_line.description} ({integration_line.percentage}%): "
            f"{_money(integration_line.amount)}"
        )
    lines += [
        f"- Precio de venta: **{_money(integration.sale_price)}** "
        f"(factor de sobrecosto {integration.overcost_factor:.4f})",
        f"- Contingencia: {_money(integration.contingency)}",
        f"- **Total con contingencia: {_money(integration.grand_total)}**",
        "",
        "## Programa y finanzas",
        "",
        f"- Duración estimada: {report.schedule.total_duration_days} días hábiles "
        f"(~{months} meses)",
        f"- Anticipo ({report.financial.advance_payment_pct:.0f}%): "
        f"{_money(report.financial.advance_payment)}",
        f"- Retenciones acumuladas ({report.financial.retention_pct:.0f}%): "
        f"{_money(report.financial.total_retention)}",
        f"- Costo anual de operación y mantenimiento: "
        f"{_money(report.financial.annual_operating_cost)}",
        "",
        "## Supuestos y advertencias",
        "",
    ]
    for assumption in report.boq.assumptions:
        lines.append(f"- {assumption}")
    for boq_line in report.boq.lines:
        for assumption in boq_line.assumptions:
            lines.append(f"- [{boq_line.concept_code}] {assumption}")
    for warning in report.warnings:
        lines.append(f"- ⚠️ {warning}")
    return "\n".join(lines) + "\n"
