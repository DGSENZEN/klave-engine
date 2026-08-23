"""Acero de refuerzo (kg) derived from what the BoQ already counted.

The sheet states armados per mark and family (``4#3 E#2@20``); the BoQ knows
how many castillos, how many metres of wall and trabe, and which zapatas.
This stage multiplies the two into kilograms with every assumption written
down: bar weights per número (NMX-B-506), anchorage, hooks, cover, waste,
and a default armado only where the sheet says nothing — and says so.
"""

import math
import re

from pydantic import BaseModel, Field

from klave_engine.costing.models import BillOfQuantities, BoqLine, QuantityKind
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation

# kg/m por número de varilla (diámetro en octavos de pulgada).
BAR_KG_PER_M: dict[str, float] = {
    "2": 0.248, "2.5": 0.388, "3": 0.560, "4": 0.994, "5": 1.552, "6": 2.235,
    "7": 3.042, "8": 3.973, "10": 6.404, "12": 9.021,
}

_REBAR_RE = re.compile(r"^(\d{1,2})#(\d(?:\.5)?)$")
_SPACING_RE = re.compile(r"^#(\d(?:\.5)?)@(\d{1,3})$")

CODE_CASTILLOS = "ACE-001"
CODE_DALAS = "ACE-002"
CODE_ZAPATAS = "ACE-003"
CODE_TRABES = "ACE-004"
CODE_MALLA = "ACE-005"
CODE_LOSAS = "ACE-006"
_SLAB_LAYER_RE = re.compile(
    r"(?P<layer>L\.?\s*[SI]\.?|LECHO\s+(?:SUP|INF)\w*)?\s*#\s*(?P<bar>\d(?:\.5)?)\s*@\s*(?P<sp>\d{1,3})"
    r"\s*(?P<both>A\s*/\s*S|A\.?S\.?|AMBOS\s+SENTIDOS)?",
    re.I,
)


class SteelAssumptions(BaseModel):
    cover_m: float = 0.025
    hook_m: float = 0.075  # per stirrup, total for both hooks
    anchorage_m: float = 0.40  # longitudinal bars beyond the element
    waste_pct: float = 5.0
    default_castillo: tuple[str, str, tuple[int, int]] = ("4#3", "#2@20", (15, 20))
    default_dala: tuple[str, str, tuple[int, int]] = ("4#3", "#2@20", (15, 20))
    default_zapata_mesh: str = "#4@20"
    malla_overlap_factor: float = 1.10
    wall_height_m: float = 2.7


class SteelLine(BaseModel):
    concept_code: str
    quantity: float
    unit: str
    source_detections: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SteelReport(BaseModel):
    lines: list[SteelLine] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def parse_rebar(text: str | None) -> tuple[int, str] | None:
    if not text:
        return None
    m = _REBAR_RE.match(text.replace(" ", ""))
    return (int(m.group(1)), m.group(2)) if m and m.group(2) in BAR_KG_PER_M else None


def parse_spacing(text: str | None) -> tuple[str, float] | None:
    """'#2@20' → (número, spacing in metres)."""
    if not text:
        return None
    m = _SPACING_RE.match(text.replace(" ", "").upper().replace("E", ""))
    if not m or m.group(1) not in BAR_KG_PER_M:
        return None
    return m.group(1), int(m.group(2)) / 100.0


def _spec_for(specs: dict | None, mark: str, family: str) -> tuple[dict | None, str]:
    """The sheet's spec for a mark, its family, or nothing — and which."""
    if not specs:
        return None, "none"
    by_mark = specs.get("by_mark") or {}
    by_family = specs.get("by_family") or {}
    if mark.upper() in by_mark:
        return by_mark[mark.upper()], "mark"
    if family in by_family:
        return by_family[family], "family"
    return None, "none"


def slab_rebar_kg_per_m2(label: str | None) -> tuple[float, str] | None:
    """Rebar per m² from a slab label: 'LS #4@20 A/S LI #4@20 A/S' is two
    layers, each both ways; '#4@20 A/S' on a 'DOBLEMENTE ARMADA' slab is two
    layers too. Returns (kg/m², how it was read) or None when the label
    carries no armado."""
    if not label:
        return None
    text = " ".join(label.split()).upper()
    matches = list(_SLAB_LAYER_RE.finditer(text))
    if not matches:
        return None
    total = 0.0
    parts: list[str] = []
    explicit_layers = any(m.group("layer") for m in matches)
    for m in matches:
        bar = m.group("bar")
        if bar not in BAR_KG_PER_M:
            continue
        spacing_m = int(m.group("sp")) / 100.0
        if spacing_m <= 0:
            continue
        directions = 2 if m.group("both") else 1
        kg = BAR_KG_PER_M[bar] * (1.0 / spacing_m) * directions
        total += kg
        parts.append(f"#{bar}@{m.group('sp')}{' a/s' if directions == 2 else ''}")
    if total <= 0:
        return None
    if not explicit_layers and "DOBLEMENTE" in text:
        total *= 2
        parts.append("×2 lechos (doblemente armada)")
    return round(total, 3), ", ".join(parts)


