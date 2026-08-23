"""Salario real per RLOPSRM art. 190–191, built in the open.

    Sr  = Sn · Fsr
    Fsr = (1 + Ps) · Tp / Tl

``Ps`` is the employer's IMSS + INFONAVIT burden as a fraction of the salary
actually paid, ``Tp`` the days paid in a year, ``Tl`` the days worked. Every
input is a parameter with a dated default (CONASAMI, UMA, IMSS 2026 tables,
LFT holidays and vacations), and the result carries its full breakdown so an
engineer can check every line against the law.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

YEAR = 2026
SALARIO_MINIMO_GENERAL = 315.04  # CONASAMI, vigente 1 ene 2026
SALARIO_MINIMO_FRONTERA = 440.87
UMA_DIARIA = 117.31  # INEGI, vigente 1 feb 2026

# Cesantía en edad avanzada y vejez, cuota patronal 2026 by SBC in UMA. The
# last band has no ceiling; a finite sentinel keeps the table JSON-safe.
NO_UPPER_BAND = 1e9
CEYV_BANDS_2026: list[tuple[float, float]] = [
    (1.00, 3.150), (1.50, 3.676), (2.00, 4.851), (2.50, 5.556),
    (3.00, 6.026), (3.50, 6.361), (4.00, 6.613), (NO_UPPER_BAND, 7.513),
]

# Construction (edificación) sits in class V; prima media of the class.
RIESGO_TRABAJO_CLASE_V = 7.58875


class FsrParameters(BaseModel):
    year: int = YEAR
    uma: float = UMA_DIARIA
    # Days paid: 365 + aguinaldo + prima vacacional (as paid days).
    aguinaldo_days: float = 15.0
    vacation_days: float = 12.0  # LFT art. 76 (reforma 2023), first year
    prima_vacacional_pct: float = 25.0
    # Days not worked: Sundays, LFT holidays, vacations, customary days.
    sundays: int = 52
    holidays: int = 7  # LFT art. 74 in 2026 (no presidential transmission)
    customary_days: float = 3.0  # jueves/viernes santo, 2 nov, 12 dic… (editable)
    # IMSS employer rates (% of SBC unless noted).
    riesgo_trabajo_pct: float = RIESGO_TRABAJO_CLASE_V
    eym_cuota_fija_pct_uma: float = 20.40  # of UMA, per day
    eym_excedente_pct: float = 1.10  # on SBC − 3 UMA
    eym_prestaciones_dinero_pct: float = 0.70
    eym_gastos_medicos_pensionados_pct: float = 1.05
    invalidez_vida_pct: float = 1.75
    guarderias_pct: float = 1.00
    retiro_pct: float = 2.00
    infonavit_pct: float = 5.00
    ceyv_bands: list[tuple[float, float]] = Field(default_factory=lambda: list(CEYV_BANDS_2026))
    # State payroll tax: not part of Ps under RLOPSRM (it belongs to
    # indirectos) but shown so nobody forgets it exists.
    isn_pct: float = 4.00
    isn_in_fsr: bool = False


class FsrBreakdown(BaseModel):
    salario_nominal: float
    factor_integracion: float
    salario_base_cotizacion: float
    sbc_in_uma: float
    employer_daily: dict[str, float]
    employer_daily_total: float
    ps: float
    tp: float
    tl: float
    fsr: float
    salario_real: float
    notes: list[str]


def ceyv_rate(sbc_in_uma: float, bands: list[tuple[float, float]]) -> float:
    for upper, rate in bands:
        if sbc_in_uma <= upper + 1e-9:
            return rate
    return bands[-1][1]


def compute_fsr(salario_nominal: float, params: FsrParameters | None = None) -> FsrBreakdown:
    p = params or FsrParameters()
    prima_days = p.vacation_days * p.prima_vacacional_pct / 100.0
    tp = 365.0 + p.aguinaldo_days + prima_days
    tl = 365.0 - p.sundays - p.holidays - p.vacation_days - p.customary_days
    factor_integracion = 1.0 + (p.aguinaldo_days + prima_days) / 365.0
    sbc = salario_nominal * factor_integracion
    sbc_uma = sbc / p.uma if p.uma else 0.0
    excedente = max(0.0, sbc - 3.0 * p.uma)
    ceyv = ceyv_rate(sbc_uma, p.ceyv_bands)
    employer = {
        "riesgo_trabajo": sbc * p.riesgo_trabajo_pct / 100.0,
        "eym_cuota_fija": p.uma * p.eym_cuota_fija_pct_uma / 100.0,
        "eym_excedente": excedente * p.eym_excedente_pct / 100.0,
        "eym_prestaciones_dinero": sbc * p.eym_prestaciones_dinero_pct / 100.0,
        "eym_gastos_medicos_pensionados": sbc * p.eym_gastos_medicos_pensionados_pct / 100.0,
        "invalidez_vida": sbc * p.invalidez_vida_pct / 100.0,
        "guarderias": sbc * p.guarderias_pct / 100.0,
        "retiro": sbc * p.retiro_pct / 100.0,
        "cesantia_vejez": sbc * ceyv / 100.0,
        "infonavit": sbc * p.infonavit_pct / 100.0,
    }
    if p.isn_in_fsr:
        employer["isn"] = salario_nominal * p.isn_pct / 100.0
    employer_total = sum(employer.values())
    # Cuotas accrue on every calendar day of SBC; salary is paid on Tp days.
    annual_employer = employer_total * 365.0
    annual_salary = salario_nominal * tp
    ps = annual_employer / annual_salary if annual_salary else 0.0
    fsr = (1.0 + ps) * tp / tl if tl else 0.0
    notes = [
        f"Tp = 365 + {p.aguinaldo_days:g} aguinaldo + {prima_days:g} prima vacacional = {tp:g}",
        f"Tl = 365 − {p.sundays} domingos − {p.holidays} festivos LFT − {p.vacation_days:g} "
        f"vacaciones − {p.customary_days:g} costumbre = {tl:g}",
        f"SBC = Sn × {factor_integracion:.4f} = {sbc:.2f} ({sbc_uma:.2f} UMA; "
        f"CEyV patronal {ceyv:.3f} %)",
        f"Ps = cuotas patronales anuales / salario anual pagado = {ps:.4f}",
        f"Fsr = (1 + Ps) × Tp / Tl = {fsr:.4f} — RLOPSRM art. 191",
        f"Referencias {p.year}: UMA {p.uma}, IMSS 2026, INFONAVIT {p.infonavit_pct:g} %"
        + ("" if p.isn_in_fsr else f"; ISN {p.isn_pct:g} % queda en indirectos"),
    ]
    return FsrBreakdown(
        salario_nominal=round(salario_nominal, 2),
        factor_integracion=round(factor_integracion, 4),
        salario_base_cotizacion=round(sbc, 2),
        sbc_in_uma=round(sbc_uma, 3),
        employer_daily={k: round(v, 4) for k, v in employer.items()},
        employer_daily_total=round(employer_total, 4),
        ps=round(ps, 4),
        tp=tp,
        tl=tl,
        fsr=round(fsr, 4),
        salario_real=round(salario_nominal * fsr, 2),
        notes=notes,
    )


class LaborCategory(BaseModel):
    code: str  # MO insumo code
    description: str
    salario_nominal: float


class RegionPreset(BaseModel):
    """What changes from one state to another in the salario real: the
    minimum wage zone (general / frontera norte) and the impuesto sobre
    nóminas. Rates are the published ones at the start of the year; the
    source is named so a taller checks its own state's law before bidding."""

    key: str
    label: str
    salario_minimo: float
    isn_pct: float
    zone: str  # general | frontera
    source: str


