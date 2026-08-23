"""The programa on the calendar: working days become dates when the obra
declares its start, on a six-day site week."""

from datetime import date

from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.models import (
    BillOfQuantities,
    BoqLine,
    CostingAssumptions,
    QuantityKind,
    ScheduleConfig,
)
from klave_engine.costing.schedule import _calendar_date, build_schedule


def _boq():
    boq = BillOfQuantities(project_id="p")
    boq.lines = [BoqLine(
        concept_code="EST-004", description="Muros", unit="M2", quantity=270.0,
        unit_price=350.0, amount=94500.0, phase="Estructura", raw_quantity=100.0,
        raw_kind=QuantityKind.LENGTH, source_detection_count=1, confidence=0.9,
    )]
    return boq


def test_calendar_dates_skip_sundays():
    start = date(2026, 9, 5)  # a Saturday
    assert _calendar_date(start, 0) == date(2026, 9, 5)
    assert _calendar_date(start, 1) == date(2026, 9, 7)  # Sunday skipped
    assert _calendar_date(start, 7) == date(2026, 9, 14)  # a full week + 1
    assert _calendar_date(date(2026, 9, 6), 0) == date(2026, 9, 7)  # Sunday start → Monday


def test_schedule_carries_dates_only_with_a_start_date():
    catalog = build_default_catalog(CostingAssumptions())
    plain = build_schedule(_boq(), catalog, ScheduleConfig())
    assert plain.start_date is None and all(a.start_date is None for a in plain.activities)
    dated = build_schedule(_boq(), catalog, ScheduleConfig(start_date="2026-09-01"))
    assert dated.start_date == "2026-09-01" and dated.end_date is not None
    activity = dated.activities[0]
    assert activity.start_date == "2026-09-01"
    assert activity.end_date is not None and activity.end_date > activity.start_date
    bad = build_schedule(_boq(), catalog, ScheduleConfig(start_date="pronto"))
    assert bad.start_date is None
