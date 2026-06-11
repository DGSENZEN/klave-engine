"""Cost report assembly: the full workflow in one artifact, plus exports."""

import csv
import io
from pathlib import Path

from klave_engine.common.io import write_text
from klave_engine.common.logging import get_logger, log_stage
from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.boq import generate_bill_of_quantities
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.financial import build_financial_plan
from klave_engine.costing.integration import integrate_costs
from klave_engine.costing.models import CostingConfig, CostReport
from klave_engine.costing.schedule import build_schedule
from klave_engine.detection.results import Detection
from klave_engine.dxf.units import DrawingUnits

logger = get_logger(__name__)


def generate_cost_report(
    project_id: str,
    detections: list[Detection],
    units: DrawingUnits,
    config: CostingConfig | None = None,
) -> CostReport:
    config = config or CostingConfig()
    catalog = build_default_catalog(config.assumptions)
    apus = build_all_apus(catalog)
    boq = generate_bill_of_quantities(
        project_id, detections, units, catalog, apus, config.currency
    )
    integration = integrate_costs(boq.direct_cost_total, config.indirects)
    schedule = build_schedule(boq, catalog, config.schedule)
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
