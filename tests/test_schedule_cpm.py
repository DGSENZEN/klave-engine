"""Programa de obra: durations that agree with the matrices that priced the
obra, an explicit network, and holguras that mean something."""

from klave_engine.costing.apu import build_all_apus
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import (
    ApuLine,
    BillOfQuantities,
    BoqLine,
    Concept,
    CostingAssumptions,
    QuantityKind,
    ResourceType,
    ScheduleConfig,
    UnitPriceAnalysis,
)
from klave_engine.costing.schedule import (
    HOURS_PER_JOURNEY,
    build_schedule,
    crew_of,
    quantity_by_period,
    rendimiento_from_apu,
)


def _apu(code: str, *lines: tuple[str, str, float, ResourceType]) -> UnitPriceAnalysis:
    return UnitPriceAnalysis(
        concept_code=code, concept_description=code, unit="M3",
        lines=[
            ApuLine(
                resource_code=rc, description=rc, unit=unit, quantity=qty,
                unit_cost=100.0, amount=qty * 100.0, resource_type=kind,
            )
            for rc, unit, qty, kind in lines
        ],
        breakdown={}, direct_unit_cost=1000.0,
    )


def test_rendimiento_comes_from_the_matrix_crew_days():
    """A matrix spending 0.45 crew-journeys per m³ states R = 2.22 m³/day —
    the same R that produced its labour cost (RLOPSRM art. 190)."""
    apu = _apu(
        "CIM-002",
        ("MAT-CONC250", "M3", 1.05, ResourceType.material),
        ("MO-CUAD-ALB", "JOR", 0.45, ResourceType.labor),
    )
    assert abs(rendimiento_from_apu(apu) - 1 / 0.45) < 1e-9


def test_machine_paced_work_reads_effective_hours_not_journeys():
    """Art. 194 states machinery rendimiento per effective hour. Treating an
    hourly figure as a daily one is the mistake that makes a programa
    contradict its own matrices."""
    apu = _apu(
        "CIM-001",
        ("EQ-RETRO", "HR", 0.25, ResourceType.equipment),
    )
    assert rendimiento_from_apu(apu) == HOURS_PER_JOURNEY / 0.25  # 32 m³/day
    # No crew and no machine: nothing to read, the caller falls back.
    assert rendimiento_from_apu(_apu("X", ("MAT-A", "M3", 1.0, ResourceType.material))) is None
    assert rendimiento_from_apu(None) is None


def test_the_crew_comes_from_the_matrix_biggest_labour_line():
    apu = _apu(
        "EST-001",
        ("MO-AYUD", "JOR", 0.1, ResourceType.labor),
        ("MO-CUAD-ALB", "JOR", 0.9, ResourceType.labor),
    )
    assert crew_of(apu) == "MO-CUAD-ALB"
    assert crew_of(_apu("X", ("MAT-A", "M3", 1.0, ResourceType.material))) == ""


def _concept(code: str, order: int, rate: float = 10.0, phase: str = "Cimentación") -> Concept:
    return Concept(
        code=code, description=code, unit="M3", phase=phase,
        production_rate_per_day=rate, sequence_order=order,
    )


def _boq(*pairs: tuple[str, float], phase: str = "Cimentación") -> BillOfQuantities:
    return BillOfQuantities(
        project_id="p",
        lines=[
            BoqLine(
                concept_code=code, description=code, unit="M3", quantity=qty,
                unit_price=100.0, amount=qty * 100.0, phase=phase,
                raw_quantity=qty, raw_kind=QuantityKind.VOLUME,
                source_detection_count=1, confidence=0.9,
            )
            for code, qty in pairs
        ],
    )


def test_the_matrix_beats_the_stored_rate_and_says_which_it_used():
    """The stored rate is a second number that can disagree with the money;
    when the matrix has one, it wins, and the activity records that."""
    boq = _boq(("CIM-002", 100.0))
    catalog = [_concept("CIM-002", 1, rate=5.0)]
    apus = {"CIM-002": _apu("CIM-002", ("MO-CUAD-ALB", "JOR", 0.5, ResourceType.labor))}

    with_matrix = build_schedule(boq, catalog, ScheduleConfig(), apus=apus).activities[0]
    assert with_matrix.rendimiento_per_day == 2.0  # 1 / 0.5, not the stored 5.0
    assert with_matrix.rendimiento_source == "matriz"
    assert with_matrix.duration_days == 50  # 100 m³ ÷ 2 per day

    without = build_schedule(boq, catalog, ScheduleConfig()).activities[0]
    assert without.rendimiento_per_day == 5.0
    assert without.rendimiento_source == "catálogo"
    assert without.duration_days == 20


