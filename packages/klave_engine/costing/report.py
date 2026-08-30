"""Cost report assembly: the full workflow in one artifact, plus exports."""

import csv
import io
import math
from collections import Counter
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
from klave_engine.costing.cimentacion import apply_cimentacion_earthmoving
from klave_engine.costing.derivadas import aplicar_derivadas
from klave_engine.costing.financial import build_financial_plan
from klave_engine.costing.formwork import apply_formwork, compute_formwork
from klave_engine.costing.indicadores import compute_indicators
from klave_engine.costing.instalaciones import ya_detectado
from klave_engine.costing.integration import integrate_costs, resolve_integration
from klave_engine.costing.levantamiento import apply_inventory
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    ComponenteResuelto,
    Concept,
    CostingAssumptions,
    CostingConfig,
    CostIntegration,
    CostReport,
    FinancialPlan,
    QuantityKind,
    Resource,
    ResourceType,
    ScheduleConfig,
    UnitPriceAnalysis,
    WorkSchedule,
)
from klave_engine.costing.parametrics import apply_parametrics, compute_basis
from klave_engine.costing.piles import apply_piles
from klave_engine.costing.plantilla import (
    build_personal_tecnico,
    desajuste_de_indirectos,
)
from klave_engine.costing.reviews import ManualAdjustment
from klave_engine.costing.schedule import build_schedule
from klave_engine.costing.steel import SteelAssumptions, apply_steel, compute_steel
from klave_engine.costing.vigencia import freshness
from klave_engine.detection.dimensions import DimensionInventory
from klave_engine.detection.results import Detection, DetectionType
from klave_engine.detection.views import SheetSegmentation
from klave_engine.dxf.units import DrawingUnits

logger = get_logger(__name__)


def _typical_column_section(detections: list[Detection]) -> tuple[int, int, int] | None:
    """The section most columns declare (cuadro or marker), for the columns
    that declare none. Only sections bound to a column mark count — never
    the most frequent NxM of the whole sheet, which may be a zapata."""
    counts: Counter[tuple[int, int]] = Counter()
    for det in detections:
        if det.detection_type != DetectionType.column_tag:
            continue
        if det.label.strip().upper().startswith("K"):
            continue  # castillos have their own assumption
        declared = det.properties.get("section_cm")
        if not isinstance(declared, str) or "x" not in declared:
            continue
        try:
            a, b = (int(float(v)) for v in declared.lower().split("x"))
        except ValueError:
            continue
        counts[(min(a, b), max(a, b))] += 1
    if not counts:
        return None
    (a, b), n = counts.most_common(1)[0]
    return a, b, n


def _calibrate_assumptions(
    base: CostingAssumptions,
    dimensions: DimensionInventory | None,
    detections: list[Detection] | None = None,
) -> tuple[CostingAssumptions, list[str]]:
    """Override assumed geometry with what the drawing declares for the
    elements themselves; sheet-wide dimension statistics only add notes."""
    calibrated = base.model_copy(deep=True)
    notes: list[str] = []
    typical = _typical_column_section(detections or [])
    if typical is not None and typical[2] >= 2:
        a, b, n = typical
        calibrated.column_section_m2 = a * b / 10_000.0
        notes.append(
            f"Sección de columna supuesta {a}x{b} cm = {calibrated.column_section_m2:.4f} m²: "
            f"la que declaran {n} columnas del plano; aplica a las que no declaran ninguna."
        )
    if dimensions is None:
        return calibrated, notes
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
    # Un catálogo de destajos cobra la mano de obra y nada más: la línea
    # sanitaria de 4" vale $61.76 de destajo y $315.59 con el tubo. Adoptar
    # uno sin decirlo deja el presupuesto corto por el material entero, así
    # que el alcance se escribe junto a la procedencia, donde se lee.
    alcance = (
        " · SÓLO MANO DE OBRA, sin materiales"
        if adopted.get("alcance") == "mano_de_obra"
        else ""
    )
    return UnitPriceAnalysis(
        concept_code=concept.code,
        concept_description=concept.description,
        unit=concept.unit,
        lines=[],
        breakdown={rt.value: 0.0 for rt in ResourceType},
        direct_unit_cost=round(float(adopted["price"]), 2),
        price_source=f"{adopted.get('source') or 'referencia'} · {adopted.get('clave') or ''}"
        f"{vigencia}{alcance}",
    )