# ISN rates per state law (Ley de Hacienda / Código Fiscal estatal) as
# published for 2026; CDMX raised its rate to 4 % in 2025. Verify yearly.
REGION_PRESETS: list[RegionPreset] = [
    RegionPreset(key="cdmx", label="Ciudad de México", salario_minimo=SALARIO_MINIMO_GENERAL,
                 isn_pct=4.0, zone="general", source="Código Fiscal CDMX art. 158 (2025)"),
    RegionPreset(key="edomex", label="Estado de México", salario_minimo=SALARIO_MINIMO_GENERAL,
                 isn_pct=3.0, zone="general", source="Código Financiero Edomex art. 56"),
    RegionPreset(key="jalisco", label="Jalisco", salario_minimo=SALARIO_MINIMO_GENERAL,
                 isn_pct=3.0, zone="general", source="Ley de Hacienda de Jalisco art. 39"),
    RegionPreset(key="nuevo_leon", label="Nuevo León", salario_minimo=SALARIO_MINIMO_GENERAL,
                 isn_pct=3.0, zone="general", source="Ley de Hacienda de N.L. art. 154"),
    RegionPreset(key="queretaro", label="Querétaro", salario_minimo=SALARIO_MINIMO_GENERAL,
                 isn_pct=3.0, zone="general", source="Ley de Hacienda de Querétaro art. 75"),
    RegionPreset(key="guanajuato", label="Guanajuato", salario_minimo=SALARIO_MINIMO_GENERAL,
                 isn_pct=3.0, zone="general", source="Ley de Hacienda de Guanajuato art. 4"),
    RegionPreset(key="puebla", label="Puebla", salario_minimo=SALARIO_MINIMO_GENERAL,
                 isn_pct=3.0, zone="general", source="Ley de Hacienda de Puebla art. 13"),
    RegionPreset(key="yucatan", label="Yucatán", salario_minimo=SALARIO_MINIMO_GENERAL,
                 isn_pct=3.0, zone="general", source="Ley General de Hacienda de Yucatán art. 24"),
    RegionPreset(key="quintana_roo", label="Quintana Roo", salario_minimo=SALARIO_MINIMO_GENERAL,
                 isn_pct=4.0, zone="general", source="Ley de Hacienda de Q. Roo art. 44"),
    RegionPreset(key="sinaloa", label="Sinaloa", salario_minimo=SALARIO_MINIMO_GENERAL,
                 isn_pct=3.0, zone="general", source="Ley de Hacienda de Sinaloa art. 17"),
    RegionPreset(key="baja_california", label="Baja California (frontera norte)",
                 salario_minimo=SALARIO_MINIMO_FRONTERA, isn_pct=3.0, zone="frontera",
                 source="Ley de Hacienda de B.C. art. 151-13; ZLFN CONASAMI"),
    RegionPreset(key="chihuahua_frontera", label="Chihuahua (municipios fronterizos)",
                 salario_minimo=SALARIO_MINIMO_FRONTERA, isn_pct=3.0, zone="frontera",
                 source="Código Fiscal de Chihuahua art. 167; ZLFN CONASAMI"),
    RegionPreset(key="tamaulipas_frontera", label="Tamaulipas (municipios fronterizos)",
                 salario_minimo=SALARIO_MINIMO_FRONTERA, isn_pct=3.0, zone="frontera",
                 source="Ley de Hacienda de Tamaulipas art. 48; ZLFN CONASAMI"),
]


