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
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XlsxImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from klave_engine.costing.letras import pesos_con_letra
from klave_engine.costing.models import BoqLine, CostReport
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


CroquisProvider = Callable[[BoqLine], list[tuple[str, Path]]]


def build_presupuesto_workbook(
    report: CostReport,
    detections: list[Detection],
    reviews: ProjectReviews,
    project_name: str,
    client: str | None,
    fmt: str = "klave",
    inventory: dict | None = None,
    croquis: CroquisProvider | None = None,
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
    elif fmt == "licitacion":
        workbook = _licitacion_workbook(report, reviews, project_name, client)
    else:
        workbook = _klave_workbook(report, detections, reviews, project_name, client)
        if inventory and inventory.get("sheets"):
            _levantamiento(workbook.create_sheet("Levantamiento"), inventory)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ------------------------------------------------------------------ flat ---

IVA_PCT = 16.0


def _licitacion_workbook(
    report: CostReport, reviews: ProjectReviews, project_name: str, client: str | None
) -> Workbook:
    """Catálogo de conceptos for a licitación pública (LOPSRM art. 45 / RLOPSRM
    art. 185): one partida per phase, each concept with its precio unitario
    con número y con letra, importe, subtotal, IVA and total con letra. The
    P.U. is the precio de venta (costo directo × factor de sobrecosto), the
    one a contractor signs — never the bare costo directo."""
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Catálogo de conceptos"
    factor = report.integration.overcost_factor or 1.0
    _title(ws, 1, "CATÁLOGO DE CONCEPTOS Y CANTIDADES DE OBRA", size=14)
    _muted(ws, 2, 1, f"Obra: {project_name}")
    _muted(ws, 3, 1, f"Dependencia / cliente: {client or '—'}")
    _muted(
        ws, 4, 1,
        f"Fecha: {datetime.now(UTC):%d/%m/%Y} · Moneda: {report.currency} · "
        f"Precios unitarios con indirectos, financiamiento, utilidad y cargos adicionales "
        f"(factor {factor:.4f} sobre costo directo)",
    )
    verification = reviews.verification
    if not (verification.units_confirmed_at and verification.detections_confirmed_at):
        cell = ws.cell(
            row=5, column=1,
            value="SIN VERIFICAR — cantidades leídas del plano, pendientes de revisión humana",
        )
        cell.font = Font(bold=True, size=9, color="B54708")
    columns = [
        "Partida", "Clave", "Concepto", "Unidad", "Cantidad",
        "P.U. con número", "P.U. con letra", "Importe",
    ]
    _header(ws, 7, columns)
    row = 8
    subtotal = 0.0
    for number, (phase, _phase_total) in enumerate(report.boq.totals_by_phase.items(), 1):
        partida = f"{number:02d}"
        phase_cell = ws.cell(row=row, column=1, value=partida)
        phase_cell.font = Font(bold=True, size=9)
        name_cell = ws.cell(row=row, column=3, value=phase.upper())
        name_cell.font = Font(bold=True, size=9)
        for col in range(1, 9):
            ws.cell(row=row, column=col).fill = PatternFill("solid", fgColor=SOFT)
        row += 1
        partida_total = 0.0
        for index, line in enumerate(
            (ln for ln in report.boq.lines if ln.phase == phase), 1
        ):
            unit_price = round(line.unit_price * factor, 2)
            amount = round(line.quantity * unit_price, 2)
            partida_total += amount
            values: list[Any] = [
                f"{partida}.{index:03d}", line.taller_clave or line.concept_code,
                line.description, line.unit, line.quantity, unit_price,
                pesos_con_letra(unit_price), amount,
            ]
            for col, value in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col, value=value)
                cell.border = _box
                if col == 5:
                    cell.number_format = QTY_FORMAT
                if col in (6, 8):
                    cell.number_format = MONEY_FORMAT
                if col in (3, 7):
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
            row += 1
        total_cell = ws.cell(row=row, column=3, value=f"Subtotal partida {partida}")
        total_cell.font = Font(italic=True, size=9, color=MUTED)
        amount_cell = ws.cell(row=row, column=8, value=round(partida_total, 2))
        amount_cell.number_format = MONEY_FORMAT
        amount_cell.font = Font(italic=True, size=9, color=MUTED)
        subtotal += partida_total
        row += 2
    iva = round(subtotal * IVA_PCT / 100, 2)
    total = round(subtotal + iva, 2)
    for label, value in (
        ("SUBTOTAL", round(subtotal, 2)),
        (f"I.V.A. {IVA_PCT:.0f} %", iva),
        ("TOTAL", total),
    ):
        label_cell = ws.cell(row=row, column=3, value=label)
        label_cell.font = Font(bold=True, size=10)
        value_cell = ws.cell(row=row, column=8, value=value)
        value_cell.number_format = MONEY_FORMAT
        value_cell.font = Font(bold=True, size=10)
        row += 1
    letra = ws.cell(row=row, column=3, value=f"Importe total con letra: {pesos_con_letra(total)}")
    letra.font = Font(bold=True, size=9)
    row += 2
    _muted(
        ws, row, 1,
        "Las cantidades provienen de la lectura del plano y de las correcciones documentadas "
        "(hoja Generadores del Excel completo); los precios son los del catálogo del taller.",
    )
    widths = {"A": 9, "B": 11, "C": 58, "D": 8, "E": 12, "F": 15, "G": 52, "H": 16}
    for letter, width in widths.items():
        ws.column_dimensions[letter].width = width
    return workbook


