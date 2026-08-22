"""Cimbra (m²) and declared concrete strengths, from the counted elements.

Formwork is contact area: castillos and columnas by perimeter × height,
trabes by (b + 2h) × span, dalas by 2h × length, zapatas by perimeter ×
peralte, and slabs only when they are maciza — a vigueta y bovedilla slab
has no contact formwork, only shoring, and the stage says so instead of
charging it. Sections come from the sheet's specs where declared, else from
the project's assumptions, and every line says which.

The same stage compares the f'c the sheet declares per element with the
f'c the concept is priced at, and warns when they differ: the catalog
prices a specific concrete, and silently relabelling it would be a lie.
"""

import math
import re

from pydantic import BaseModel, Field

from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    CostingAssumptions,
    QuantityKind,
)
from klave_engine.detection.dimensions import DimensionInventory
from klave_engine.detection.results import Detection

CODE_ZAPATAS = "CIM-006"
CODE_CASTILLOS = "EST-008"
CODE_TRABES = "EST-009"
CODE_DALAS = "EST-010"
CODE_LOSA = "EST-011"

# Concept → element family whose declared f'c applies.
_FC_FAMILY_BY_CONCEPT = {
    "CIM-002": "cimentacion", "EST-001": "castillo", "EST-002": "trabe", "EST-003": "losa",
    "EST-005": "dala", "EST-006": "castillo", "EST-007": "firme", "CIM-003": "cimentacion",
}
_FC_IN_TEXT = re.compile(r"f\s*'?\s*c\s*=?\s*(\d{3})", re.I)
_MIN_SECTION_M2, _MAX_SECTION_M2 = 0.0100, 1.44  # 10×10 cm … 120×120 cm
_CASTILLO_DEFAULT_M = (0.15, 0.20)


class FormworkLine(BaseModel):
    concept_code: str
    quantity: float
    unit: str = "M2"
    source_detections: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FormworkReport(BaseModel):
    lines: list[FormworkLine] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _section_m(props: dict, specs: dict | None, mark: str, family: str,
               default_m: tuple[float, float], factor: float) -> tuple[tuple[float, float], str]:
    declared = props.get("section_cm")
    if isinstance(declared, str) and "x" in declared:
        a, b = (int(v) for v in declared.split("x"))
        return (a / 100.0, b / 100.0), "plano"
    if specs:
        spec = (specs.get("by_mark") or {}).get(mark.upper()) or (
            specs.get("by_family") or {}
        ).get(family)
        if spec and spec.get("section_cm"):
            a, b = spec["section_cm"]
            return (a / 100.0, b / 100.0), "plano"
    area_du2 = props.get("section_area_du2")
    if isinstance(area_du2, (int, float)) and area_du2 > 0:
        area_m2 = float(area_du2) * factor * factor
        # Same plausibility window the BoQ uses: a marker outside it was a
        # bubble or a grid circle, not the section.
        if _MIN_SECTION_M2 <= area_m2 <= _MAX_SECTION_M2:
            side = math.sqrt(area_m2)
            return (side, side), "marcador"
    return default_m, "supuesto"


