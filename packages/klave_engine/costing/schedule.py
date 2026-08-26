"""Programa de obra: a real activity network, not a bar chart drawn from
guesses.

Three things this module is careful about, all of them because a Mexican
convocante checks exactly these:

**The rendimiento comes from the matrix.** RLOPSRM art. 190 defines the
rendimiento as the quantity a crew installs in an eight-hour day, and it is
the very number the labour cost is built on (``Mo = Sr / R``). So the
duration is derived from the APU's own crew-days per unit rather than from
a second figure stored beside it. When those two disagree, the programa and
the presupuesto contradict each other — and RLOPSRM art. 64-A-I-c) asks the
reviewer to check precisely that the programs are "congruentes con los
consumos y rendimientos considerados". Congruence here is structural: there
is one number, used twice.

**The network is explicit.** Art. 224 asks for activities with their
duration, their sequence, the relations to what precedes and follows them,
and the resulting early dates, late dates and *holguras*. Overlap between
trades is therefore modelled as a start-to-start relation with a lag —
which is what a traslape actually is — instead of a global percentage
applied after the fact.

**Working days and calendar days are different units.** Durations are
computed in eight-hour journeys on a six-day site week; the contract speaks
in días naturales (LOPSRM art. 31 fr. V). Reporting the first as the second
understates the plazo by about a fifth, so both are carried.
"""

import math
from collections import defaultdict
from datetime import date, timedelta

from klave_engine.costing.catalog import PHASE_ORDER
from klave_engine.costing.models import (
    DERIVADO_DE,
    BillOfQuantities,
    Concept,
    ResourceType,
    ScheduleActivity,
    ScheduleConfig,
    ScheduleLink,
    UnitPriceAnalysis,
    WorkSchedule,
)

# The pairs that genuinely cannot overlap, derived from the same map that
# orders them. Everything else stays start-to-start with a lag, because
# traslape between trades is how obra actually runs — flattening that would
# replace one wrong model with another.
HARD_PREDECESSORS: dict[str, tuple[str, ...]] = {}
for _derived, (_parent, _tipo) in DERIVADO_DE.items():
    HARD_PREDECESSORS[_parent] = (*HARD_PREDECESSORS.get(_parent, ()), _derived)

# Units that mean "one crew for one journey" in a matrix (art. 190: R is
# per eight-hour journey) and "one machine for one hour" (art. 194: Rhm is
# per effective hour). Dividing an hourly rate as if it were daily — the
# mistake behind most incongruent programas — is what these two lists exist
# to keep apart.
_JOURNEY_UNITS = ("JOR", "JORNADA", "JOR.", "DIA", "DÍA")
_HOUR_UNITS = ("HR", "HRA", "HORA", "H", "HH")
HOURS_PER_JOURNEY = 8.0


def crew_of(apu: UnitPriceAnalysis | None) -> str:
    """The cuadrilla a concept occupies, read from its matrix.

    This is the only genuine source of parallelism Klave has: a crew can only
    be in one place at a time, so two concepts that share one must queue,
    while concepts on different crews can run side by side. Deriving it from
    the matrix keeps the programa honest — no invented dependency graph, just
    the resource the price analysis already says the work consumes."""
    if apu is None:
        return ""
    labor = [line for line in apu.lines if line.resource_type == ResourceType.labor]
    if not labor:
        return ""
    return max(labor, key=lambda line: line.amount).resource_code


def rendimiento_from_apu(apu: UnitPriceAnalysis | None) -> float | None:
    """Concept units per crew per day, read from the matrix that prices it.

    A matrix that spends 0.45 crew-journeys per m³ is stating a rendimiento
    of 1/0.45 = 2.22 m³ per day; that is the same R that produced its labour
    cost (RLOPSRM art. 190). When no crew line carries a journey, the work is
    machine-paced and the rate comes from the equipment's effective hours
    instead (art. 194), converted to a journey of eight hours.

    Returns None when neither exists — an adopted P.U., or a concept that is
    pure material — and the caller falls back to the catálogo's stored rate."""
    if apu is None:
        return None
    journeys = sum(
        line.quantity
        for line in apu.lines
        if line.resource_type == ResourceType.labor
        and line.unit.strip().upper() in _JOURNEY_UNITS
    )
    if journeys > 0:
        return 1.0 / journeys
    hours = sum(
        line.quantity
        for line in apu.lines
        if line.resource_type == ResourceType.equipment
        and line.unit.strip().upper() in _HOUR_UNITS
    )
    if hours > 0:
        return HOURS_PER_JOURNEY / hours
    return None