def preset_by_key(key: str) -> RegionPreset | None:
    return next((p for p in REGION_PRESETS if p.key == key), None)


def apply_preset(
    params: FsrParameters, categories: list[LaborCategory], preset: RegionPreset
) -> tuple[FsrParameters, list[LaborCategory]]:
    """The ISN of the state, and no category below its minimum wage."""
    updated = params.model_copy(update={"isn_pct": preset.isn_pct})
    floor = preset.salario_minimo
    lifted = [
        c.model_copy(update={"salario_nominal": max(c.salario_nominal, floor)})
        for c in categories
    ]
    return updated, lifted


DEFAULT_CATEGORIES: list[LaborCategory] = [
    LaborCategory(code="MO-PEON", description="Peón", salario_nominal=SALARIO_MINIMO_GENERAL),
    LaborCategory(code="MO-AYUD", description="Ayudante general", salario_nominal=360.0),
    LaborCategory(code="MO-ALBA", description="Albañil (oficial)", salario_nominal=470.0),
    LaborCategory(code="MO-FIERRERO", description="Fierrero (oficial)", salario_nominal=480.0),
    LaborCategory(code="MO-CARP", description="Carpintero de obra negra", salario_nominal=480.0),
    LaborCategory(code="MO-CABO", description="Cabo de oficios", salario_nominal=560.0),
]


def labor_provenance(params: FsrParameters) -> str:
    return (
        f"Salario real calculado: Sn × Fsr (RLOPSRM 190–191), CONASAMI/UMA {params.year}, "
        f"IMSS {params.year}, INFONAVIT {params.infonavit_pct:g} %"
    )


def now_month() -> str:
    return datetime.now(UTC).strftime("%Y-%m")
