"""One authority decides whether a number may be shown as money. This is
that authority's truth table — including the legacy runs written before the
verdict existed, which must not be readable as money."""

from datetime import UTC, datetime

import pytest
from klave_engine.costing.models import BillOfQuantities, BoqLine, QuantityKind
from klave_engine.costing.presentation import (
    LEGACY_REASON,
    MoneyBasis,
    basis_reasons,
    money_basis_from_boq,
    resolve_money_state,
)
from klave_engine.costing.reviews import VerificationState
from klave_engine.dxf.units import DrawingUnits

CONFIRMED = VerificationState(units_confirmed_at=datetime.now(UTC), units_confirmed_by="ing")
UNCONFIRMED = VerificationState()


def basis(*, reliable=True, unit="m", source="dxf_header", confidence=0.9) -> MoneyBasis:
    return MoneyBasis(
        units_reliable=reliable, unit=unit, source=source, confidence=confidence,
        reasons=[], confidence_bands={},
    )


@pytest.mark.parametrize(
    "given, verification, expected",
    [
        # The engine priced nothing: no sign-off can turn that into money.
        (basis(reliable=False, unit="drawing_units", source="unknown", confidence=0.0),
         CONFIRMED, "blocked"),
        (basis(reliable=False), UNCONFIRMED, "blocked"),
        # Read with confidence but nobody signed: money with the banner.
        (basis(), UNCONFIRMED, "unverified"),
        (basis(), CONFIRMED, "ok"),
        # A lone weak heuristic is a suggestion, not a scale.
        (basis(source="text_height_heuristic", confidence=0.4), UNCONFIRMED, "blocked"),
        # ...until a person confirms it, which is exactly what sign-off is for.
        (basis(source="text_height_heuristic", confidence=0.4), CONFIRMED, "ok"),
        # A run written before money_basis existed carries no verdict at all.
        (None, UNCONFIRMED, "blocked"),
        (None, CONFIRMED, "blocked"),
    ],
)
def test_every_combination_of_engine_reading_and_human_signoff(given, verification, expected):
    assert resolve_money_state(given, verification) == expected


def test_legacy_run_says_why_it_is_blocked():
    assert basis_reasons(None) == [LEGACY_REASON]


def test_basis_reasons_is_a_copy_not_the_runs_own_list():
    """A dated run reports its own reasons — but mutating what basis_reasons
    hands back must not reach back into the frozen run."""
    given = MoneyBasis(reasons=["motivo propio de esta corrida"])

    result = basis_reasons(given)

    assert result == given.reasons
    assert result is not given.reasons
    result.append("mutación de prueba")
    assert given.reasons == ["motivo propio de esta corrida"]


def test_bands_weigh_money_not_lines():
    """One expensive doubtful line must not be hidden by many cheap sure ones."""
    boq = BillOfQuantities(project_id="p")
    boq.lines = [
        BoqLine(concept_code="A", description="cara y dudosa", unit="M3", quantity=1,
                unit_price=900.0, amount=900.0, phase="Estructura", raw_quantity=1,
                raw_kind=QuantityKind.COUNT, source_detection_count=1, confidence=0.70),
        BoqLine(concept_code="B", description="barata y segura", unit="PZA", quantity=1,
                unit_price=100.0, amount=100.0, phase="Estructura", raw_quantity=1,
                raw_kind=QuantityKind.COUNT, source_detection_count=1, confidence=0.95),
    ]
    boq.direct_cost_total = 1000.0
    units = DrawingUnits(unit="m", source="dxf_header", confidence=0.9)

    bands = money_basis_from_boq(boq, units).confidence_bands

    assert bands["en_el_limite"] == pytest.approx(90.0)
    assert bands["alta"] == pytest.approx(10.0)
    assert sum(bands.values()) == pytest.approx(100.0)


def test_bands_are_absent_when_nothing_is_priced():
    """No line carries an amount: the split must not invent a number."""
    boq = BillOfQuantities(project_id="p")
    units = DrawingUnits(unit="m", source="dxf_header", confidence=0.9)

    bands = money_basis_from_boq(boq, units).confidence_bands

    assert bands == {}


def test_reasons_say_why_when_units_are_not_reliable():
    boq = BillOfQuantities(project_id="p", units_reliable=False)
    units = DrawingUnits(unit="drawing_units", source="unknown", confidence=0.0)

    reasons = money_basis_from_boq(boq, units).reasons

    assert any("no es confiable" in r for r in reasons)


def test_reasons_say_why_when_confidence_is_below_firm():
    boq = BillOfQuantities(project_id="p")
    units = DrawingUnits(unit="cm", source="text_height_heuristic", confidence=0.4)

    reasons = money_basis_from_boq(boq, units).reasons

    assert any("Unidad leída como" in r for r in reasons)


def test_the_report_carries_its_own_basis():
    """The verdict travels with the run, so a surface never has to re-derive it."""
    from klave_engine.costing.models import CostingConfig
    from klave_engine.costing.report import generate_cost_report
    from klave_engine.detection.results import DetectionType, make_detection
    from klave_engine.detection.taxonomy import classify_family

    from tests.precios import LIBRO

    wall = make_detection(
        "w1", DetectionType.wall, "w1", (0, 0, 10.0, 0.15), 0.9, [], "m", [],
        {"estimated_length": 10.0, "estimated_thickness": 0.15, "wall_kind": "block"},
    )
    wall.family = classify_family(wall).value
    units = DrawingUnits(unit="m", source="dxf_header", confidence=0.9)

    report = generate_cost_report(
        "p", [wall], units, CostingConfig(), None, None, price_book=LIBRO
    )

    assert report.money_basis is not None
    assert report.money_basis.units_reliable is True
    assert report.money_basis.unit == "m"
    assert sum(report.money_basis.confidence_bands.values()) == pytest.approx(100.0, abs=0.2)


def test_an_unreadable_drawing_produces_a_basis_that_blocks():
    from klave_engine.costing.models import CostingConfig
    from klave_engine.costing.report import generate_cost_report
    from klave_engine.detection.results import DetectionType, make_detection
    from klave_engine.detection.taxonomy import classify_family

    from tests.precios import LIBRO

    wall = make_detection(
        "w1", DetectionType.wall, "w1", (0, 0, 10.0, 0.15), 0.9, [], "u", [],
        {"estimated_length": 10.0, "estimated_thickness": 0.15, "wall_kind": "block"},
    )
    wall.family = classify_family(wall).value
    unknown = DrawingUnits(unit="drawing_units", source="unknown", confidence=0.0)

    report = generate_cost_report(
        "p", [wall], unknown, CostingConfig(), None, None, price_book=LIBRO
    )

    assert resolve_money_state(report.money_basis, UNCONFIRMED) == "blocked"
    assert resolve_money_state(report.money_basis, CONFIRMED) == "blocked"
    assert report.money_basis.reasons  # it says why, not just no
