"""Whether a number may be shown as money — decided once, here.

Before this module the rule lived in three places at three levels of rigor:
the web joined report and reviews correctly, the exports checked only
``units_reliable``, and the project list checked nothing at all. A doctrine
rule re-derived per surface is a doctrine that decays with every surface
added, and the newest one always gets the weakest version.

The split is forced by ``set_verification``, which deliberately does not
recompute: a full verdict frozen into ``cost_report.json`` would still read
"unverified" long after a person confirmed the unit. So the artifact carries
only what the engine read; the human half stays in reviews; this module joins
them at read time.
"""

from typing import Literal

from klave_engine.costing.models import BillOfQuantities, MoneyBasis
from klave_engine.costing.reviews import VerificationState
from klave_engine.dxf.units import DrawingUnits

MoneyState = Literal["ok", "unverified", "blocked"]

# The floor a reading has to clear to be treated as firm, mirrored in the web
# as CONFIDENCE_FIRM. One number, two languages, stated in both.
CONFIDENCE_FIRM = 0.7

LEGACY_REASON = "corrida anterior sin veredicto de unidades"


def money_basis_from_boq(boq: BillOfQuantities, units: DrawingUnits) -> MoneyBasis:
    reasons: list[str] = []
    if not boq.units_reliable:
        reasons.append(
            "La unidad del plano no es confiable: las cantidades están en unidades "
            "de dibujo y ninguna línea lleva precio."
        )
    elif units.confidence < CONFIDENCE_FIRM:
        reasons.append(
            f"Unidad leída como {units.unit} con {units.confidence:.0%} de confianza "
            f"(fuente: {units.source})."
        )
    return MoneyBasis(
        units_reliable=boq.units_reliable,
        unit=units.unit,
        source=units.source,
        confidence=units.confidence,
        reasons=reasons,
        confidence_bands=_confidence_bands(boq),
    )


def _confidence_bands(boq: BillOfQuantities) -> dict[str, float]:
    """Direct cost split three ways by the confidence behind it.

    Three bands rather than a pass rate because a single threshold lets a
    quarter of the money sit exactly on the line and still report "100 %
    firme" — which is the screen looking better than the reading behind it.
    """
    total = sum(line.amount for line in boq.lines)
    if total <= 0:
        return {}
    bands = {"alta": 0.0, "media": 0.0, "en_el_limite": 0.0}
    for line in boq.lines:
        if line.confidence > CONFIDENCE_FIRM:
            bands["alta"] += line.amount
        elif line.confidence == CONFIDENCE_FIRM:
            bands["en_el_limite"] += line.amount
        else:
            bands["media"] += line.amount
    return {key: round(value / total * 100.0, 1) for key, value in bands.items()}


def resolve_money_state(
    basis: MoneyBasis | None, verification: VerificationState | None
) -> MoneyState:
    """The one rule every money surface obeys.

    ``None`` basis means a run written before this verdict existed. It is
    blocked, not trusted: those runs priced at factor 1.0 when the unit was
    unknown, which is exactly the number nobody should see.
    """
    if basis is None:
        return "blocked"
    # The engine's own verdict wins: without a reliable unit it priced nothing,
    # so there is no amount for a person to sign off on.
    if not basis.units_reliable:
        return "blocked"
    if verification is not None and verification.units_confirmed_at is not None:
        return "ok"
    trustworthy = basis.unit != "drawing_units" and basis.confidence >= CONFIDENCE_FIRM
    return "unverified" if trustworthy else "blocked"


def basis_reasons(basis: MoneyBasis | None) -> list[str]:
    """What to tell the reader when money is withheld."""
    return [LEGACY_REASON] if basis is None else list(basis.reasons)
