"""Programa de obra: activity durations from production rates, phased timeline,
and the direct-cost spend per period (programa de erogaciones)."""

import math
from collections import defaultdict

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
) -> WorkSchedule:
    concepts = {c.code: c for c in catalog}
    phases_present = [
        phase for phase in PHASE_ORDER if any(line.phase == phase for line in boq.lines)
    ]

    activities: list[ScheduleActivity] = []
    phase_start = 0
    for phase in phases_present:
        phase_lines = [line for line in boq.lines if line.phase == phase]
        phase_duration = 0
        for line in phase_lines:
            concept = concepts[line.concept_code]
            rate = concept.production_rate_per_day * max(config.crews_per_activity, 1)
            duration = max(1, math.ceil(line.quantity / rate))
            activities.append(
                ScheduleActivity(
                    concept_code=line.concept_code,
                    description=line.description,
                    phase=phase,
                    quantity=line.quantity,
                    unit=line.unit,
                    duration_days=duration,
                    start_day=phase_start,
                    end_day=phase_start + duration,
                    direct_cost=line.amount,
                )
            )
            phase_duration = max(phase_duration, duration)
        # Next phase fast-tracks: it starts before this one fully ends.
        overlap = config.phase_overlap_pct / 100.0
        phase_start += max(1, math.ceil(phase_duration * (1.0 - overlap)))

    total_duration = max((a.end_day for a in activities), default=0)
    return WorkSchedule(
        activities=activities,
        total_duration_days=total_duration,
        workdays_per_month=config.workdays_per_month,
        phases=phases_present,
    )


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