def _linear_element_kg(
    length_m: float, rebar: tuple[int, str], stirrups: tuple[str, float] | None,
    section_cm: tuple[int, int], a: SteelAssumptions, *, anchorage: bool,
) -> tuple[float, float]:
    """(longitudinal kg, stirrup kg) for one prismatic element."""
    count, number = rebar
    bar_length = length_m + (a.anchorage_m if anchorage else 0.0)
    longitudinal = count * bar_length * BAR_KG_PER_M[number]
    stirrup_kg = 0.0
    if stirrups is not None:
        s_number, spacing = stirrups
        w, h = section_cm[0] / 100.0, section_cm[1] / 100.0
        perimeter = 2 * ((w - 2 * a.cover_m) + (h - 2 * a.cover_m)) + a.hook_m
        n_stirrups = math.floor(length_m / spacing) + 1 if spacing > 0 else 0
        stirrup_kg = n_stirrups * perimeter * BAR_KG_PER_M[s_number]
    return longitudinal, stirrup_kg


def compute_steel(
    boq: BillOfQuantities,
    detections: list[Detection],
    specs: dict | None,
    segmentation: SheetSegmentation | None,
    meters_factor: float | None,
    column_height_m: float,
    assumptions: SteelAssumptions | None = None,
) -> SteelReport:
    a = assumptions or SteelAssumptions()
    report = SteelReport()
    by_id = {d.detection_id: d for d in detections}
    lines = {line.concept_code: line for line in boq.lines}
    waste = 1.0 + a.waste_pct / 100.0
    height = (segmentation.total_height() if segmentation else None) or column_height_m

    # --- castillos / columnas -------------------------------------------
    columns = lines.get("EST-001")
    if columns is not None and columns.source_detections:
        total_long = total_stirrup = 0.0
        groups: dict[str, list[Detection]] = {}
        for det_id in columns.source_detections:
            det = by_id.get(det_id)
            if det is not None:
                groups.setdefault(det.label.strip().upper() or "?", []).append(det)
        notes: list[str] = []
        assumed_marks: list[str] = []
        for mark, members in sorted(groups.items()):
            family = "castillo" if mark.startswith("K") else "columna"
            spec, origin = _spec_for(specs, mark, family)
            rebar = parse_rebar(spec.get("rebar")) if spec else None
            stirrups = parse_spacing(spec.get("stirrups")) if spec else None
            section = tuple(spec["section_cm"]) if spec and spec.get("section_cm") else None
            if rebar is None or section is None:
                d_rebar, d_stirrup, d_section = a.default_castillo
                rebar = rebar or parse_rebar(d_rebar)
                stirrups = stirrups or parse_spacing(d_stirrup)
                section = section or d_section
                assumed_marks.append(mark)
            assert rebar is not None and section is not None
            long_kg, stir_kg = _linear_element_kg(
                height, rebar, stirrups, (int(section[0]), int(section[1])), a, anchorage=True
            )
            total_long += long_kg * len(members)
            total_stirrup += stir_kg * len(members)
            notes.append(
                f"{mark}: {len(members)} pzas × {rebar[0]}#{rebar[1]}"
                + (f" E#{stirrups[0]}@{stirrups[1] * 100:.0f}" if stirrups else "")
                + f" sección {section[0]}x{section[1]} cm "
                + ("(plano)" if origin != "none" else "(supuesto)")
            )
        quantity = (total_long + total_stirrup) * waste
        if assumed_marks:
            notes.append(
                "Armado supuesto (el plano no lo declara): " + ", ".join(assumed_marks[:8])
            )
        notes.insert(
            0,
            f"Altura {height:.2f} m por elemento + {a.anchorage_m:.2f} m de anclaje; "
            f"desperdicio {a.waste_pct:g} %",
        )
        report.lines.append(
            SteelLine(
                concept_code=CODE_CASTILLOS, quantity=round(quantity, 2), unit="KG",
                source_detections=list(columns.source_detections), notes=notes,
            )
        )

    # --- dalas over walls ------------------------------------------------
    walls = lines.get("EST-004")
    if walls is not None and walls.raw_quantity > 0:
        length = walls.raw_quantity  # metres of wall (already in m)
        spec, origin = _spec_for(specs, "DALA", "dala")
        rebar = parse_rebar(spec.get("rebar")) if spec else None
        stirrups = parse_spacing(spec.get("stirrups")) if spec else None
        section = tuple(spec["section_cm"]) if spec and spec.get("section_cm") else None
        assumed = rebar is None or section is None
        if assumed:
            d_rebar, d_stirrup, d_section = a.default_dala
            rebar = rebar or parse_rebar(d_rebar)
            stirrups = stirrups or parse_spacing(d_stirrup)
            section = section or d_section
        assert rebar is not None and section is not None
        long_kg, stir_kg = _linear_element_kg(
            length, rebar, stirrups, (int(section[0]), int(section[1])), a, anchorage=False
        )
        report.lines.append(
            SteelLine(
                concept_code=CODE_DALAS, quantity=round((long_kg + stir_kg) * waste, 2),
                unit="KG", source_detections=list(walls.source_detections),
                notes=[
                    f"Dala de cerramiento sobre {length:,.1f} m de muro: {rebar[0]}#{rebar[1]}"
                    + (f" E#{stirrups[0]}@{stirrups[1] * 100:.0f}" if stirrups else "")
                    + f" sección {section[0]}x{section[1]} cm "
                    + ("(supuesto)" if assumed else f"(plano: {origin})"),
                    f"Desperdicio {a.waste_pct:g} %",
                ],
            )
        )

    # --- zapatas: parrilla -------------------------------------------------
    footings = lines.get("CIM-002")
    if footings is not None and footings.source_detections and meters_factor:
        spec, origin = _spec_for(specs, "ZAPATA", "zapata")
        mesh = parse_spacing(spec.get("mesh")) if spec else None
        assumed = mesh is None
        mesh = mesh or parse_spacing(a.default_zapata_mesh)
        assert mesh is not None
        number, spacing = mesh
        total = 0.0
        sized = 0
        for det_id in footings.source_detections:
            det = by_id.get(det_id)
            if det is None:
                continue
            props = det.properties
            if props.get("dimensioned_width") and props.get("dimensioned_length"):
                w = float(props["dimensioned_width"]) * meters_factor
                length = float(props["dimensioned_length"]) * meters_factor
                sized += 1
            else:
                area = float(props.get("estimated_area") or 0.0) * meters_factor**2
                w = length = math.sqrt(area) if area > 0 else 0.0
            if w <= 0 or length <= 0:
                continue
            bars_along = math.floor((w - 2 * a.cover_m) / spacing) + 1
            bars_across = math.floor((length - 2 * a.cover_m) / spacing) + 1
            total += (bars_along * (length + a.hook_m) + bars_across * (w + a.hook_m)) * (
                BAR_KG_PER_M[number]
            )
        report.lines.append(
            SteelLine(
                concept_code=CODE_ZAPATAS, quantity=round(total * waste, 2), unit="KG",
                source_detections=list(footings.source_detections),
                notes=[
                    f"Parrilla #{number}@{spacing * 100:.0f} cm en ambos sentidos "
                    + ("(supuesta)" if assumed else f"(plano: {origin})")
                    + f" en {len(footings.source_detections)} zapatas, {sized} con cotas del plano",
                    f"Ganchos {a.hook_m:.3f} m, recubrimiento {a.cover_m:.3f} m, "
                    f"desperdicio {a.waste_pct:g} %",
                ],
            )
        )

    # --- trabes: only with a stated armado -----------------------------------
    beam_sources: list[tuple[str, str]] = []
    for line_code, family in (("EST-002", "trabe"), ("CIM-008", "contratrabe")):
        beam_line = lines.get(line_code)
        if beam_line is not None:
            beam_sources.extend((det_id, family) for det_id in beam_line.source_detections)
    if beam_sources:
        total = 0.0
        covered: list[str] = []
        missing: set[str] = set()
        for det_id, family in beam_sources:
            det = by_id.get(det_id)
            if det is None:
                continue
            mark = det.label.strip().upper()
            spec, _origin = _spec_for(specs, mark, family)
            rebar = parse_rebar(spec.get("rebar")) if spec else None
            section = tuple(spec["section_cm"]) if spec and spec.get("section_cm") else None
            span_du = float(det.properties.get("estimated_span_length") or 0.0)
            span = span_du * (meters_factor or 1.0)
            if rebar is None or section is None or span <= 0:
                missing.add(mark)
                continue
            stirrups = parse_spacing(spec.get("stirrups")) if spec else None
            long_kg, stir_kg = _linear_element_kg(
                span, rebar, stirrups, (int(section[0]), int(section[1])), a, anchorage=True
            )
            total += long_kg + stir_kg
            covered.append(det_id)
        if covered:
            report.lines.append(
                SteelLine(
                    concept_code=CODE_TRABES, quantity=round(total * waste, 2), unit="KG",
                    source_detections=covered,
                    notes=[f"{len(covered)} trabes con armado declarado en el plano",
                           f"Desperdicio {a.waste_pct:g} %"],
                )
            )
        if missing:
            report.warnings.append(
                "Trabes sin armado declarado en el plano (acero no cuantificado): "
                + ", ".join(sorted(missing)[:10])
            )

    # --- losa: malla electrosoldada en la capa de compresión ----------------
    malla_area = 0.0
    malla_sources: list[str] = []
    for code in ("EST-003", "EST-012"):
        line = lines.get(code)
        if line is not None and line.raw_quantity > 0:
            malla_area += line.raw_quantity
            malla_sources.extend(line.source_detections)
    if malla_area > 0:
        report.lines.append(
            SteelLine(
                concept_code=CODE_MALLA,
                quantity=round(malla_area * a.malla_overlap_factor, 2), unit="M2",
                source_detections=malla_sources,
                notes=[
                    f"Área de losa reticular/vigueta {malla_area:,.1f} m² × "
                    f"{a.malla_overlap_factor:.2f} de traslapes (capa de compresión)"
                ],
            )
        )
    # --- losas macizas y de cimentación: armado por su propia etiqueta ---------
    factor = (meters_factor or 1.0) ** 2
    slab_total = 0.0
    slab_sources: list[str] = []
    slab_notes: list[str] = []
    for code, label in (("EST-013", "losa maciza"), ("CIM-007", "losa de cimentación")):
        line = lines.get(code)
        if line is None or line.raw_quantity <= 0:
            continue
        read_m2 = 0.0
        unread_m2 = 0.0
        for det_id in line.source_detections:
            det = by_id.get(det_id)
            if det is None:
                continue
            area = float(det.properties.get("estimated_area") or 0.0) * factor
            parsed = slab_rebar_kg_per_m2(det.properties.get("label"))
            if parsed is None or area <= 0:
                unread_m2 += area
                continue
            kg_m2, how = parsed
            slab_total += area * kg_m2
            read_m2 += area
            slab_sources.append(det_id)
            if how not in slab_notes:
                slab_notes.append(how)
        if unread_m2 > 0:
            report.warnings.append(
                f"{label.capitalize()}: {unread_m2:,.1f} m² sin armado en su etiqueta; ese acero "
                "no se cuantificó (capturarlo del detalle)."
            )
        if read_m2 > 0:
            slab_notes.append(f"{label} {read_m2:,.1f} m² con armado leído de la etiqueta")
    if slab_total > 0:
        report.lines.append(
            SteelLine(
                concept_code=CODE_LOSAS, quantity=round(slab_total * waste, 2), unit="KG",
                source_detections=slab_sources,
                notes=["Parrillas por m² según etiqueta de cada tablero: " + "; ".join(slab_notes),
                       f"Desperdicio {a.waste_pct:g} %"],
            )
        )
    return report