def _warn_solo_mano_de_obra(
    boq: BillOfQuantities, apus: dict[str, UnitPriceAnalysis]
) -> None:
    """Conceptos cuyo P.U. adoptado sólo paga la mano de obra.

    Un catálogo de destajos es un precio real y citable, pero no es el precio
    del concepto: falta el material. El presupuesto suma esos renglones como
    si estuvieran completos y por eso hay que decirlo — la diferencia no es
    un matiz, en una línea sanitaria de 4 pulgadas el tubo es cinco veces la
    mano de obra."""
    afectados = [
        line for line in boq.lines
        if (apu := apus.get(line.concept_code)) is not None
        and apu.price_source
        and "SÓLO MANO DE OBRA" in apu.price_source
        and line.amount > 0
    ]
    if not afectados:
        return
    total = round(sum(line.amount for line in afectados), 2)
    claves = ", ".join(sorted(line.concept_code for line in afectados)[:6])
    boq.warnings.append(
        f"{len(afectados)} conceptos por ${total:,.2f} tienen un P.U. de destajo: pagan la "
        f"mano de obra y no el material ({claves}"
        f"{'…' if len(afectados) > 6 else ''}). El presupuesto los suma como si estuvieran "
        "completos; cárgales el material o adopta un precio unitario que lo incluya."
    )


def _warn_stale_prices(
    boq: BillOfQuantities, apus: dict[str, UnitPriceAnalysis], vigencias: dict[str, str]
) -> None:
    """The insumos this presupuesto actually prices with, older than a year
    (or undated), named in a warning — the cotización list in one line."""
    used: set[str] = set()
    for line in boq.lines:
        apu = apus.get(line.concept_code)
        if apu is None:
            continue
        for component in apu.lines:
            used.add(component.resource_code)
    stale = sorted(code for code in used if freshness(vigencias.get(code, "")) == "vencido")
    review = sorted(code for code in used if freshness(vigencias.get(code, "")) == "revisar")
    if stale:
        boq.warnings.append(
            f"{len(stale)} insumo(s) con precio de más de 12 meses o sin vigencia en este "
            f"presupuesto: {', '.join(stale[:8])}{'…' if len(stale) > 8 else ''}. "
            "Pide cotización (Catálogo → Solicitar cotización) o actualízalos por índice."
        )
    if review:
        boq.assumptions.append(
            f"{len(review)} insumo(s) con precio de 7–12 meses: {', '.join(review[:8])}"
            f"{'…' if len(review) > 8 else ''}; conviene revisarlos antes de licitar."
        )


def apply_aliases(
    catalog: list[Concept], apus: dict[str, UnitPriceAnalysis], aliases: dict[str, dict]
) -> None:
    """The taller's concept in place of ours: its clave and description on
    the line, and — for an alias to a workspace concept — its matrix as the
    price (a reference alias already adopted the row's P.U.)."""
    for concept in catalog:
        alias = aliases.get(concept.code)
        if not alias:
            continue
        concept.taller_clave = str(alias.get("clave") or "")
        if alias.get("description"):
            concept.description = str(alias["description"])
        if alias.get("kind") == "concept" and alias.get("target_code") in apus:
            source = apus[str(alias["target_code"])]
            apus[concept.code] = source.model_copy(
                update={
                    "concept_code": concept.code,
                    "concept_description": concept.description,
                    "price_source": (
                        f"matriz del taller {alias['target_code']}"
                        + (f" · {source.price_source}" if source.price_source else "")
                    ),
                }
            )
        apu = apus.get(concept.code)
        if apu is not None and apu.concept_description != concept.description:
            apus[concept.code] = apu.model_copy(
                update={"concept_description": concept.description}
            )


def _declare_schedule_basis(
    boq: BillOfQuantities, schedule: WorkSchedule, config: ScheduleConfig
) -> None:
    """Say what the programa assumed, in the register that defends it later."""
    if not schedule.activities:
        return
    from_matrix = sum(1 for a in schedule.activities if a.rendimiento_source == "matriz")
    boq.assumptions.append(
        f"Programa de obra: duraciones de {from_matrix} de {len(schedule.activities)} "
        "actividades derivadas del rendimiento de su propia matriz (RLOPSRM art. 190), "
        f"con {config.crews_per_activity} cuadrilla(s) por actividad y "
        f"{config.frentes} frente(s) de trabajo. "
        f"Plazo {schedule.total_duration_days} días hábiles = "
        f"{schedule.calendar_days} días naturales, en semana de seis días."
    )


