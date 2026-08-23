"""Prices that do not rot: how old every price is, which ones the presupuesto
actually uses, and how to bring an old one forward by an official index.

Three states by age of the vigencia (YYYY-MM):
  vigente   ≤ 6 months
  revisar   7–12 months — ask the supplier again before bidding
  vencido   > 12 months, or no vigencia at all
A presupuesto that uses vencido prices says so in its warnings; the
catálogo can export a solicitud de cotización for them and import the
supplier's answer; and an index (INPP construcción, the taller's own
table of monthly values with their source) can roll a price forward with
the factor written as its provenance — labeled calculado, never cotizado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

FRESH_MONTHS = 6
STALE_MONTHS = 12
_VIGENCIA_RE = re.compile(r"^(\d{4})-(\d{2})")


def months_old(vigencia: str | None, now: datetime | None = None) -> int | None:
    """Whole months between a vigencia (YYYY-MM…) and now; None when unreadable."""
    if not vigencia:
        return None
    match = _VIGENCIA_RE.match(str(vigencia).strip())
    if not match:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        return None
    today = now or datetime.now(UTC)
    return (today.year - year) * 12 + (today.month - month)


def freshness(vigencia: str | None, now: datetime | None = None) -> str:
    age = months_old(vigencia, now)
    if age is None or age > STALE_MONTHS:
        return "vencido"
    if age > FRESH_MONTHS:
        return "revisar"
    return "vigente"


@dataclass
class PriceAge:
    code: str
    description: str
    unit: str
    unit_cost: float
    source: str
    source_type: str
    vigencia: str
    months: int | None
    status: str  # vigente | revisar | vencido


def price_ages(insumos: list[dict], now: datetime | None = None) -> list[PriceAge]:
    out: list[PriceAge] = []
    for row in insumos:
        vigencia = str(row.get("vigencia") or "")
        out.append(
            PriceAge(
                code=str(row["code"]), description=str(row.get("description") or ""),
                unit=str(row.get("unit") or ""), unit_cost=float(row.get("unit_cost") or 0.0),
                source=str(row.get("source") or ""),
                source_type=str(row.get("source_type") or ""), vigencia=vigencia,
                months=months_old(vigencia, now), status=freshness(vigencia, now),
            )
        )
    return out


def roll_forward_factor(
    indices: dict[str, float], from_vigencia: str, to_vigencia: str
) -> float | None:
    """index(to) / index(from) when both months exist in the taller's table;
    the nearest earlier month stands in for a missing one (indices publish
    with a lag), never a later one."""

    def lookup(month: str) -> float | None:
        key = (month or "")[:7]
        if key in indices:
            return float(indices[key])
        earlier = sorted(k for k in indices if k <= key)
        return float(indices[earlier[-1]]) if earlier else None

    start, end = lookup(from_vigencia), lookup(to_vigencia)
    if not start or not end or start <= 0:
        return None
    return round(end / start, 6)


def now_month(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m")
