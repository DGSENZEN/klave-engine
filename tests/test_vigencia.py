from datetime import UTC, datetime

from klave_engine.costing.vigencia import (
    freshness,
    months_old,
    price_ages,
    roll_forward_factor,
)

NOW = datetime(2026, 8, 23, tzinfo=UTC)


def test_ages_and_states():
    assert months_old("2026-06", NOW) == 2 and freshness("2026-06", NOW) == "vigente"
    assert months_old("2025-11", NOW) == 9 and freshness("2025-11", NOW) == "revisar"
    assert months_old("2025-06", NOW) == 14 and freshness("2025-06", NOW) == "vencido"
    assert months_old("", NOW) is None and freshness("", NOW) == "vencido"
    assert months_old("junio 2026", NOW) is None
    ages = price_ages(
        [{"code": "MAT-CEM", "description": "Cemento", "unit": "TON", "unit_cost": 3350.0,
          "source": "Referencia Klave", "source_type": "referencia", "vigencia": "2026-01"}],
        NOW,
    )
    assert ages[0].months == 7 and ages[0].status == "revisar"


def test_roll_forward_uses_the_nearest_earlier_month():
    indices = {"2025-06": 130.0, "2025-12": 133.9, "2026-06": 137.8}
    assert roll_forward_factor(indices, "2025-06", "2026-06") == round(137.8 / 130.0, 6)
    # August 2026 is not published yet: June stands in; March falls back to December.
    assert roll_forward_factor(indices, "2026-03", "2026-08") == round(137.8 / 133.9, 6)
    assert roll_forward_factor(indices, "2024-01", "2026-08") is None  # nothing earlier
    assert roll_forward_factor({}, "2025-06", "2026-06") is None
