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
from klave_engine.costing.earthwork import cut_fill_volumes, describe
from klave_engine.costing.insumos import REFERENCE_PRICE_DISCLAIMER
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    Concept,
    CostingAssumptions,
    QuantityKind,
    QuantityRule,
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
MAX_COLUMN_SECTION_M2 = 2.00  # 1.4×1.4 m: a large building column
MAX_CASTILLO_SECTION_M2 = 0.25  # 50×50 cm: anything bigger is a column, not a castillo
MAX_LINEAR_SECTION_M2 = 0.60  # 50×120 cm: beyond this a "section" is another drawing


def rule_matches(rule: QuantityRule, detection: Detection) -> bool:
    """Whether a detection of the rule's type feeds it: the filter reads a
    property, else a field of the detection (family from the taxonomy)."""
    if not rule.property_filter:
        return True
    for key, allowed in rule.property_filter.items():
        value = detection.properties.get(key)
        if value is None:
            value = getattr(detection, key, None) or None
        if value not in allowed:
            return False
    return True


def _section_m2(detection: Detection, rule: QuantityRule, meters_factor: float) -> float:
    """Section of a linear element: declared on the sheet (cuadro/detalle/
    cota as "30x80"), else a plausible measured marker, else the default."""
    declared = detection.properties.get("section_cm")
    if isinstance(declared, str) and "x" in declared:
        try:
            a, b = (float(v) for v in declared.lower().split("x"))
            if MIN_COLUMN_SECTION_M2 <= a * b / 10_000.0 <= MAX_LINEAR_SECTION_M2:
                return a * b / 10_000.0
        except ValueError:
            pass
    measured = detection.properties.get(rule.section_property or "")
    if isinstance(measured, (int, float)) and measured > 0:
        if rule.section_height_m:
            # A wall: the measured value is its thickness, the section is
            # thickness × height.
            thickness = float(measured) * meters_factor
            if 0.05 <= thickness <= 0.6:
                return thickness * rule.section_height_m
            return rule.default_section_m2 or 0.0
        area = float(measured) * meters_factor ** 2
        if MIN_COLUMN_SECTION_M2 <= area <= MAX_COLUMN_SECTION_M2:
            return area
    return rule.default_section_m2 or 0.0


def _raw_over(concept: Concept, detections: list[Detection], meters_factor: float) -> float:
    """Count, or summed length/area/volume (converted to metres), over a detection set."""
    rule = concept.rule
    assert rule is not None  # callers skip manual (rule-less) concepts
    if rule.kind == QuantityKind.COUNT:
        return float(len(detections))
    if rule.kind in (QuantityKind.EARTHWORK_CUT, QuantityKind.EARTHWORK_FILL):
        return 0.0  # computed by _earthwork_result against the platform level
    if rule.kind == QuantityKind.LINEAR_VOLUME:
        return sum(
            float(d.properties[rule.source_property]) * meters_factor
            * _section_m2(d, rule, meters_factor)
            for d in detections
            if rule.source_property and rule.source_property in d.properties
        )
    if rule.kind == QuantityKind.VOLUME:
        volume = 0.0
        for d in detections:
            if not rule.source_property or rule.source_property not in d.properties:
                continue
            declared = d.properties.get(rule.thickness_property or "")
            thickness_m = (
                float(declared) / 100.0 if declared else (rule.default_thickness_m or 0.0)
            )
            volume += float(d.properties[rule.source_property]) * meters_factor ** 2 * thickness_m
        return volume
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
                 notes: list[str], by_view: dict[str, float] | None = None,
                 supersedes: set[str] | None = None) -> None:
        self.quantity = quantity
        self.raw = raw
        self.dets = dets
        self.notes = notes
        self.by_view = by_view or {}
        # Fragments of the concept's fallback assumptions that this result
        # made moot ("si no hay niveles N.P.T." when the levels were read).
        self.supersedes: set[str] = supersedes or set()
        self.sections = (0, 0, 0)  # declared, measured, assumed (columns only)


