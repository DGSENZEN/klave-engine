"""Indicadores de sanidad y completitud del presupuesto.

Every senior estimator checks a handful of ratios before a presupuesto
leaves the office: kg of acero per m³ of concreto, m² of cimbra per m³,
pesos per m² construido, the share of each partida. Juniors don't, and the
costliest error — an omitted partida — shows up only at the obra. This
module computes those ratios from the BoQ, compares them against typical
ranges for the tipología and against the taller's own plantillas, and lists
the partidas the plantilla has that this presupuesto lacks. Out of range is
a flag with the reason, never a correction.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from klave_engine.costing.models import BillOfQuantities

CONCRETE_CODES = ("CIM-002", "CIM-007", "CIM-008", "EST-001", "EST-002", "EST-013", "EST-014")
STEEL_PREFIX = "ACE-"
FORMWORK_CODES = ("CIM-006", "CIM-009", "EST-008", "EST-009", "EST-010", "EST-011")

# Typical ranges for casa habitación residencial in Mexico (CMIC/BIMSA-style
# practice); the taller's plantillas refine them per tipología.
TYPICAL_RANGES: dict[str, tuple[float, float, str, str]] = {
    "acero_por_m3": (80.0, 160.0, "kg/m³", "kg de acero de refuerzo por m³ de concreto"),
    "cimbra_por_m3": (4.0, 12.0, "m²/m³", "m² de cimbra por m³ de concreto estructural"),
    "concreto_por_m2": (0.25, 0.55, "m³/m²", "m³ de concreto por m² construido"),
    "costo_directo_por_m2": (7000.0, 22000.0, "$/m²", "costo directo por m² construido"),
}


class Indicator(BaseModel):
    key: str
    label: str
    value: float | None
    unit: str
    low: float | None = None
    high: float | None = None
    status: str  # ok | alto | bajo | sin_dato
    detail: str = ""


class PhaseShare(BaseModel):
    phase: str
    share_pct: float
    typical_pct: float | None = None
    status: str  # ok | alto | bajo | falta | sin_referencia


class Indicators(BaseModel):
    indicators: list[Indicator] = Field(default_factory=list)
    phase_shares: list[PhaseShare] = Field(default_factory=list)
    missing_phases: list[str] = Field(default_factory=list)
    reference: str = ""  # which plantilla (or "rangos típicos") set the expectations
    notes: list[str] = Field(default_factory=list)


def _status(value: float | None, low: float | None, high: float | None) -> str:
    if value is None:
        return "sin_dato"
    if low is not None and value < low:
        return "bajo"
    if high is not None and value > high:
        return "alto"
    return "ok"


def _norm_phase(phase: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", phase or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.strip().upper()


def compute_indicators(
    boq: BillOfQuantities,
    area_construida_m2: float | None,
    plantillas: list[dict] | None = None,
) -> Indicators:
    out = Indicators()
    concrete = sum(ln.quantity for ln in boq.lines if ln.concept_code in CONCRETE_CODES)
    steel = sum(ln.quantity for ln in boq.lines if ln.concept_code.startswith(STEEL_PREFIX))
    formwork = sum(ln.quantity for ln in boq.lines if ln.concept_code in FORMWORK_CODES)
    direct = boq.direct_cost_total
    area = area_construida_m2 if area_construida_m2 and area_construida_m2 > 0 else None

    def add(key: str, value: float | None, detail: str) -> None:
        low, high, unit, label = TYPICAL_RANGES[key]
        out.indicators.append(
            Indicator(
                key=key, label=label, value=round(value, 2) if value is not None else None,
                unit=unit, low=low, high=high, status=_status(value, low, high), detail=detail,
            )
        )

    add(
        "acero_por_m3",
        steel / concrete if concrete > 0 and steel > 0 else None,
        f"{steel:,.0f} kg de acero cuantificado / {concrete:,.1f} m³ de concreto"
        if concrete > 0 else "sin concreto cuantificado",
    )
    add(
        "cimbra_por_m3",
        formwork / concrete if concrete > 0 and formwork > 0 else None,
        f"{formwork:,.1f} m² de cimbra / {concrete:,.1f} m³ de concreto"
        if concrete > 0 else "sin concreto cuantificado",
    )
    add(
        "concreto_por_m2",
        concrete / area if area and concrete > 0 else None,
        f"{concrete:,.1f} m³ / {area:,.0f} m² construidos" if area else "sin área construida",
    )
    add(
        "costo_directo_por_m2",
        direct / area if area and direct > 0 else None,
        f"${direct:,.0f} / {area:,.0f} m² construidos" if area else "sin área construida",
    )
    # The $/m² band is for a complete house. A presupuesto that only has
    # obra negra (structural drawings alone) sits below it by construction;
    # say so instead of flagging it as cheap.
    structural_phases = {"PRELIMINARES", "TERRACERIAS", "CIMENTACION", "ESTRUCTURA"}
    finishing_cost = sum(
        amount for phase, amount in boq.totals_by_phase.items()
        if _norm_phase(phase) not in structural_phases
    )
    if direct > 0 and finishing_cost / direct < 0.10:
        cost_indicator = out.indicators[-1]
        if cost_indicator.status == "bajo":
            cost_indicator.status = "sin_referencia"
            cost_indicator.detail += (
                " · solo obra negra (sin albañilería, acabados ni instalaciones): el rango "
                "típico es de obra completa"
            )
    for indicator in out.indicators:
        if indicator.status in ("alto", "bajo"):
            out.notes.append(
                f"{indicator.label}: {indicator.value:,.2f} {indicator.unit} está "
                f"{'arriba' if indicator.status == 'alto' else 'abajo'} del rango típico "
                f"({indicator.low:g}–{indicator.high:g}); revisa cantidades o precios."
            )

    # Shares by partida, against the closest plantilla (by tipología presence) if any.
    reference_shares: dict[str, float] = {}
    reference_name = "rangos típicos"
    for plantilla in plantillas or []:
        shares = plantilla.get("phase_shares") or {}
        if isinstance(shares, str):
            import json

            try:
                shares = json.loads(shares)
            except ValueError:
                shares = {}
        if shares:
            reference_shares = {_norm_phase(k): float(v) for k, v in shares.items()}
            reference_name = f"plantilla {plantilla.get('name')}"
            break
    out.reference = reference_name
    if direct > 0:
        own = {_norm_phase(k): v / direct * 100.0 for k, v in boq.totals_by_phase.items()}
        for phase, share in own.items():
            typical = reference_shares.get(phase)
            status = "sin_referencia"
            if typical is not None:
                status = "ok"
                if share > typical * 1.6 + 2:
                    status = "alto"
                elif share < typical * 0.5 - 2:
                    status = "bajo"
            out.phase_shares.append(
                PhaseShare(
                    phase=phase.title(), share_pct=round(share, 1), typical_pct=typical,
                    status=status,
                )
            )
        for phase, typical in reference_shares.items():
            if phase not in own and typical >= 2.0:
                out.missing_phases.append(phase.title())
                out.phase_shares.append(
                    PhaseShare(phase=phase.title(), share_pct=0.0, typical_pct=typical,
                               status="falta")
                )
        if out.missing_phases:
            out.notes.append(
                "Partidas que tu plantilla tiene y este presupuesto no: "
                + ", ".join(
                    f"{p} ({reference_shares[_norm_phase(p)]:.0f} %)" for p in out.missing_phases
                )
                + ". Agrégalas por paramétricos o ajustes antes de entregar."
            )
    return out


def phase_shares_from_rows(rows: list) -> dict[str, float]:
    """Share of each partida (group) in a past presupuesto, from its rows'
    quantity × price; rows without price weigh nothing."""
    totals: dict[str, float] = {}
    for row in rows:
        price = getattr(row, "price", None)
        if not price:
            continue
        group = _norm_phase(getattr(row, "group", "") or "SIN PARTIDA")
        totals[group] = totals.get(group, 0.0) + float(row.quantity) * float(price)
    grand = sum(totals.values())
    if grand <= 0:
        return {}
    return {k: round(v / grand * 100.0, 2) for k, v in totals.items()}