def build_schedule(
    boq: BillOfQuantities,
    catalog: list[Concept],
    config: ScheduleConfig,
    levels: int = 1,
    apus: dict[str, UnitPriceAnalysis] | None = None,
) -> WorkSchedule:
    """Programa de obra with realistic sequencing and a computed critical path.

    Each activity's duration comes from its rendimiento — the matrix's own
    when it has one, the catálogo's otherwise. Within a phase, trades follow
    each other with an overlap expressed as a start-to-start lag; phases
    fast-track onto the previous one the same way. The structure phase cannot
    be compressed below one cycle per building level.
    """
    concepts = {c.code: c for c in catalog}
    # Cuadrillas por actividad y frentes se multiplican: tres frentes con una
    # cuadrilla cada uno rinden lo mismo que tres cuadrillas en un frente,
    # mientras haya obra donde ponerlas.
    frentes = max(config.frentes, 1)
    crews = max(config.crews_per_activity, 1) * frentes
    intra_overlap = config.intra_phase_overlap_pct / 100.0
    phase_overlap = config.phase_overlap_pct / 100.0

    phases_present = [
        phase for phase in PHASE_ORDER if any(line.phase == phase for line in boq.lines)
    ]

    activities: list[ScheduleActivity] = []
    phase_start = 0
    # The activity the next phase hangs off: the previous phase's last one to
    # finish. Anchoring on the phase's *first* activity instead would leave
    # its tail with no successor, and CPM would hand that tail the whole
    # project's slack — "you may delay the foundation formwork by a year".
    previous_anchor: ScheduleActivity | None = None
    for phase in phases_present:
        phase_lines = sorted(
            (line for line in boq.lines if line.phase == phase),
            key=lambda line: concepts[line.concept_code].sequence_order,
        )
        phase_end = phase_start
        # Two constraints decide when work can start, and both come from data
        # the taller already has rather than from an invented graph:
        #   · trade precedence — the catálogo's sequence_order says excavación
        #     comes before zapatas, which come before contratrabes;
        #   · crew contention — the matrix names the cuadrilla, and one crew
        #     cannot be in two places, so work sharing it queues.
        # Holgura is what falls out of the second: parallel crews give the
        # shorter chains slack against the longest one.
        tail: dict[str, tuple[str, int, int]] = {}  # crew → (code, start, duration)
        step_anchor: ScheduleActivity | None = None  # last of the previous trade step
        pending_step: list[ScheduleActivity] = []
        current_order: int | None = None
        for line in phase_lines:
            concept = concepts[line.concept_code]
            if current_order is not None and concept.sequence_order != current_order:
                if pending_step:
                    step_anchor = max(pending_step, key=lambda a: (a.end_day, a.start_day))
                pending_step = []
            current_order = concept.sequence_order
            apu = (apus or {}).get(line.concept_code)
            from_apu = rendimiento_from_apu(apu)
            rate_per_crew = from_apu if from_apu else concept.production_rate_per_day
            source = "matriz" if from_apu else "catálogo"
            rate = max(rate_per_crew, 1e-9) * crews
            duration = max(1, math.ceil(line.quantity / rate))
            crew = crew_of(apu) or line.concept_code  # no crew: its own queue
            links: list[ScheduleLink] = []
            cursor = phase_start
            if step_anchor is not None:
                lag = max(1, math.ceil(step_anchor.duration_days * (1.0 - intra_overlap)))
                cursor = max(cursor, step_anchor.start_day + lag)
                links.append(
                    ScheduleLink(
                        predecessor=step_anchor.concept_code, kind="SS", lag_days=lag
                    )
                )
            previous = tail.get(crew)
            if previous is not None:
                prev_code, prev_start, prev_duration = previous
                crew_lag = max(1, math.ceil(prev_duration * (1.0 - intra_overlap)))
                crew_start = prev_start + crew_lag
                if crew_start >= cursor:
                    cursor = crew_start
                links.append(
                    ScheduleLink(predecessor=prev_code, kind="SS", lag_days=crew_lag)
                )
            if not links and previous_anchor is not None:
                # Fast-track: this phase starts before the previous one ends,
                # expressed as a start-to-start lag off that phase's last
                # activity — which is what a traslape actually is.
                links.append(
                    ScheduleLink(
                        predecessor=previous_anchor.concept_code,
                        kind="SS",
                        lag_days=max(0, cursor - previous_anchor.start_day),
                    )
                )
            for hard_code in HARD_PREDECESSORS.get(line.concept_code, ()):
                placed = next(
                    (a for a in activities if a.concept_code == hard_code), None
                )
                if placed is None:
                    continue
                cursor = max(cursor, placed.end_day)
                links.append(
                    ScheduleLink(predecessor=hard_code, kind="FS", lag_days=0)
                )
            # Same predecessor can reach here via two branches above; see
            # _dedupe_links for why the collision is resolved by lag size.
            links = _dedupe_links(links)
            activities.append(
                ScheduleActivity(
                    concept_code=line.concept_code,
                    description=line.description,
                    phase=phase,
                    quantity=line.quantity,
                    unit=line.unit,
                    rendimiento_per_day=round(rate_per_crew, 4),
                    rendimiento_source=source,
                    crews=crews,  # ya multiplicado por los frentes
                    duration_days=duration,
                    start_day=cursor,
                    end_day=cursor + duration,
                    predecessors=links,
                    direct_cost=line.amount,
                )
            )
            tail[crew] = (line.concept_code, cursor, duration)
            pending_step.append(activities[-1])
            phase_end = max(phase_end, cursor + duration)

        # The structure phase respects a minimum cycle per building level.
        if phase == "Estructura" and levels > 1:
            floor_end = phase_start + levels * config.per_level_cycle_days
            if floor_end > phase_end:
                _stretch_phase(activities, phase, phase_start, phase_end, floor_end)
                phase_end = floor_end

        phase_span = phase_end - phase_start
        phase_codes = {line.concept_code for line in phase_lines}
        in_phase = [a for a in activities if a.concept_code in phase_codes]
        if in_phase:
            previous_anchor = max(in_phase, key=lambda a: (a.end_day, a.start_day))
        phase_start += max(1, math.ceil(phase_span * (1.0 - phase_overlap)))

    total_duration = max((a.end_day for a in activities), default=0)
    schedule = WorkSchedule(
        activities=activities,
        total_duration_days=total_duration,
        workdays_per_month=config.workdays_per_month,
        phases=phases_present,
    )
    schedule.assumptions.append(
        f"{frentes} frente(s) de trabajo con {max(config.crews_per_activity, 1)} "
        "cuadrilla(s) por actividad. Es el supuesto que más mueve el plazo y el "
        "plano no puede decirlo: ajústalo si la obra tendrá más frentes."
    )
    _compute_float(schedule)
    _apply_calendar(schedule, config.start_date)
    return schedule