def _integrate_with_analyses(
    direct_cost: float,
    config: CostingConfig,
    integracion_taller: dict | None,
    schedule: WorkSchedule,
    currency: str,
    warnings: list[str],
) -> tuple[list[ComponenteResuelto], CostIntegration, FinancialPlan]:
    """Integración y flujo al punto fijo.

    Sólo el financiamiento depende del flujo, y el flujo del precio de venta:
    se siembra con lo declarado y se itera. El factor de perturbación es la
    porción del financiamiento (~1–3 %), así que converge en pocas pasadas;
    el tope de 10 es un guardarraíl, y tocarlo se dice con el residual."""
    resolved = resolve_integration(config, integracion_taller, direct_cost, schedule, None)
    integration = integrate_costs(direct_cost, config.indirects, resolved=resolved)
    financial = build_financial_plan(schedule, integration, config.financial, currency)
    residual = 0.0
    for _ in range(10):
        resolved = resolve_integration(
            config, integracion_taller, direct_cost, schedule, financial
        )
        if next(c for c in resolved if c.code == "FI").fuente == "declarado":
            integration = integrate_costs(direct_cost, config.indirects, resolved=resolved)
            financial = build_financial_plan(schedule, integration, config.financial, currency)
            break
        new_integration = integrate_costs(direct_cost, config.indirects, resolved=resolved)
        new_financial = build_financial_plan(schedule, new_integration, config.financial, currency)
        residual = abs(new_integration.grand_total - integration.grand_total)
        integration, financial = new_integration, new_financial
        if residual < 0.01:
            break
    else:
        warnings.append(
            f"El costo de financiamiento no convergió tras 10 iteraciones; "
            f"residual de ${residual:,.2f} en el total con contingencia."
        )
    for comp in resolved:
        for falta in comp.faltantes:
            warnings.append(
                f"Integración ({comp.code}): {falta}. El componente sigue por "
                "porcentaje declarado."
            )
    if any(c.fuente == "analisis" for c in resolved):
        warnings.append(
            f"Utilidad declarada: {config.indirects.profit_pct:g} % — criterio "
            "del taller, no un análisis."
        )
    oficina = next(c for c in resolved if c.code == "CI-O")
    if oficina.documento.get("override") is not None:
        warnings.append(
            f"Oficina central por share fijado: {oficina.documento['override']:g} % — "
            f"{oficina.documento.get('motivo', '')}"
        )
    return resolved, integration, financial


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
    inventory: dict | None = None,
    inventory_mappings: list[dict] | None = None,
    concept_aliases: dict[str, dict] | None = None,
    parametric_rules: list[dict] | None = None,
    plantillas: list[dict] | None = None,
    price_vigencias: dict[str, str] | None = None,
    integracion_taller: dict | None = None,
) -> CostReport:
    config = config or CostingConfig()
    assumptions, calibration_notes = _calibrate_assumptions(
        config.assumptions, dimensions, detections
    )
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
    apply_aliases(catalog, apus, concept_aliases or {})
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
        segmentation=segmentation,
    )
    apply_formwork(boq, catalog, apus, formwork)
    # Pilotes: the count becomes metres when the plano declares the length.
    apply_piles(boq, catalog, apus, detections, schedule_specs)
    # Relleno y acarreo: derived from the excavation and the buried concrete.
    apply_cimentacion_earthmoving(boq, catalog, apus, assumptions)
    # Levantamiento: symbols and layers the taller mapped to concepts. Lo que
    # los detectores ya midieron no se vuelve a sumar por asignación.
    apply_inventory(
        boq, catalog, apus, inventory, inventory_mappings, ya_detectado(detections)
    )
    # Derivadas: lo que se sigue de una cantidad ya medida (aplanado sobre
    # muro, pintura sobre aplanado). Antes de los paramétricos: una deducción
    # aritmética sobre una medición gana a una apuesta desde la historia.
    aplicar_derivadas(boq, catalog, apus)
    # Paramétricos: the taller's history proposes what no plan reader produces.
    basis = compute_basis(
        detections, segmentation, units.to_meters() or 1.0, assumptions.area_construida_m2
    )
    if parametric_rules:
        apply_parametrics(boq, catalog, apus, parametric_rules, basis)
    if adjustments:
        _apply_adjustments(boq, catalog, apus, adjustments)
    if not boq.units_reliable:
        # Drawing units are not metres: nothing here may carry a price.
        for line in boq.lines:
            line.unpriced = True
            line.unit_price = 0.0
            line.amount = 0.0
        boq.direct_cost_total = 0.0
        boq.totals_by_phase = {phase: 0.0 for phase in boq.totals_by_phase}
    indicators = compute_indicators(boq, basis.area_construida_m2 or None, plantillas)
    boq.warnings.extend(indicators.notes)
    if price_vigencias is not None:
        _warn_stale_prices(boq, apus, price_vigencias)
    _warn_solo_mano_de_obra(boq, apus)
    levels = (
        max(len(segmentation.superstructure_views()), 1)
        if segmentation is not None and segmentation.is_segmented
        else 1
    )
    # The programa reads its rendimientos from the same matrices that priced
    # the obra, so the two cannot contradict each other (RLOPSRM 64-A-I-c).
    schedule = build_schedule(boq, catalog, config.schedule, levels=levels, apus=apus)
    resolved, integration, financial = _integrate_with_analyses(
        boq.direct_cost_total, config, integracion_taller, schedule,
        config.currency, boq.warnings,
    )
    indirectos_campo = next(l.amount for l in integration.lines if l.code == "CI-C")
    _declare_schedule_basis(boq, schedule, config.schedule)
    _warn_plantilla_vs_indirectos(
        boq, config, schedule, indirectos_campo,
        ci_c_fuente=next(c for c in resolved if c.code == "CI-C").fuente,
    )

    report = CostReport(
        project_id=project_id,
        currency=config.currency,
        drawing_units=units,
        boq=boq,
        # An unpriced line has no analysis to show; the presupuesto says so.
        apus=[apus[line.concept_code] for line in boq.lines if line.concept_code in apus],
        integration=integration,
        schedule=schedule,
        financial=financial,
        warnings=list(boq.warnings),
        indicators=indicators.model_dump(),
        # El programa de personal (art. 45-A-XI-d) y el número contra el que
        # tiene que cuadrar, guardados con el reporte.
        plantilla_campo=list(config.plantilla_campo),
        indirectos_campo=indirectos_campo,
        integracion_resuelta=resolved,
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


def _warn_plantilla_vs_indirectos(
    boq: BillOfQuantities,
    config: CostingConfig,
    schedule: WorkSchedule,
    indirectos_campo: float,
    ci_c_fuente: str = "declarado",
) -> None:
    """El personal que el taller planea tener contra el dinero que los
    indirectos le destinan.

    No se avisa cuando falta la plantilla: un presupuesto de obra privada no
    la necesita, y convertir eso en hallazgo sería una alarma en cada
    proyecto. Se avisa cuando la plantilla existe, está completa y no cabe en
    los indirectos — ahí el problema es real en obra pública y privada por
    igual, porque ese personal se paga con o sin formato de por medio."""
    if ci_c_fuente == "analisis":
        # En modo análisis la plantilla está dentro del desglose: no hay dos
        # números que comparar.
        return
    if not config.plantilla_campo:
        return
    period_days = schedule.workdays_per_month or 24
    periods = (
        max(1, math.ceil(schedule.total_duration_days / period_days))
        if schedule.total_duration_days
        else 0
    )
    if not periods:
        return
    programa = build_personal_tecnico(
        config.plantilla_campo, periods, period_days, "mes", indirectos_campo
    )
    desajuste = desajuste_de_indirectos(
        programa.total, indirectos_campo, programa.cargos_sin_sueldo
    )
    if desajuste is None:
        return
    direccion = "no alcanzan para pagarla" if desajuste > 0 else "sobran frente a ella"
    boq.warnings.append(
        f"La plantilla de personal de campo suma ${programa.total:,.2f} en "
        f"{periods} meses y los indirectos de campo del presupuesto "
        f"(${indirectos_campo:,.2f}, {config.indirects.field_indirects_pct:g} % del "
        f"costo directo) {direccion}: {abs(desajuste):.0f} % de diferencia."
    )


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
        line = lines_by_code.get(adjustment.concept_code)
        if adjustment.is_set:
            previous = line.quantity if line is not None else 0.0
            note = (
                f"Cantidad fijada en {adjustment.quantity_set:,.2f} {concept.unit} "
                f"(la lectura daba {previous:,.2f} {concept.unit})"
            )
        else:
            note = f"Ajuste manual {adjustment.quantity_delta:+,.2f} {concept.unit}"
        if adjustment.note:
            note += f": {adjustment.note}"
        if adjustment.actor:
            note += f" — {adjustment.actor}"

        if line is None:
            wants = adjustment.quantity_set if adjustment.is_set else adjustment.quantity_delta
            if wants is None or wants <= 0:
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

        if line.engine_quantity is None:
            line.engine_quantity = line.quantity
        new_quantity = (
            adjustment.quantity_set
            if adjustment.quantity_set is not None
            else line.quantity + adjustment.quantity_delta
        )
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
