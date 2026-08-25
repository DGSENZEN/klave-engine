"""One authority decides whether a number may be shown as money. This is
that authority's truth table — including the legacy runs written before the
verdict existed, which must not be readable as money."""

from datetime import UTC, datetime

import pytest
from klave_engine.costing.models import BillOfQuantities, BoqLine, QuantityKind
from klave_engine.costing.presentation import (
    MoneyBasis,
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
    state = resolve_money_state(None, UNCONFIRMED)
    assert state == "blocked"


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
