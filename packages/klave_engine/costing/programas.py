"""Los programas de erogaciones que pide una propuesta de obra pública.

RLOPSRM art. 45, apartado A, fracción XI asks for four calendarised programs
"a costo directo", divided into partidas, over the periods the convocante
sets:

  a) de la mano de obra;
  b) de la maquinaria y equipo para construcción, identificando su tipo y
     características;
  c) de los materiales y equipos de instalación permanente, expresados en
     unidades convencionales y volúmenes requeridos;
  d) del personal profesional técnico, administrativo y de servicio.

They are not four documents someone types up beside the presupuesto. They
are one derivation: **the explosión de insumos, put on the programa's
calendar**. Each concept's resources are consumed while that concept runs,
so spreading each activity's resource consumption over the days it occupies
produces all four at once — and produces them congruent with the programa
and with the matrices by construction, which is precisely what a reviewer
checks under art. 64-A-I-c ("congruentes con los consumos y rendimientos
considerados").

Two honesty notes carried into the output:

* (a) and (b) come out in their own physical units — jornadas for a crew,
  horas efectivas for a machine — as well as pesos, because that is what the
  formats ask for. (c) carries volumes in unidades convencionales.
* (d) personal técnico y administrativo is **indirect** cost: it is not in
  the explosión at all, so it cannot be derived from it. Rather than invent
  a curve, this module returns it empty with a note saying where it must
  come from. Inventing that program would be inventing money.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from klave_engine.costing.explosion import explode
from klave_engine.costing.models import CostReport, ResourceType

# The four rubros of art. 45-A-XI, in the order the article lists them.
RUBROS = ("mano_de_obra", "maquinaria", "materiales", "personal_tecnico")

RUBRO_LABEL = {
    "mano_de_obra": "Programa de erogaciones de la mano de obra",
    "maquinaria": "Programa de erogaciones de la maquinaria y equipo de construcción",
    "materiales": (
        "Programa de erogaciones de los materiales y equipos de instalación permanente"
    ),
    "personal_tecnico": (
        "Programa de utilización del personal profesional técnico, administrativo y de servicio"
    ),
}


@dataclass
class ProgramaRow:
    """One insumo across the calendar, in its own unit and in pesos."""

    code: str
    description: str
    unit: str
    quantity: float
    amount: float
    # Physical quantity per period (jornadas, horas, m³…) and pesos per period.
    by_period: list[float] = field(default_factory=list)
    amount_by_period: list[float] = field(default_factory=list)


@dataclass
class Programa:
    rubro: str
    label: str
    rows: list[ProgramaRow]
    total: float
    total_by_period: list[float] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ProgramasErogaciones:
    periods: int
    period_label: str  # "mes" | "quincena" | "semana"
    programas: list[Programa]
    notes: list[str] = field(default_factory=list)

    def get(self, rubro: str) -> Programa | None:
        return next((p for p in self.programas if p.rubro == rubro), None)


def _rubro_of(resource_type: str) -> str:
    if resource_type == ResourceType.labor.value:
        return "mano_de_obra"
    if resource_type == ResourceType.equipment.value:
        return "maquinaria"
    return "materiales"


def build_programas(
    report: CostReport, workdays_per_period: int | None = None
) -> ProgramasErogaciones:
    """The four programs of art. 45-A-XI, derived from one source.

    ``workdays_per_period`` overrides the schedule's own period length: the
    law says "conforme a los periodos determinados por la convocante", and
    real convocatorias ask for monthly, fortnightly and weekly."""
    schedule = report.schedule
    period_days = workdays_per_period or schedule.workdays_per_month or 24
    period_label = {24: "mes", 12: "quincena", 6: "semana"}.get(period_days, "periodo")
    periods = (
        max(1, math.ceil(schedule.total_duration_days / period_days))
        if schedule.total_duration_days
        else 0
    )
    explosion = explode(report)

    # How much of each concept runs in each period, as a share of its total:
    # the calendar the resources ride on.
    share: dict[str, list[float]] = {}
    for activity in schedule.activities:
        spread = [0.0] * periods
        days = max(activity.duration_days, 1)
        for day in range(activity.start_day, activity.end_day):
            index = min(day // period_days, periods - 1) if periods else 0
            if periods:
                spread[index] += 1.0 / days
        share[activity.concept_code] = spread

    buckets: dict[str, list[ProgramaRow]] = {r: [] for r in RUBROS}
    for resource in explosion.resources:
        if resource.is_percentage or resource.unit.strip().startswith("%"):
            # Herramienta menor is a share of each matrix's labour, not something
            # anyone delivers on a date: it has no calendar of its own.
            continue
        rubro = _rubro_of(resource.resource_type)
        by_period = [0.0] * periods
        for concept_code, quantity in resource.by_concept.items():
            for index, part in enumerate(share.get(concept_code, [])):
                by_period[index] += quantity * part
        unit_cost = resource.unit_cost
        buckets[rubro].append(
            ProgramaRow(
                code=resource.code,
                description=resource.description,
                unit=resource.unit,
                quantity=round(resource.quantity, 4),
                amount=round(resource.amount, 2),
                by_period=[round(v, 4) for v in by_period],
                amount_by_period=[round(v * unit_cost, 2) for v in by_period],
            )
        )

    programas: list[Programa] = []
    for rubro in RUBROS:
        rows = sorted(buckets[rubro], key=lambda r: -r.amount)
        totals = [0.0] * periods
        for entry in rows:
            for index, value in enumerate(entry.amount_by_period):
                totals[index] += value
        notes: list[str] = []
        if rubro == "personal_tecnico" and not rows:
            notes.append(
                "El personal técnico, administrativo y de servicio es costo indirecto: "
                "no aparece en la explosión de insumos, así que este programa no se "
                "puede derivar del presupuesto. Captúralo desde tu plantilla de "
                "indirectos — el motor no lo inventa."
            )
        if rubro == "maquinaria" and rows:
            notes.append(
                "Cantidades en horas efectivas de trabajo; identifica tipo y "
                "características de cada máquina antes de entregar (art. 45-A-XI-b)."
            )
        if rubro == "materiales" and rows:
            notes.append(
                "Cantidades en unidades convencionales y volúmenes requeridos "
                "(art. 45-A-XI-c)."
            )
        programas.append(
            Programa(
                rubro=rubro,
                label=RUBRO_LABEL[rubro],
                rows=rows,
                total=round(sum(r.amount for r in rows), 2),
                total_by_period=[round(v, 2) for v in totals],
                notes=notes,
            )
        )

    notes = list(explosion.notes)
    notes.append(
        f"Programas calendarizados por {period_label} sobre el programa de ejecución "
        "(mismos rendimientos que las matrices), a costo directo."
    )
    return ProgramasErogaciones(
        periods=periods, period_label=period_label, programas=programas, notes=notes
    )