def compute_formwork(
    boq: BillOfQuantities,
    detections: list[Detection],
    specs: dict | None,
    dimensions: DimensionInventory | None,
    assumptions: CostingAssumptions,
    meters_factor: float | None,
    total_height_m: float | None,
) -> FormworkReport:
    report = FormworkReport()
    factor = meters_factor or 1.0
    by_id = {d.detection_id: d for d in detections}
    lines = {line.concept_code: line for line in boq.lines}
    height = total_height_m or assumptions.column_height_m
    col_side = math.sqrt(assumptions.column_section_m2)
    beam_b, beam_h = 0.25, assumptions.beam_section_m2 / 0.25

    columns = lines.get("EST-001")
    if columns is not None and columns.source_detections:
        area = 0.0
        origins: dict[str, int] = {}
        for det_id in columns.source_detections:
            det = by_id.get(det_id)
            if det is None:
                continue
            family = "castillo" if det.label.strip().upper().startswith("K") else "columna"
            default = _CASTILLO_DEFAULT_M if family == "castillo" else (col_side, col_side)
            (a, b), origin = _section_m(det.properties, specs, det.label, family, default, factor)
            origins[origin] = origins.get(origin, 0) + 1
            area += 2 * (a + b) * height
        report.lines.append(
            FormworkLine(
                concept_code=CODE_CASTILLOS, quantity=round(area, 2),
                source_detections=list(columns.source_detections),
                notes=[
                    f"Perímetro de sección × {height:.2f} m en {len(columns.source_detections)} "
                    "castillos/columnas",
                    "Sección por: " + ", ".join(f"{k} {v}" for k, v in origins.items()),
                ],
            )
        )

    beams = lines.get("EST-002")
    if beams is not None and beams.source_detections:
        area = 0.0
        counted = 0
        for det_id in beams.source_detections:
            det = by_id.get(det_id)
            if det is None:
                continue
            span = float(det.properties.get("estimated_span_length") or 0.0) * factor
            if span <= 0:
                continue
            (b, h), _origin = _section_m(
                det.properties, specs, det.label, "trabe", (beam_b, beam_h), factor
            )
            area += (b + 2 * h) * span
            counted += 1
        if counted:
            report.lines.append(
                FormworkLine(
                    concept_code=CODE_TRABES, quantity=round(area, 2),
                    source_detections=list(beams.source_detections),
                    notes=[f"(b + 2h) × claro en {counted} trabes; sección del plano o supuesta "
                           f"{beam_b:.2f}×{beam_h:.2f} m"],
                )
            )

    walls = lines.get("EST-004")
    if walls is not None and walls.raw_quantity > 0:
        dala_h = 0.20
        if specs and (specs.get("by_family") or {}).get("dala", {}).get("section_cm"):
            dala_h = specs["by_family"]["dala"]["section_cm"][1] / 100.0
        report.lines.append(
            FormworkLine(
                concept_code=CODE_DALAS, quantity=round(2 * dala_h * walls.raw_quantity, 2),
                source_detections=list(walls.source_detections),
                notes=[
                    f"2 caras × {dala_h:.2f} m de peralte × {walls.raw_quantity:,.1f} m de dala"
                ],
            )
        )

    footings = lines.get("CIM-002")
    if footings is not None and footings.source_detections:
        area = 0.0
        for det_id in footings.source_detections:
            det = by_id.get(det_id)
            if det is None:
                continue
            props = det.properties
            if props.get("dimensioned_width") and props.get("dimensioned_length"):
                w = float(props["dimensioned_width"]) * factor
                length = float(props["dimensioned_length"]) * factor
            else:
                side = math.sqrt(float(props.get("estimated_area") or 0.0)) * factor
                w = length = side
            area += 2 * (w + length) * assumptions.footing_depth_m
        report.lines.append(
            FormworkLine(
                concept_code=CODE_ZAPATAS, quantity=round(area, 2),
                source_detections=list(footings.source_detections),
                notes=[f"Perímetro × peralte {assumptions.footing_depth_m:.2f} m en "
                       f"{len(footings.source_detections)} zapatas"],
            )
        )

    slabs = lines.get("EST-003")
    if slabs is not None and slabs.raw_quantity > 0:
        vigueta: str | None = dimensions.vigueta_system if dimensions else None
        if vigueta:
            report.warnings.append(
                f"Losa de vigueta y bovedilla {vigueta}: sin cimbra de contacto; "
                "el apuntalamiento va en la matriz de la losa."
            )
        else:
            report.lines.append(
                FormworkLine(
                    concept_code=CODE_LOSA, quantity=round(slabs.raw_quantity, 2),
                    source_detections=list(slabs.source_detections),
                    notes=[f"Área de losa maciza {slabs.raw_quantity:,.1f} m²"],
                )
            )

    # Declared f'c vs priced f'c.
    declared = (specs or {}).get("concrete_fc") or {}
    for line in boq.lines:
        family = _FC_FAMILY_BY_CONCEPT.get(line.concept_code)
        if family is None or family not in declared:
            continue
        priced = _FC_IN_TEXT.search(line.description)
        sheet_fc = declared[family]
        if priced and int(priced.group(1)) != sheet_fc:
            note = (
                f"El plano declara f'c={sheet_fc} para {family}; el concepto costea "
                f"f'c={priced.group(1)}. Ajusta el concepto o su matriz."
            )
            line.assumptions.append(note)
            report.warnings.append(f"{line.concept_code}: {note}")
        elif priced:
            line.assumptions.append(f"f'c={sheet_fc} coincide con lo declarado en el plano.")
    return report


def apply_formwork(
    boq: BillOfQuantities, catalog: list, apus: dict, formwork: FormworkReport
) -> int:
    concepts = {concept.code: concept for concept in catalog}
    existing = {line.concept_code for line in boq.lines}
    added = 0
    for item in formwork.lines:
        concept = concepts.get(item.concept_code)
        apu = apus.get(item.concept_code)
        if concept is None or apu is None:
            boq.warnings.append(
                f"Cimbra calculada ({item.quantity:,.0f} m²) pero el catálogo no tiene el "
                f"concepto {item.concept_code} con matriz."
            )
            continue
        if item.concept_code in existing or item.quantity <= 0:
            continue
        boq.lines.append(
            BoqLine(
                concept_code=concept.code,
                description=concept.description,
                unit=concept.unit,
                quantity=round(item.quantity, 4),
                unit_price=apu.direct_unit_cost,
                amount=round(item.quantity * apu.direct_unit_cost, 2),
                phase=concept.phase,
                raw_quantity=item.quantity,
                raw_kind=QuantityKind.AREA,
                source_detection_count=len(item.source_detections),
                source_detections=list(item.source_detections),
                confidence=0.7,
                assumptions=["Área de contacto derivada de los elementos cuantificados"]
                + item.notes,
            )
        )
        added += 1
    boq.warnings.extend(formwork.warnings)
    if added:
        boq.direct_cost_total = round(sum(line.amount for line in boq.lines), 2)
        totals: dict[str, float] = {}
        for line in boq.lines:
            totals[line.phase] = round(totals.get(line.phase, 0.0) + line.amount, 2)
        boq.totals_by_phase = totals
    return added
