"""Nineteen findings that differ only in a clave are one finding with a
count. Repeating four identical lines nineteen times is how a reader learns
to skim past warnings — which is the failure mode the severity tiers exist
to prevent."""

from klave_engine.costing.hallazgos import diagnose
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    CostIntegration,
    CostReport,
    FinancialPlan,
    QuantityKind,
    WorkSchedule,
)
from klave_engine.dxf.units import DrawingUnits


def _unpriced(code: str, quantity: float, unit: str) -> BoqLine:
    return BoqLine(
        concept_code=code, description=f"{code} descripción", unit=unit,
        quantity=quantity, unit_price=0.0, amount=0.0, phase="Instalación hidráulica",
        raw_quantity=quantity, raw_kind=QuantityKind.COUNT, source_detection_count=1,
        confidence=0.8, unpriced=True,
    )


def _report_with_unpriced_lines() -> CostReport:
    boq = BillOfQuantities(project_id="p")
    boq.lines = [
        _unpriced("SAN-003", 238.89, "M"),
        _unpriced("HID-007", 1.0, "PZA"),
        _unpriced("SAN-002", 167.75, "M"),
    ]
    # CostIntegration, WorkSchedule and FinancialPlan have no default values
    # for most of their fields (see models.py) — the brief's zero-arg
    # `WorkSchedule()` / `CostIntegration()` / `FinancialPlan()` raise
    # pydantic ValidationErrors before `diagnose` ever runs. Built the way
    # tests/test_hallazgos.py already builds a minimal CostReport instead.
    return CostReport(
        project_id="p", currency="MXN",
        drawing_units=DrawingUnits(unit="m", source="dxf_header", confidence=0.9),
        boq=boq, apus=[],
        integration=CostIntegration(
            direct_cost=0.0, lines=[], sale_price=0.0, contingency=0.0,
            grand_total=0.0, overcost_factor=1.0,
        ),
        schedule=WorkSchedule(
            activities=[], total_duration_days=0, workdays_per_month=24, phases=[]
        ),
        financial=FinancialPlan(
            advance_payment_pct=30.0, retention_pct=5.0, advance_payment=0.0,
            total_retention=0.0, periods=[], operating_projection=[],
            annual_operating_cost=0.0,
        ),
    )


def test_same_rule_findings_collapse_into_one_group():
    diagnostico = diagnose(_report_with_unpriced_lines())

    sin_precio = next(g for g in diagnostico.grupos if g.rule_id == "sin_precio")
    assert sin_precio.count == 3
    assert len(sin_precio.miembros) == 3
    assert "3" in sin_precio.titulo


def test_groups_rank_by_the_quantity_at_stake_not_alphabetically():
    """SAN-003 at 238 m outranks HID-007 at one pieza."""
    diagnostico = diagnose(_report_with_unpriced_lines())

    sin_precio = next(g for g in diagnostico.grupos if g.rule_id == "sin_precio")
    codes = [h.concept_code for h in sin_precio.miembros]
    assert codes[0] == "SAN-003"
    assert codes[-1] == "HID-007"


def test_a_lone_finding_still_becomes_a_group_of_one():
    """The renderer must handle every finding the same way; a special case for
    singletons is a second code path that will drift."""
    boq = BillOfQuantities(project_id="p")
    boq.lines = [_unpriced("SAN-003", 238.89, "M")]
    report = _report_with_unpriced_lines()
    report.boq = boq

    diagnostico = diagnose(report)

    sin_precio = next(g for g in diagnostico.grupos if g.rule_id == "sin_precio")
    assert sin_precio.count == 1


def test_different_engine_warnings_do_not_merge_under_one_group():
    """`sin_precio:{code}` and `motor:{key}` both carry a colon, but they are
    not the same kind of id. `sin_precio` names one rule repeated once per
    unpriced line — the suffix is only which line, so collapsing on the
    prefix is exactly right. `motor` is a namespace for every engine-prose
    warning regardless of which rule produced it: the free-text loop in
    `diagnose` has already collapsed repeats of *one* family into a single
    Hallazgo before this ever runs, so two distinct `motor:` findings share
    only that namespace, never a rule. Grouping on the bare "motor" prefix
    would merge a bloqueante finding and a dinero finding under one card and
    one severity — hiding whichever one is not `primero`, which is the exact
    failure (severity swallowed by a wall of sameness) this task exists to
    fix, just introduced a second time by the grouping code itself."""
    report = _report_with_unpriced_lines()
    report.boq.warnings = [
        "CIM-002: El plano declara f'c=300; el concepto costea f'c=250. "
        "Ajusta el concepto o su matriz.",
        "3 elementos con acero no cuantificado en su detalle.",
    ]

    diagnostico = diagnose(report)

    rule_ids = [g.rule_id for g in diagnostico.grupos]
    assert "motor" not in rule_ids

    by_rule = {g.rule_id: g for g in diagnostico.grupos}
    fc = by_rule["motor:fc_menor_al_plano"]
    acero = by_rule["motor:acero_sin_cuantificar"]
    assert fc.severity == "bloqueante"
    assert acero.severity == "dinero"
    assert fc.count == 1
    assert acero.count == 1
