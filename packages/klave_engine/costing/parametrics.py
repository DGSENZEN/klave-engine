"""Paramétricos: the 60 % of a presupuesto no plan reader produces, proposed
from the taller's own history instead of remembered by hand.

A parametric rule says "this concept goes at F units per BASIS" — per m²
construido, per planta, per local of a kind (baño, recámara, interior…),
or a fixed lot per project. Rules come from a past presupuesto imported as
a plantilla (quantity ÷ that project's m²) or are written by the taller.
Applied to a new project they produce lines tagged *paramétrico* with the
basis, the factor and the source written on them — proposals to edit, never
readings, and never for a concept the engine already quantified from the
plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    Concept,
    QuantityKind,
    UnitPriceAnalysis,
)
from klave_engine.detection.results import Detection, DetectionType
from klave_engine.detection.views import SheetSegmentation

BASIS_M2 = "m2_construida"
BASIS_PLANTA = "planta"
BASIS_PROYECTO = "proyecto"
BASIS_LOCAL = "local"  # local:<kind or word>
PARAMETRIC_CONFIDENCE = 0.5


@dataclass
class ParametricBasis:
    """What the drawing says about the project's size, for the rules."""

    area_construida_m2: float = 0.0
    area_source: str = ""
    plantas: int = 0
    locales: dict[str, int] = field(default_factory=dict)  # kind/word → count
    locales_area_m2: dict[str, float] = field(default_factory=dict)

    def value(self, basis: str) -> tuple[float, str]:
        """(value, how it was read) for a basis key; 0 when unknown."""
        if basis == BASIS_M2:
            return self.area_construida_m2, self.area_source
        if basis == BASIS_PLANTA:
            return float(self.plantas), "plantas de superestructura en el plano"
        if basis == BASIS_PROYECTO:
            return 1.0, "por proyecto"
        if basis.startswith(BASIS_LOCAL + ":"):
            key = basis.split(":", 1)[1].strip().lower()
            return float(self.locales.get(key, 0)), f"locales «{key}» leídos del plano"
        return 0.0, ""


def compute_basis(
    detections: list[Detection],
    segmentation: SheetSegmentation | None,
    meters_factor: float,
    area_override_m2: float | None = None,
) -> ParametricBasis:
    """Area construida = the tableros of every superstructure planta (the
    slabs ARE the built floor); plantas = superstructure plan views; locales
    by kind and by name word."""
    basis = ParametricBasis()
    assignment = segmentation.assignment if segmentation else {}
    super_ids = (
        {v.view_id for v in segmentation.superstructure_views()} if segmentation else set()
    )
    basis.plantas = len(super_ids)
    area = 0.0
    counted = 0
    for d in detections:
        if d.detection_type != DetectionType.slab_region:
            continue
        view = assignment.get(d.detection_id)
        if super_ids and view not in super_ids:
            continue
        if d.properties.get("family") == "cimentacion":
            continue
        estimated = d.properties.get("estimated_area")
        if estimated is None:
            continue
        area += float(estimated) * meters_factor * meters_factor
        counted += 1
    if area_override_m2 is not None and area_override_m2 > 0:
        basis.area_construida_m2 = round(area_override_m2, 2)
        basis.area_source = "área construida capturada en Parámetros"
    elif counted:
        basis.area_construida_m2 = round(area, 2)
        basis.area_source = f"suma de {counted} tableros de losa de superestructura"
    for d in detections:
        if d.detection_type != DetectionType.room:
            continue
        kind = str(d.properties.get("room_kind") or "sin_nombre")
        basis.locales[kind] = basis.locales.get(kind, 0) + 1
        label = str(d.properties.get("label") or "").lower()
        for word in label.replace("/", " ").split():
            word = word.strip(".,:;()")
            if len(word) >= 4:
                basis.locales[word] = basis.locales.get(word, 0) + 1
        area_m2 = float(d.properties.get("estimated_area") or 0.0) * meters_factor ** 2
        basis.locales_area_m2[kind] = basis.locales_area_m2.get(kind, 0.0) + area_m2
    return basis


def apply_parametrics(
    boq: BillOfQuantities,
    catalog: list[Concept],
    apus: dict[str, UnitPriceAnalysis],
    rules: list[dict] | None,
    basis: ParametricBasis,
) -> int:
    """Add parametric lines for concepts the plan did not quantify. Returns
    how many rules produced a line."""
    if not rules:
        return 0
    concepts = {concept.code: concept for concept in catalog}
    lines = {line.concept_code: line for line in boq.lines}
    applied = 0
    for rule in rules:
        code = str(rule.get("concept_code") or "")
        concept = concepts.get(code)
        if concept is None:
            boq.warnings.append(
                f"Paramétrico: la regla de {code} apunta a un concepto inexistente; se ignora."
            )
            continue
        existing = lines.get(code)
        if existing is not None and existing.quantity > 0 and not existing.parametric:
            continue  # the plan (or the levantamiento) already quantified it: the reading wins
        basis_key = str(rule.get("basis") or BASIS_M2)
        value, how = basis.value(basis_key)
        if value <= 0:
            if basis_key == BASIS_M2:
                boq.warnings.append(
                    f"Paramétrico {code}: sin área construida leída (no hay tableros de losa) "
                    "ni capturada en Parámetros; captúrala para proponer la cantidad."
                )
            continue
        factor = float(rule.get("factor") or 0.0)
        if factor <= 0:
            continue
        apu = apus.get(code)
        if apu is None:
            boq.warnings.append(
                f"Paramétrico {code} ({concept.description[:40]}…) sin matriz ni precio "
                "adoptado; la cantidad propuesta queda sin costo."
            )
            continue
        quantity = round(factor * value, 4)
        source = str(rule.get("source") or "regla del taller")
        basis_label = {
            BASIS_M2: "m² construido", BASIS_PLANTA: "planta", BASIS_PROYECTO: "proyecto",
        }.get(basis_key, basis_key.replace("local:", "local "))
        note = (
            f"Paramétrico: {factor:g} {concept.unit} por {basis_label} × {value:,.2f} "
            f"({how}) — fuente: {source}. Propuesta para revisar, no lectura del plano."
        )
        if rule.get("note"):
            note += f" {rule['note']}"
        if existing is not None:
            existing.quantity = quantity
            existing.amount = round(quantity * existing.unit_price, 2)
            existing.assumptions.append(note)
        else:
            boq.lines.append(
                BoqLine(
                    concept_code=code,
                    description=concept.description,
                    unit=concept.unit,
                    quantity=quantity,
                    unit_price=apu.direct_unit_cost,
                    amount=round(quantity * apu.direct_unit_cost, 2),
                    phase=concept.phase,
                    raw_quantity=value,
                    raw_kind=QuantityKind.COUNT,
                    source_detection_count=0,
                    confidence=PARAMETRIC_CONFIDENCE,
                    assumptions=[note],
                    parametric=True,
                    taller_clave=concept.taller_clave,
                )
            )
            lines[code] = boq.lines[-1]
        applied += 1
    if applied:
        boq.assumptions.append(
            f"{applied} concepto(s) paramétrico(s): cantidades propuestas desde la historia del "
            "taller, marcadas como tales; revísalas antes de entregar."
        )
    return applied