def _flat_workbook(report: CostReport, sheet_title: str, columns: list[str]) -> Workbook:
    """One row per concept, no merges: made for import wizards."""
    workbook = Workbook()
    ws = workbook.active
    ws.title = sheet_title
    _header(ws, 1, columns)
    row = 2
    for line in report.boq.lines:
        values: list[Any] = [
            line.taller_clave or line.concept_code,
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
    croquis: CroquisProvider | None = None,
) -> Workbook:
    workbook = Workbook()
    _caratula(workbook.active, report, reviews, project_name, client)
    _presupuesto(workbook.create_sheet("Presupuesto"), report)
    _apus(workbook.create_sheet("APUs"), report)
    _generadores(workbook.create_sheet("Generadores"), report, detections, reviews, croquis)
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
    columns = ["Clave", "Concepto", "Unidad", "Cantidad", "P.U. (CD)", "Importe", "Confianza"]
    _header(ws, 1, [*columns, "Por nivel"])
    row = 2
    for phase, phase_total in report.boq.totals_by_phase.items():
        phase_cell = ws.cell(row=row, column=1, value=phase.upper())
        phase_cell.font = Font(bold=True, size=9, color=MUTED)
        phase_cell.fill = PatternFill("solid", fgColor=SOFT)
        for col in range(2, 9):
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
                line.taller_clave or line.concept_code, line.description, line.unit,
                line.quantity, line.unit_price, line.amount,
                f"{line.confidence:.0%}",
                "; ".join(f"{title}: {qty:,.2f}" for title, qty in line.by_view.items()),
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
    _autosize(ws, [12, 62, 9, 13, 14, 16, 11, 48])
    ws.freeze_panes = "A2"


def _apus(ws: Worksheet, report: CostReport) -> None:
    row = 1
    for apu in report.apus:
        _title(ws, row, f"{apu.concept_code} — {apu.concept_description}", size=11)
        _muted(ws, row + 1, 1, f"Costo directo por {apu.unit}")
        row += 2
        _header(ws, row, ["Recurso", "Descripción", "Unidad", "Cantidad", "Costo", "Importe"])
        row += 1
        if apu.price_source:
            _muted(ws, row, 1, f"P.U. adoptado de {apu.price_source} (sin matriz)")
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


CROQUIS_WIDTH_PX = 520
ROW_PX = 20


def _croquis_rows(ws: Worksheet, row: int, items: list[tuple[str, Path]]) -> int:
    """Each croquis below its concept, captioned with its planta."""
    for title, path in items:
        try:
            image = XlsxImage(str(path))
        except OSError:
            continue
        ratio = CROQUIS_WIDTH_PX / max(image.width, 1)
        image.width, image.height = CROQUIS_WIDTH_PX, int(image.height * ratio)
        _muted(ws, row, 1, f"Croquis · {title}")
        row += 1
        ws.add_image(image, f"A{row}")
        row += int(image.height / ROW_PX) + 2
    return row