def _dedupe_links(links: list[ScheduleLink]) -> list[ScheduleLink]:
    """Collapse links that state the same constraint twice.

    The step anchor and the crew tail are frequently the same concept, and
    each branch that can propose a link appends its own — so a link is kept
    per distinct ``(predecessor, kind)``, not per branch. When two links do
    collide, the larger lag wins: for a start-to-start relation both
    constraints apply at once, so the true bound is their max and the
    smaller lag is redundant."""
    deduped: dict[tuple[str, str], ScheduleLink] = {}
    for link in links:
        key = (link.predecessor, link.kind)
        current = deduped.get(key)
        if current is None or link.lag_days > current.lag_days:
            deduped[key] = link
    return list(deduped.values())


def _compute_float(schedule: WorkSchedule) -> None:
    """Backward pass over the network: late dates, holgura total and libre,
    and the critical path that falls out of them (RLOPSRM art. 224).

    The forward pass already happened while placing the activities, so the
    early dates are theirs; this walks the same edges in reverse."""
    if not schedule.activities:
        return
    by_code = {a.concept_code: a for a in schedule.activities}
    successors: dict[str, list[tuple[str, ScheduleLink]]] = defaultdict(list)
    for activity in schedule.activities:
        for link in activity.predecessors:
            successors[link.predecessor].append((activity.concept_code, link))

    project_end = schedule.total_duration_days
    for activity in reversed(schedule.activities):
        outgoing = successors.get(activity.concept_code, [])
        if not outgoing:
            activity.late_finish_day = project_end
        else:
            limits = []
            for succ_code, link in outgoing:
                successor = by_code[succ_code]
                if link.kind == "SS":
                    # The successor may start `lag` after this one starts, so
                    # this one may start at most that much before it does.
                    limits.append(successor.late_start_day - link.lag_days + activity.duration_days)
                else:  # FS
                    limits.append(successor.late_start_day - link.lag_days)
            activity.late_finish_day = min(limits)
        activity.late_start_day = activity.late_finish_day - activity.duration_days
        activity.total_float_days = max(0, activity.late_start_day - activity.start_day)

    for activity in schedule.activities:
        outgoing = successors.get(activity.concept_code, [])
        if not outgoing:
            activity.free_float_days = max(0, project_end - activity.end_day)
        else:
            slack = []
            for succ_code, link in outgoing:
                successor = by_code[succ_code]
                if link.kind == "SS":
                    slack.append(successor.start_day - link.lag_days - activity.start_day)
                else:
                    slack.append(successor.start_day - link.lag_days - activity.end_day)
            activity.free_float_days = max(0, min(slack))
        # Free float is by definition bounded by total float; never let a
        # rounding in the network hand out more slack than the path allows.
        activity.free_float_days = min(activity.free_float_days, activity.total_float_days)
        activity.critical = activity.total_float_days == 0