FALLBACK_HEIGHT = "si no hay niveles"
FALLBACK_SECTION = "si no hay marcador"


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
    rejected: list[str] = []
    for column in columns:
        is_castillo = column.label.strip().upper().startswith("K")
        default_m2 = (
            assumptions.castillo_section_m2 if is_castillo else assumptions.column_section_m2
        )
        section_m2: float | None = None
        declared_cm = column.properties.get("section_cm")
        if isinstance(declared_cm, str) and "x" in declared_cm:
            try:
                a_cm, b_cm = (float(v) for v in declared_cm.lower().split("x"))
                section_m2 = a_cm * b_cm / 10_000.0
                declared += 1
            except ValueError:
                section_m2 = None
        section_du2 = column.properties.get("section_area_du2")
        if section_m2 is None and section_du2 is not None:
            section_m2 = float(section_du2) * meters_factor * meters_factor
        # Only trust a measured section within plausible physical bounds;
        # otherwise the marker was an ID bubble / grid circle, not the section.
        max_m2 = MAX_CASTILLO_SECTION_M2 if is_castillo else MAX_COLUMN_SECTION_M2
        if section_m2 is not None and MIN_COLUMN_SECTION_M2 <= section_m2 <= max_m2:
            volume += section_m2 * height
            measured += 1
        else:
            if section_m2 is not None:
                # Never silently: the reading is reported next to the value used.
                rejected.append(
                    f"{column.label.strip() or '?'} {section_m2 * 10_000:.0f} cm² "
                    f"(fuera de {MIN_COLUMN_SECTION_M2 * 10_000:.0f}–{max_m2 * 10_000:.0f} cm²)"
                )
            volume += default_m2 * height
    assumed = len(columns) - measured
    notes = [
        f"{len(columns)} columnas y castillos × altura {height:.2f} m"
        + (" (de niveles N.P.T.)" if total_height else " (supuesta: altura de entrepiso)"),
        _section_note(declared, measured - declared, assumed, assumptions),
    ]
    if rejected:
        notes.append(
            "Secciones leídas fuera de rango, sustituidas por la supuesta: "
            + ", ".join(sorted(set(rejected))[:6])
            + (f" y {len(set(rejected)) - 6} más" if len(set(rejected)) > 6 else "")
        )
    result = _LineResult(round(volume, 6), float(len(columns)), columns, notes)
    result.sections = (declared, measured - declared, assumed)
    if total_height:
        result.supersedes.add(FALLBACK_HEIGHT)
    if assumed == 0:
        result.supersedes.add(FALLBACK_SECTION)
    return result


def _section_note(
    declared: int, measured: int, assumed: int, assumptions: CostingAssumptions
) -> str:
    note = (
        f"Sección: {declared} declaradas en el plano (cuadro/detalle), "
        f"{measured} medidas del marcador"
    )
    if assumed:
        note += (
            f", {assumed} supuestas (castillo {assumptions.castillo_section_m2:.3f} m², "
            f"columna {assumptions.column_section_m2:.3f} m²)"
        )
    return note