def apply_steel(boq: BillOfQuantities, catalog: list, apus: dict, steel: SteelReport) -> int:
    """Append steel lines for the concepts the catalog has; report the rest."""
    concepts = {concept.code: concept for concept in catalog}
    existing = {line.concept_code for line in boq.lines}
    added = 0
    for steel_line in steel.lines:
        concept = concepts.get(steel_line.concept_code)
        apu = apus.get(steel_line.concept_code)
        if concept is None or apu is None:
            boq.warnings.append(
                f"Acero calculado ({steel_line.quantity:,.0f} {steel_line.unit}) pero el "
                f"catálogo no tiene el concepto {steel_line.concept_code} con matriz: "
                "agrégalo para costearlo."
            )
            continue
        if steel_line.concept_code in existing or steel_line.quantity <= 0:
            continue
        boq.lines.append(
            BoqLine(
                concept_code=concept.code,
                description=concept.description,
                unit=concept.unit,
                quantity=round(steel_line.quantity, 4),
                unit_price=apu.direct_unit_cost,
                amount=round(steel_line.quantity * apu.direct_unit_cost, 2),
                phase=concept.phase,
                raw_quantity=steel_line.quantity,
                raw_kind=QuantityKind.COUNT,
                source_detection_count=len(steel_line.source_detections),
                source_detections=list(steel_line.source_detections),
                confidence=0.7,
                assumptions=["Derivado de armados del plano y cantidades del presupuesto"]
                + steel_line.notes,
            )
        )
        added += 1
    boq.warnings.extend(steel.warnings)
    if added:
        boq.direct_cost_total = round(sum(line.amount for line in boq.lines), 2)
        totals: dict[str, float] = {}
        for line in boq.lines:
            totals[line.phase] = round(totals.get(line.phase, 0.0) + line.amount, 2)
        boq.totals_by_phase = totals
    return added