def _calendar_date(start: date, workday: int) -> date:
    """The calendar date of the Nth working day from the start, on a six-day
    site week (Sundays off — 24 workdays a month)."""
    current = start
    remaining = max(workday, 0)
    while current.weekday() == 6:  # a start on Sunday begins Monday
        current += timedelta(days=1)
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() != 6:
            remaining -= 1
    return current


def _apply_calendar(schedule: WorkSchedule, start_date: str | None) -> None:
    """Working days become calendar dates when the obra has a start date, and
    the plazo in días naturales — the unit the contract uses — comes with it."""
    if not start_date:
        # Without a start date the six-day week still lets us state the plazo
        # honestly: six working days span seven natural ones.
        schedule.calendar_days = math.ceil(schedule.total_duration_days * 7 / 6)
        return
    try:
        start = date.fromisoformat(start_date[:10])
    except ValueError:
        return
    schedule.start_date = start.isoformat()
    for activity in schedule.activities:
        activity.start_date = _calendar_date(start, activity.start_day).isoformat()
        activity.end_date = _calendar_date(start, activity.end_day).isoformat()
    end = _calendar_date(start, schedule.total_duration_days)
    schedule.end_date = end.isoformat()
    schedule.calendar_days = (end - start).days


def _stretch_phase(
    activities: list[ScheduleActivity],
    phase: str,
    phase_start: int,
    phase_end: int,
    target_end: int,
) -> None:
    """Scale a phase's activity timeline to span up to target_end (per-level floor)."""
    span = max(phase_end - phase_start, 1)
    scale = (target_end - phase_start) / span
    for activity in activities:
        if activity.phase != phase:
            continue
        activity.start_day = phase_start + round((activity.start_day - phase_start) * scale)
        activity.duration_days = max(1, round(activity.duration_days * scale))
        activity.end_day = activity.start_day + activity.duration_days


def direct_spend_by_period(schedule: WorkSchedule) -> list[float]:
    """Uniformly spread each activity's direct cost over its working days,
    bucketed into periods of ``workdays_per_month`` days."""
    if schedule.total_duration_days == 0:
        return []
    period_count = math.ceil(schedule.total_duration_days / schedule.workdays_per_month)
    spend: defaultdict[int, float] = defaultdict(float)
    for activity in schedule.activities:
        daily = activity.direct_cost / max(activity.duration_days, 1)
        for day in range(activity.start_day, activity.end_day):
            spend[day // schedule.workdays_per_month] += daily
    return [round(spend.get(i, 0.0), 2) for i in range(period_count)]


def quantity_by_period(schedule: WorkSchedule) -> dict[str, list[float]]:
    """Each activity's quantity spread over the periods it runs in — the
    calendarised physical progress the erogación programs are built from."""
    if schedule.total_duration_days == 0:
        return {}
    period_count = math.ceil(schedule.total_duration_days / schedule.workdays_per_month)
    out: dict[str, list[float]] = {}
    for activity in schedule.activities:
        row = [0.0] * period_count
        per_day = activity.quantity / max(activity.duration_days, 1)
        for day in range(activity.start_day, activity.end_day):
            index = min(day // schedule.workdays_per_month, period_count - 1)
            row[index] += per_day
        out[activity.concept_code] = [round(v, 4) for v in row]
    return out