def test_work_sharing_a_crew_queues_and_different_crews_run_in_parallel():
    boq = _boq(("A-001", 40.0), ("A-002", 40.0))
    catalog = [_concept("A-001", 1, rate=10.0), _concept("A-002", 1, rate=10.0)]
    shared = {
        "A-001": _apu("A-001", ("MO-CUAD-ALB", "JOR", 0.1, ResourceType.labor)),
        "A-002": _apu("A-002", ("MO-CUAD-ALB", "JOR", 0.1, ResourceType.labor)),
    }
    split = {
        "A-001": _apu("A-001", ("MO-CUAD-ALB", "JOR", 0.1, ResourceType.labor)),
        "A-002": _apu("A-002", ("MO-CUAD-CARP", "JOR", 0.1, ResourceType.labor)),
    }
    config = ScheduleConfig(intra_phase_overlap_pct=0.0)

    queued = build_schedule(boq, catalog, config, apus=shared)
    assert [a.start_day for a in queued.activities] == [0, 4]  # one crew: it waits
    assert queued.activities[1].predecessors[0].predecessor == "A-001"

    parallel = build_schedule(boq, catalog, config, apus=split)
    assert [a.start_day for a in parallel.activities] == [0, 0]  # two crews: together
    assert parallel.total_duration_days < queued.total_duration_days


def test_a_trade_step_waits_for_the_one_before_it():
    """Excavación before zapatas: the catálogo's sequence_order is physical
    precedence, so a later step never starts on day zero beside an earlier one."""
    boq = _boq(("CIM-001", 20.0), ("CIM-002", 20.0))
    catalog = [_concept("CIM-001", 0, rate=10.0), _concept("CIM-002", 1, rate=10.0)]
    apus = {  # different crews, so only precedence can separate them
        "CIM-001": _apu("CIM-001", ("MO-PEON", "JOR", 0.1, ResourceType.labor)),
        "CIM-002": _apu("CIM-002", ("MO-CUAD-ALB", "JOR", 0.1, ResourceType.labor)),
    }
    schedule = build_schedule(
        boq, catalog, ScheduleConfig(intra_phase_overlap_pct=0.0), apus=apus
    )
    excavacion, zapatas = schedule.activities
    assert excavacion.start_day == 0
    assert zapatas.start_day >= excavacion.duration_days
    assert zapatas.predecessors[0].predecessor == "CIM-001"


def test_holgura_and_the_critical_path_fall_out_of_the_network():
    """A short chain beside a long one has slack; the long one has none."""
    boq = _boq(("LARGA", 100.0), ("CORTA", 10.0))
    catalog = [_concept("LARGA", 1, rate=1.0), _concept("CORTA", 1, rate=1.0)]
    apus = {
        "LARGA": _apu("LARGA", ("MO-CUAD-ALB", "JOR", 1.0, ResourceType.labor)),
        "CORTA": _apu("CORTA", ("MO-CUAD-CARP", "JOR", 1.0, ResourceType.labor)),
    }
    schedule = build_schedule(boq, catalog, ScheduleConfig(), apus=apus)
    larga = next(a for a in schedule.activities if a.concept_code == "LARGA")
    corta = next(a for a in schedule.activities if a.concept_code == "CORTA")
    assert larga.critical and larga.total_float_days == 0
    assert not corta.critical
    assert corta.total_float_days == 90  # 100 days of obra, 10 of work
    assert corta.free_float_days <= corta.total_float_days
    assert schedule.critical_path == ["LARGA"]


def test_the_plazo_is_reported_in_natural_days_too():
    """LOPSRM art. 31 fr. V: the contract's plazo is in días naturales, and a
    six-day site week means those are not the same number."""
    boq = _boq(("A-001", 60.0))
    catalog = [_concept("A-001", 1, rate=1.0)]
    plain = build_schedule(boq, catalog, ScheduleConfig())
    assert plain.total_duration_days == 60
    assert plain.calendar_days == 70  # 60 working days on a six-day week

    dated = build_schedule(boq, catalog, ScheduleConfig(start_date="2026-09-01"))
    assert dated.start_date == "2026-09-01"
    assert dated.calendar_days == 70
    assert dated.end_date is not None


def test_quantities_spread_over_the_periods_they_run_in():
    boq = _boq(("A-001", 48.0))
    catalog = [_concept("A-001", 1, rate=1.0)]
    schedule = build_schedule(boq, catalog, ScheduleConfig(workdays_per_month=24))
    rows = quantity_by_period(schedule)
    assert rows["A-001"] == [24.0, 24.0]  # 48 m³ over two months of 24 days
    assert sum(rows["A-001"]) == 48.0


def test_the_default_catalog_now_agrees_with_its_own_matrices():
    """The regression this whole change exists for: 26 of 27 concepts had a
    stored rate that contradicted the matrix pricing them."""
    assumptions = CostingAssumptions()
    catalog = build_default_catalog(assumptions)
    apus = build_all_apus(catalog)
    boq = _boq(*[(c.code, 10.0) for c in catalog if c.code in apus], phase="Cimentación")
    for line in boq.lines:  # keep each line in its concept's real phase
        line.phase = next(c.phase for c in catalog if c.code == line.concept_code)
    schedule = build_schedule(boq, catalog, ScheduleConfig(), apus=apus)
    from_matrix = [a for a in schedule.activities if a.rendimiento_source == "matriz"]
    assert len(from_matrix) > 20
    for activity in from_matrix:
        expected = rendimiento_from_apu(apus[activity.concept_code])
        assert abs(activity.rendimiento_per_day - round(expected, 4)) < 1e-6
