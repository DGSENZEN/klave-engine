"""Deliverable exports: the documents an estimator actually hands over.

Builds XLSX workbooks from the persisted artifacts:

- ``klave``: carátula, presupuesto formateado, hojas de APU, números
  generadores (the per-concept evidence backup: every detection that produced
  the quantity, plus manual adjustments with note and author), programa y
  flujo. The generadores sheet is the differentiator — it is generated from
  the evidence chain, not typed by hand.
- ``opus`` / ``neodata``: flat, import-wizard-friendly layouts using each
  suite's conventional column order. Both tools import from Excel through a
  column-mapping wizard; these exports keep one row per concept with no
  merged cells so that mapping is trivial.
"""

import io
from datetime import UTC, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from klave_engine.costing.models import CostReport
from klave_engine.costing.reviews import ProjectReviews
from klave_engine.detection.results import Detection

INK = "18181B"
MUTED = "6E6E76"
BORDER_COLOR = "D2D2D7"
SOFT = "F2F2F3"

MONEY_FORMAT = '"$"#,##0.00'
QTY_FORMAT = "#,##0.00"

_thin = Side(style="thin", color=BORDER_COLOR)
_box = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)

RAW_KIND_LABELS = {
    "count": "conteo (pza)",
    "length": "longitud (m)",
    "area": "área (m²)",
}

KIND_PROPERTY = {
    "length": ("estimated_span_length", "estimated_length"),
    "area": ("estimated_area",),
}


def _header(ws: Worksheet, row: int, values: list[str]) -> None:
    for col, value in enumerate(values, start=1):
        cell = ws.cell(row=row, column=col, value=value)
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.fill = PatternFill("solid", fgColor=INK)
        cell.alignment = Alignment(vertical="center")
        cell.border = _box