def _generadores(
    ws: Worksheet,
    report: CostReport,
    detections: list[Detection],
    reviews: ProjectReviews,
    croquis: CroquisProvider | None = None,
) -> None:
    """The evidence backup sheet: where every quantity comes from — and,
    with a croquis provider, where on the planta it sits."""
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
        # Provenance that is not a detection: mapped levantamiento counts,
        # adopted prices, and the per-planta split.
        for assumption in line.assumptions:
            if assumption.startswith(("Levantamiento:", "P.U. adoptado")):
                cell = ws.cell(row=row, column=1, value=assumption)
                cell.font = Font(italic=True, size=9, color=MUTED)
                row += 1
        if line.by_view:
            split = "; ".join(
                f"{title}: {qty:,.2f} {line.unit}" for title, qty in line.by_view.items()
            )
            cell = ws.cell(row=row, column=1, value=f"Por planta: {split}")
            cell.font = Font(italic=True, size=9, color=MUTED)
            row += 1
        for adjustment in reviews.adjustments:
            if adjustment.concept_code != line.concept_code:
                continue
            if adjustment.quantity_set is not None:
                note = f"CANTIDAD FIJADA EN {adjustment.quantity_set:,.2f} {line.unit}"
                if line.engine_quantity is not None:
                    note += f" (lectura: {line.engine_quantity:,.2f} {line.unit})"
            else:
                note = f"AJUSTE MANUAL {adjustment.quantity_delta:+,.2f} {line.unit}"
            if adjustment.note:
                note += f" — {adjustment.note}"
            if adjustment.actor:
                note += f" ({adjustment.actor})"
            cell = ws.cell(row=row, column=1, value=note)
            cell.font = Font(italic=True, size=9, color="B54708")
            row += 1
        if croquis is not None and line.source_detections:
            row = _croquis_rows(ws, row, croquis(line))
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


def _levantamiento(ws: Worksheet, inventory: dict) -> None:
    """Symbols, tags and runs per sheet: the count behind every mapped line
    and the backlog of what is still unmapped."""
    _header(ws, 1, ["Hoja", "Disciplina", "Tipo", "Elemento", "Capa", "Cantidad", "Unidad",
                    "Por planta"])
    row = 2
    unit = inventory.get("unit") or "u. dib."
    for sheet in inventory.get("sheets") or []:
        label = sheet.get("label") or sheet.get("sheet", "")
        discipline = sheet.get("discipline") or ""
        entries: list[list[Any]] = []
        for block in sheet.get("blocks") or []:
            entries.append(["Símbolo", block["block_name"], block.get("layer", ""),
                            block["count"], "PZA", block.get("by_view") or {}])
        for tag in sheet.get("tags") or []:
            entries.append(["Etiqueta", tag["tag"], "", tag["count"], "PZA",
                            tag.get("by_view") or {}])
        for region in sheet.get("areas") or []:
            area = region.get("area_m2")
            entries.append(["Área", region["layer"], region["layer"],
                            area if area is not None else region.get("area_du2", 0.0),
                            "M2" if area is not None else f"{unit}²", region.get("by_view") or {}])
        for run in sheet.get("runs") or []:
            length = run.get("length_m")
            entries.append(["Trazo", run["layer"], run["layer"],
                            length if length is not None else run.get("length_du", 0.0),
                            "M" if length is not None else unit, run.get("by_view") or {}])
        for kind, element, layer, quantity, qty_unit, by_view in entries:
            split = "; ".join(f"{title}: {qty:,.2f}" for title, qty in by_view.items())
            values: list[Any] = [label, discipline, kind, element, layer, quantity, qty_unit, split]
            for col, value in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col, value=value)
                cell.border = _box
                if col == 6:
                    cell.number_format = QTY_FORMAT
            row += 1
    row += 1
    for note in inventory.get("notes") or []:
        _muted(ws, row, 1, note)
        row += 1
    _autosize(ws, [34, 14, 10, 34, 24, 12, 8, 48])
    ws.freeze_panes = "A2"


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