def _earthwork_result(
    concept: Concept,
    terrains: list[Detection],
    meters_factor: float,
    assumptions: CostingAssumptions,
) -> _LineResult:
    """Corte or terraplén over every terrain read, against the platform level."""
    rule = concept.rule
    assert rule is not None and assumptions.platform_level_m is not None
    level = assumptions.platform_level_m
    total = 0.0
    notes: list[str] = []
    used: list[Detection] = []
    for terrain in terrains:
        volumes = cut_fill_volumes(
            terrain.properties.get("sample_points") or [],
            terrain.properties.get("polygon") or [],
            level,
            meters_factor,
        )
        if volumes is None:
            continue
        total += volumes.cut_m3 if rule.kind == QuantityKind.EARTHWORK_CUT else volumes.fill_m3
        notes.append(describe(volumes, level))
        used.append(terrain)
    return _LineResult(round(total, 6), round(total, 6), used, notes)


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

    titles = {v.view_id: v.title for v in segmentation.plan_views()}

    def per_view(dets: list[Detection]) -> dict[str, float]:
        """The line's quantity split by planta, in presupuesto order."""
        split: dict[str, float] = {}
        for view in segmentation.plan_views():
            raw = _raw_over(concept, in_views(dets, {view.view_id}), meters_factor)
            if raw > 0:
                split[titles[view.view_id]] = round(raw * concept.quantity_factor, 4)
        return split

    scope = concept.view_scope

    heights = segmentation.story_heights()

    if scope == ViewScope.COLUMN_VOLUME:
        by_view: dict[str, list[Detection]] = defaultdict(list)
        for d in matched_plan:
            by_view[assignment[d.detection_id]].append(d)
        if heights:
            # Each planta's columns × its own story height (NTC to NTC); the
            # cimentación planta draws the same columns at their base.
            total = _LineResult(0.0, 0.0, [], [])
            split: dict[str, float] = {}
            n_declared = n_measured = n_assumed = 0
            for view in segmentation.superstructure_views():
                columns = by_view.get(view.view_id, [])
                height = heights.get(view.view_id)
                if not columns or height is None:
                    continue
                part = _column_volume(columns, meters_factor, assumptions, height)
                total.quantity = round(total.quantity + part.quantity, 6)
                total.raw += part.raw
                total.dets.extend(part.dets)
                split[titles[view.view_id]] = part.quantity
                n_declared += part.sections[0]
                n_measured += part.sections[1]
                n_assumed += part.sections[2]
            if total.dets:
                total.notes = [
                    "Columnas y castillos por planta × altura de entrepiso declarada en el "
                    "plano (niveles NTC/NPT): "
                    + ", ".join(
                        f"{titles[v.view_id].split(' · ')[-1][:22]} {heights[v.view_id]:.2f} m"
                        for v in segmentation.superstructure_views() if v.view_id in heights
                    ),
                    _section_note(n_declared, n_measured, n_assumed, assumptions),
                ]
                total.by_view = split
                total.supersedes.add(FALLBACK_HEIGHT)
                if n_assumed == 0:
                    total.supersedes.add(FALLBACK_SECTION)
                return total
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
                           _contributing(concept, dets), [note], per_view(dets))

    if scope == ViewScope.SUPERSTRUCTURE_SUM:
        dets = in_views(matched_plan, superstructure_ids) or matched_plan
        rule = concept.rule
        if rule is not None and rule.height_from_levels and heights and dets:
            # The planta's own story height replaces the assumed height.
            quantity_sum = 0.0
            raw_sum = 0.0
            view_split: dict[str, float] = {}
            for view in segmentation.superstructure_views():
                view_dets = in_views(dets, {view.view_id})
                if not view_dets:
                    continue
                height = heights.get(view.view_id)
                if rule.kind == QuantityKind.LINEAR_VOLUME and rule.section_height_m:
                    scoped = concept.model_copy(
                        update={
                            "rule": rule.model_copy(
                                update={"section_height_m": height or rule.section_height_m}
                            )
                        }
                    )
                    view_raw = _raw_over(scoped, view_dets, meters_factor)
                    view_quantity = view_raw * concept.quantity_factor
                else:
                    view_raw = _raw_over(concept, view_dets, meters_factor)
                    view_quantity = view_raw * (
                        height * rule.sides if height is not None else concept.quantity_factor
                    )
                quantity_sum += view_quantity
                raw_sum += view_raw
                view_split[titles[view.view_id]] = round(view_quantity, 4)
            declared = ", ".join(
                f"{titles[v.view_id].split(' · ')[-1][:22]} {heights[v.view_id]:.2f} m"
                for v in segmentation.superstructure_views() if v.view_id in heights
            )
            return _LineResult(
                round(quantity_sum, 6), raw_sum, _contributing(concept, dets),
                [f"Suma de plantas de superestructura ({len(dets)} detecciones)",
                 f"Altura de entrepiso por planta declarada en el plano (NTC/NPT): {declared}"],
                view_split if len(view_split) > 1 else {},
                supersedes={FALLBACK_HEIGHT},
            )
        raw = _raw_over(concept, dets, meters_factor)
        return _LineResult(round(raw * concept.quantity_factor, 6), raw,
                           _contributing(concept, dets),
                           [f"Suma de plantas de superestructura ({len(dets)} detecciones)"],
                           per_view(dets))

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
                           ["Huella de la planta más grande (una sola vez)"],
                           per_view(best_dets))

    raw = _raw_over(concept, matched_plan, meters_factor)
    return _LineResult(round(raw * concept.quantity_factor, 6), raw,
                       _contributing(concept, matched_plan), [], per_view(matched_plan))


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
        matched = [
            d for d in by_type.get(concept.rule.detection_type, [])
            if rule_matches(concept.rule, d)
        ]
        if concept.rule.kind in (QuantityKind.EARTHWORK_CUT, QuantityKind.EARTHWORK_FILL):
            if not matched:
                continue  # no survey on the drawing: nothing to say, the detector said it
            if assumptions.platform_level_m is None:
                if not any("nivel de plataforma" in w for w in boq.warnings):
                    boq.warnings.append(
                        "Terracerías: el plano trae topografía pero no se ha definido el "
                        "nivel de plataforma (Parámetros → Nivel de plataforma); corte y "
                        "terraplén no se calculan contra un nivel supuesto."
                    )
                continue
            result = _earthwork_result(concept, matched, meters_factor, assumptions)
        elif seg is not None:
            matched_plan = [
                d for d in matched if seg.assignment.get(d.detection_id) in plan_ids
            ]
            result = _scoped_result(
                concept, matched_plan, seg, meters_factor, assumptions
            )
        elif concept.view_scope == ViewScope.COLUMN_VOLUME and matched:
            # A sheet without frames (one planta, or a file with no title
            # blocks) still declares sections in its cuadro and markers; the
            # count × default section × default height shortcut threw that
            # reading away. One planta: the assumed column height applies.
            result = _column_volume(matched, meters_factor, assumptions, None)
        else:
            raw = _raw_over(concept, matched, meters_factor)
            quantity = round(raw * concept.quantity_factor, 6)
            result = _LineResult(quantity, raw, _contributing(concept, matched), [])

        if result.quantity <= 0:
            # A concept whose element type the drawing does not contain at
            # all (no locales on a structural set, no terrain without a
            # survey) simply does not apply; only a concept that HAD
            # candidates and matched none deserves a warning.
            if by_type.get(concept.rule.detection_type):
                boq.warnings.append(
                    f"Concepto {concept.code} ({concept.description[:40]}…) sin "
                    "cantidades: no hubo detecciones aplicables."
                )
            continue

        apu = apus.get(concept.code)
        if apu is None:
            # The quantity is real; the money is unknown, not zero. The line
            # stays on the presupuesto marked unpriced so nobody misses it.
            boq.warnings.append(
                f"Concepto {concept.code} ({concept.description[:40]}…): {result.quantity:,.2f} "
                f"{concept.unit} contados, sin matriz ni precio adoptado — sin costo hasta que "
                "el catálogo le dé precio."
            )
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
                unit_price=apu.direct_unit_cost if apu else 0.0,
                amount=round(result.quantity * apu.direct_unit_cost, 2) if apu else 0.0,
                unpriced=apu is None,
                phase=concept.phase,
                raw_quantity=round(result.raw, 3),
                raw_kind=concept.rule.kind,
                source_detection_count=len(contributing),
                source_detections=[d.detection_id for d in contributing][:200],
                confidence=round(confidence, 3),
                assumptions=[
                    a for a in concept.assumptions
                    if not any(fragment in a for fragment in result.supersedes)
                ] + result.notes + (
                    [f"P.U. adoptado de {apu.price_source}"] if apu and apu.price_source else []
                ),
                by_view=result.by_view if len(result.by_view) > 1 else {},
                taller_clave=concept.taller_clave,
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