def _autosize(ws: Worksheet, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width


def _title(ws: Worksheet, row: int, text: str, size: int = 12) -> None:
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = Font(bold=True, size=size, color=INK)


def _muted(ws: Worksheet, row: int, col: int, text: str) -> None:
    cell = ws.cell(row=row, column=col, value=text)
    cell.font = Font(size=9, color=MUTED)


def build_presupuesto_workbook(
    report: CostReport,
    detections: list[Detection],
    reviews: ProjectReviews,
    project_name: str,
    client: str | None,
    fmt: str = "klave",
) -> bytes:
    if fmt == "opus":
        workbook = _flat_workbook(
            report,
            sheet_title="Presupuesto",
            columns=["Clave", "Descripción", "Unidad", "Cantidad", "Precio Unitario", "Importe"],
        )
    elif fmt == "neodata":
        workbook = _flat_workbook(
            report,
            sheet_title="Presupuesto",
            columns=["Código", "Concepto", "Unidad", "Cantidad", "P.U.", "Monto"],
        )
    else:
        workbook = _klave_workbook(report, detections, reviews, project_name, client)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ------------------------------------------------------------------ flat ---

def _flat_workbook(report: CostReport, sheet_title: str, columns: list[str]) -> Workbook:
    """One row per concept, no merges: made for import wizards."""
    workbook = Workbook()
    ws = workbook.active
    ws.title = sheet_title
    _header(ws, 1, columns)
    row = 2
    for line in report.boq.lines:
        values: list[Any] = [
            line.concept_code,
            line.description,
            line.unit,
            line.quantity,
            line.unit_price,
            line.amount,
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.border = _box
            if col == 4:
                cell.number_format = QTY_FORMAT
            if col in (5, 6):
                cell.number_format = MONEY_FORMAT
        row += 1
    _autosize(ws, [14, 64, 10, 14, 16, 18])
    ws.freeze_panes = "A2"
    return workbook


# ----------------------------------------------------------------- klave ---

def _klave_workbook(
    report: CostReport,
    detections: list[Detection],
    reviews: ProjectReviews,
    project_name: str,
    client: str | None,
) -> Workbook:
    workbook = Workbook()
    _caratula(workbook.active, report, reviews, project_name, client)
    _presupuesto(workbook.create_sheet("Presupuesto"), report)
    _apus(workbook.create_sheet("APUs"), report)
    _generadores(workbook.create_sheet("Generadores"), report, detections, reviews)
    _programa(workbook.create_sheet("Programa"), report)
    _flujo(workbook.create_sheet("Flujo"), report)
    return workbook


def _caratula(
    ws: Worksheet,
    report: CostReport,
    reviews: ProjectReviews,
    project_name: str,
    client: str | None,
) -> None:
    ws.title = "Carátula"
    _title(ws, 1, "Presupuesto de obra — Klave", size=16)
    _muted(ws, 2, 1, "Ingeniería de costos con evidencia inspeccionable")

    verification = reviews.verification
    verified = bool(
        verification.units_confirmed_at
        and verification.detections_confirmed_at
        and verification.assumptions_confirmed_at
    )
    rows = [
        ("Proyecto", project_name),
        ("Cliente", client or "—"),
        ("Fecha de emisión", datetime.now(UTC).strftime("%Y-%m-%d")),
        ("Moneda", report.currency),
        ("Unidades del plano", f"{report.drawing_units.unit} "
         f"({report.drawing_units.confidence:.0%} de confianza)"),
        ("Verificación", "Verificado (unidades, detecciones y supuestos)"
         if verified else "SIN VERIFICAR — revisar antes de usar"),
        ("", ""),
        ("Costo directo", report.boq.direct_cost_total),
        ("Precio de venta", report.integration.sale_price),
        ("Contingencia", report.integration.contingency),
        ("Total con contingencia", report.integration.grand_total),
        ("Plazo estimado", f"{report.schedule.total_duration_days} días hábiles"),
    ]
    for offset, (label, value) in enumerate(rows, start=4):
        label_cell = ws.cell(row=offset, column=1, value=label)
        label_cell.font = Font(bold=True, size=10, color=MUTED)
        value_cell = ws.cell(row=offset, column=2, value=value)
        if isinstance(value, float):
            value_cell.number_format = MONEY_FORMAT
        if label == "Verificación" and not verified:
            value_cell.font = Font(bold=True, color="B54708")
    _muted(
        ws, len(rows) + 5, 1,
        "Precios de referencia salvo indicación contraria; ver la fuente de cada "
        "insumo en el catálogo del taller.",
    )
    _autosize(ws, [26, 46])


def _presupuesto(ws: Worksheet, report: CostReport) -> None:
    _header(ws, 1, ["Clave", "Concepto", "Unidad", "Cantidad", "P.U. (CD)", "Importe", "Confianza"])
    row = 2
    for phase, phase_total in report.boq.totals_by_phase.items():
        phase_cell = ws.cell(row=row, column=1, value=phase.upper())
        phase_cell.font = Font(bold=True, size=9, color=MUTED)
        phase_cell.fill = PatternFill("solid", fgColor=SOFT)
        for col in range(2, 8):
            ws.cell(row=row, column=col).fill = PatternFill("solid", fgColor=SOFT)
        total_cell = ws.cell(row=row, column=6, value=phase_total)
        total_cell.number_format = MONEY_FORMAT
        total_cell.font = Font(bold=True, size=9, color=MUTED)
        total_cell.fill = PatternFill("solid", fgColor=SOFT)
        row += 1
        for line in report.boq.lines:
            if line.phase != phase:
                continue
            values: list[Any] = [
                line.concept_code, line.description, line.unit,
                line.quantity, line.unit_price, line.amount,
                f"{line.confidence:.0%}",
            ]
            for col, value in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col, value=value)
                cell.border = _box
                if col == 4:
                    cell.number_format = QTY_FORMAT
                if col in (5, 6):
                    cell.number_format = MONEY_FORMAT
            row += 1
    row += 1
    summary = [
        ("Costo directo", report.boq.direct_cost_total),
        *((line.description + f" ({line.percentage}%)", line.amount)
          for line in report.integration.lines),
        ("Precio de venta", report.integration.sale_price),
        ("Contingencia", report.integration.contingency),
        ("TOTAL", report.integration.grand_total),
    ]
    for label, amount in summary:
        font = Font(bold=label in ("Costo directo", "Precio de venta", "TOTAL"))
        label_cell = ws.cell(row=row, column=5, value=label)
        label_cell.font = font
        amount_cell = ws.cell(row=row, column=6, value=amount)
        amount_cell.number_format = MONEY_FORMAT
        amount_cell.font = font
        row += 1
    _autosize(ws, [12, 62, 9, 13, 14, 16, 11])
    ws.freeze_panes = "A2"


def _apus(ws: Worksheet, report: CostReport) -> None:
    row = 1
    for apu in report.apus:
        _title(ws, row, f"{apu.concept_code} — {apu.concept_description}", size=11)
        _muted(ws, row + 1, 1, f"Costo directo por {apu.unit}")
        row += 2
        _header(ws, row, ["Recurso", "Descripción", "Unidad", "Cantidad", "Costo", "Importe"])
        row += 1
        for line in apu.lines:
            values: list[Any] = [
                line.resource_code, line.description, line.unit,
                line.quantity, line.unit_cost, line.amount,
            ]
            for col, value in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col, value=value)
                cell.border = _box
                if col == 4:
                    cell.number_format = "#,##0.0000"
                if col in (5, 6):
                    cell.number_format = MONEY_FORMAT
            row += 1
        total_label = ws.cell(row=row, column=5, value="CD unitario")
        total_label.font = Font(bold=True)
        total_cell = ws.cell(row=row, column=6, value=apu.direct_unit_cost)
        total_cell.number_format = MONEY_FORMAT
        total_cell.font = Font(bold=True)
        row += 3
    _autosize(ws, [16, 52, 9, 12, 13, 15])


