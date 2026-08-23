"""Programa de obra: activity durations from production rates, phased timeline,
and the direct-cost spend per period (programa de erogaciones)."""

import math
from collections import defaultdict
from datetime import date, timedelta

from klave_engine.costing.catalog import PHASE_ORDER
from klave_engine.costing.models import (
    BillOfQuantities,
    Concept,
    ScheduleActivity,
    ScheduleConfig,
    WorkSchedule,
)


def build_schedule(
    boq: BillOfQuantities,
    catalog: list[Concept],
    config: ScheduleConfig,
    levels: int = 1,
) -> WorkSchedule:
    """Programa de obra with realistic sequencing.

    Each activity's duration comes from its rendimiento (units/crew/day).
    Within a phase, trades follow each other (intra-phase overlap) instead of
    running fully in parallel; phases fast-track onto the previous one. The
    structure phase cannot be compressed below one cycle per building level.
    """
    concepts = {c.code: c for c in catalog}
    crews = max(config.crews_per_activity, 1)
    intra_overlap = config.intra_phase_overlap_pct / 100.0
    phase_overlap = config.phase_overlap_pct / 100.0

    phases_present = [
        phase for phase in PHASE_ORDER if any(line.phase == phase for line in boq.lines)
    ]

    activities: list[ScheduleActivity] = []
    phase_start = 0
    for phase in phases_present:
        phase_lines = sorted(
            (line for line in boq.lines if line.phase == phase),
            key=lambda line: concepts[line.concept_code].sequence_order,
        )
        cursor = phase_start  # start day of the activity currently being placed
        phase_end = phase_start
        prev_duration = 0
        for index, line in enumerate(phase_lines):
            concept = concepts[line.concept_code]
            rate = concept.production_rate_per_day * crews
            duration = max(1, math.ceil(line.quantity / rate))
            if index > 0:
                cursor = cursor + max(1, math.ceil(prev_duration * (1.0 - intra_overlap)))
            activities.append(
                ScheduleActivity(
                    concept_code=line.concept_code,
                    description=line.description,
                    phase=phase,
                    quantity=line.quantity,
                    unit=line.unit,
                    rendimiento_per_day=concept.production_rate_per_day,
                    crews=crews,
                    duration_days=duration,
                    start_day=cursor,
                    end_day=cursor + duration,
                    direct_cost=line.amount,
                )
            )
            prev_duration = duration
            phase_end = max(phase_end, cursor + duration)

        # The structure phase respects a minimum cycle per building level.
        if phase == "Estructura" and levels > 1:
            floor_end = phase_start + levels * config.per_level_cycle_days
            if floor_end > phase_end:
                _stretch_phase(activities, phase, phase_start, phase_end, floor_end)
                phase_end = floor_end

        phase_span = phase_end - phase_start
        phase_start += max(1, math.ceil(phase_span * (1.0 - phase_overlap)))

    total_duration = max((a.end_day for a in activities), default=0)
    schedule = WorkSchedule(
        activities=activities,
        total_duration_days=total_duration,
        workdays_per_month=config.workdays_per_month,
        phases=phases_present,
    )
    _apply_calendar(schedule, config.start_date)
    return schedule


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
    """Working days become calendar dates when the obra has a start date."""
    if not start_date:
        return
    try:
        start = date.fromisoformat(start_date[:10])
    except ValueError:
        return
    schedule.start_date = start.isoformat()
    for activity in schedule.activities:
        activity.start_date = _calendar_date(start, activity.start_day).isoformat()
        activity.end_date = _calendar_date(start, activity.end_day).isoformat()
    schedule.end_date = _calendar_date(start, schedule.total_duration_days).isoformat()


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