def _generadores(
    ws: Worksheet,
    report: CostReport,
    detections: list[Detection],
    reviews: ProjectReviews,
) -> None:
    """The evidence backup sheet: where every quantity comes from."""
    by_id = {d.detection_id: d for d in detections}
    row = 1
    _title(ws, row, "Números generadores", size=13)
    _muted(
        ws, row + 1, 1,
        "Respaldo de cantidades: cada renglón es una detección del plano o un "
        "ajuste manual documentado.",
    )
    row += 3
    for line in report.boq.lines:
        _title(ws, row, f"{line.concept_code} — {line.description}", size=11)
        row += 1
        _muted(
            ws, row, 1,
            f"Base medida: {line.raw_quantity:,.2f} "
            f"{RAW_KIND_LABELS.get(line.raw_kind.value, line.raw_kind.value)} → "
            f"cantidad: {line.quantity:,.2f} {line.unit} · "
            f"confianza {line.confidence:.0%}",
        )
        row += 1
        _header(
            ws, row,
            ["Elemento", "Marca en plano", "Familia", "Hoja", "Medida base", "Confianza"],
        )
        row += 1
        for detection_id in line.source_detections:
            detection = by_id.get(detection_id)
            if detection is None:
                continue
            measure: Any = 1
            for prop in KIND_PROPERTY.get(line.raw_kind.value, ()):
                if detection.properties.get(prop) is not None:
                    measure = round(float(detection.properties[prop]), 3)
                    break
            values: list[Any] = [
                detection.display_label or detection.label,
                detection.mark or "—",
                detection.family_label or detection.detection_type.value,
                detection.evidence.source,
                measure,
                f"{detection.confidence:.0%}",
            ]
            for col, value in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col, value=value)
                cell.border = _box
                if col == 5 and isinstance(value, float):
                    cell.number_format = QTY_FORMAT
            row += 1
        for adjustment in reviews.adjustments:
            if adjustment.concept_code != line.concept_code:
                continue
            note = f"AJUSTE MANUAL {adjustment.quantity_delta:+,.2f} {line.unit}"
            if adjustment.note:
                note += f" — {adjustment.note}"
            if adjustment.actor:
                note += f" ({adjustment.actor})"
            cell = ws.cell(row=row, column=1, value=note)
            cell.font = Font(italic=True, size=9, color="B54708")
            row += 1
        row += 1
    excluded_summary = [
        (key, review)
        for key, review in reviews.detections.items()
        if review.status == "excluded"
    ]
    if excluded_summary:
        _title(ws, row, "Elementos excluidos por revisión humana", size=11)
        row += 1
        for key, review in excluded_summary:
            note = f"{key}"
            if review.note:
                note += f" — {review.note}"
            if review.actor:
                note += f" ({review.actor})"
            _muted(ws, row, 1, note)
            row += 1
    _autosize(ws, [18, 16, 18, 26, 14, 11])


def _programa(ws: Worksheet, report: CostReport) -> None:
    _header(ws, 1, ["Clave", "Actividad", "Fase", "Cantidad", "Unidad",
                    "Rendimiento/día", "Días", "Inicio", "Término"])
    row = 2
    for activity in report.schedule.activities:
        values: list[Any] = [
            activity.concept_code, activity.description, activity.phase,
            activity.quantity, activity.unit, activity.rendimiento_per_day,
            activity.duration_days, activity.start_day, activity.end_day,
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.border = _box
            if col == 4:
                cell.number_format = QTY_FORMAT
        row += 1
    ws.cell(row=row + 1, column=2, value="Duración total (días hábiles)").font = Font(bold=True)
    ws.cell(row=row + 1, column=7, value=report.schedule.total_duration_days).font = Font(bold=True)
    _autosize(ws, [12, 52, 14, 12, 9, 15, 8, 8, 9])
    ws.freeze_panes = "A2"


def _flujo(ws: Worksheet, report: CostReport) -> None:
    _header(ws, 1, ["Periodo", "Avance %", "Gasto directo", "Estimación",
                    "Amort. anticipo", "Retención", "Flujo neto", "Fact. acumulada"])
    row = 2
    for period in report.financial.periods:
        values: list[Any] = [
            period.label, period.progress_pct, period.direct_spend, period.billing,
            period.advance_amortization, period.retention, period.net_cashflow,
            period.accumulated_billing,
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.border = _box
            if col == 2:
                cell.number_format = "0.0"
            if col >= 3:
                cell.number_format = MONEY_FORMAT
        row += 1
    _autosize(ws, [12, 10, 16, 16, 16, 14, 16, 17])
    ws.freeze_panes = "A2"
