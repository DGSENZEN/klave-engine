"""Estimaciones: lo que de verdad se cobra, mes con mes.

El presupuesto se hace una vez y la obra se cobra veinte. Cada periodo el
residente mide lo ejecutado, arma la estimación y la contratante paga — menos
la parte del anticipo que toca amortizar y menos la retención del fondo de
garantía. Ahí vive el contratista, y hasta ahora la aplicación se detenía
antes de ese punto: servía para ganar la obra y no para cobrarla.

La ley pone la forma (RLOPSRM arts. 130 a 132, LOPSRM art. 54):

* la estimación se formula por periodos **pactados**, no por avance a ojo, y
  va acompañada de sus generadores;
* el anticipo se amortiza **proporcionalmente** a lo estimado — el mismo
  porcentaje que se recibió al principio se descuenta de cada estimación, de
  modo que al terminar la obra queda saldado;
* la retención del fondo de garantía se descuenta de cada una y se devuelve al
  finiquito;
* lo ejecutado se compara contra lo contratado, no contra lo presupuestado: el
  catálogo firmado manda.

Dos reglas de honestidad que este módulo no negocia:

**Nada se estima sin medirse.** No hay «porcentaje de avance» que reparta
importes: cada renglón lleva la cantidad que alguien midió en obra, y la que
no se midió no entra. Un avance inventado se paga y luego se descuenta, y esa
conversación siempre sale cara.

**Nadie cobra dos veces el mismo metro.** Lo acumulado de estimaciones
anteriores se resta de la cantidad medida, y si la suma pasa de lo contratado
la estimación lo dice en vez de dejarlo pasar: rebasar el catálogo necesita
convenio, no una estimación más.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


class RenglonEstimado(BaseModel):
    """Un concepto del catálogo contratado, con lo medido este periodo."""

    clave: str
    description: str
    unit: str
    unit_price: float
    # Lo que dice el catálogo firmado: el techo de lo que se puede cobrar sin
    # convenio.
    quantity_contract: float
    # Lo que se midió en obra este periodo, con su generador detrás.
    quantity_period: float = 0.0
    # Lo acumulado en estimaciones anteriores.
    quantity_previous: float = 0.0

    @property
    def quantity_accumulated(self) -> float:
        return round(self.quantity_previous + self.quantity_period, 4)

    @property
    def amount_period(self) -> float:
        return round(self.quantity_period * self.unit_price, 2)

    @property
    def amount_accumulated(self) -> float:
        return round(self.quantity_accumulated * self.unit_price, 2)

    @property
    def pct_avance(self) -> float:
        if self.quantity_contract <= 0:
            return 0.0
        return round(self.quantity_accumulated / self.quantity_contract * 100.0, 2)

    @property
    def excede_contrato(self) -> bool:
        """Pasarse del catálogo firmado necesita convenio, no otra estimación."""
        return self.quantity_contract > 0 and self.quantity_accumulated > self.quantity_contract


class Deductiva(BaseModel):
    """Un descuento que no es amortización ni retención: penas, materiales de
    la contratante, trabajos rechazados. Lleva su razón porque alguien la va a
    reclamar."""

    concepto: str
    importe: float
    razon: str = ""


class Estimacion(BaseModel):
    numero: int
    periodo_inicio: str  # ISO
    periodo_fin: str
    renglones: list[RenglonEstimado] = Field(default_factory=list)
    deductivas: list[Deductiva] = Field(default_factory=list)
    # Porcentajes del contrato, para amortizar y retener como se pactó.
    anticipo_pct: float = 30.0
    retencion_pct: float = 5.0
    # Lo ya amortizado en estimaciones anteriores, para no pasarse del anticipo.
    amortizado_previo: float = 0.0
    monto_contrato: float = 0.0
    notas: list[str] = Field(default_factory=list)


@dataclass
class ResumenEstimacion:
    """La carátula de la estimación: de importe bruto a líquido por pagar."""

    numero: int
    periodo: str
    importe: float = 0.0            # lo ejecutado este periodo
    amortizacion: float = 0.0       # del anticipo, proporcional
    retencion: float = 0.0          # fondo de garantía
    deductivas: float = 0.0
    liquido: float = 0.0            # lo que efectivamente se cobra
    acumulado: float = 0.0          # ejecutado de toda la obra hasta hoy
    avance_pct: float = 0.0
    avisos: list[str] = field(default_factory=list)


def _anticipo(estimacion: Estimacion) -> float:
    return round(estimacion.monto_contrato * estimacion.anticipo_pct / 100.0, 2)


def calcular(estimacion: Estimacion) -> ResumenEstimacion:
    """De lo medido a lo que se cobra, con sus descuentos y sus avisos."""
    importe = round(sum(r.amount_period for r in estimacion.renglones), 2)
    acumulado = round(sum(r.amount_accumulated for r in estimacion.renglones), 2)

    # El anticipo se amortiza al mismo porcentaje al que se recibió: así queda
    # saldado exactamente cuando la obra termina, que es lo que pide el
    # art. 132. Nunca más de lo que queda por amortizar.
    anticipo = _anticipo(estimacion)
    por_amortizar = max(anticipo - estimacion.amortizado_previo, 0.0)
    amortizacion = min(
        round(importe * estimacion.anticipo_pct / 100.0, 2), por_amortizar
    )
    retencion = round(importe * estimacion.retencion_pct / 100.0, 2)
    deductivas = round(sum(d.importe for d in estimacion.deductivas), 2)
    liquido = round(importe - amortizacion - retencion - deductivas, 2)

    avance = (
        round(acumulado / estimacion.monto_contrato * 100.0, 2)
        if estimacion.monto_contrato > 0 else 0.0
    )

    avisos: list[str] = []
    excedidos = [r for r in estimacion.renglones if r.excede_contrato]
    if excedidos:
        peor = max(excedidos, key=lambda r: r.quantity_accumulated - r.quantity_contract)
        avisos.append(
            f"{len(excedidos)} conceptos rebasan la cantidad del catálogo contratado; "
            f"el mayor es {peor.clave}: contratado {peor.quantity_contract:,.2f} "
            f"{peor.unit}, estimado {peor.quantity_accumulated:,.2f}. Rebasar el "
            "catálogo necesita convenio, no una estimación más (RLOPSRM art. 132)."
        )
    if liquido < 0:
        avisos.append(
            f"El líquido sale negativo (${liquido:,.2f}): entre amortización, retención y "
            "deductivas se descuenta más de lo estimado. Revisa las deductivas antes de "
            "presentarla."
        )
    if importe > 0 and por_amortizar > 0 and amortizacion < round(
        importe * estimacion.anticipo_pct / 100.0, 2
    ):
        avisos.append(
            f"La amortización se topó en ${amortizacion:,.2f}: es lo que quedaba del "
            "anticipo. A partir de aquí las estimaciones ya no amortizan."
        )
    if not estimacion.renglones:
        avisos.append(
            "Estimación sin renglones medidos. Una estimación se formula sobre lo que "
            "alguien midió en obra, no sobre un porcentaje de avance."
        )

    return ResumenEstimacion(
        numero=estimacion.numero,
        periodo=f"{estimacion.periodo_inicio} → {estimacion.periodo_fin}",
        importe=importe, amortizacion=amortizacion, retencion=retencion,
        deductivas=deductivas, liquido=liquido, acumulado=acumulado,
        avance_pct=avance, avisos=avisos,
    )


def siguiente(
    estimacion: Estimacion, numero: int, inicio: str, fin: str
) -> Estimacion:
    """La estimación que sigue, con lo acumulado ya cargado.

    Encadenar a mano es como se cobra dos veces el mismo metro: lo estimado
    hasta hoy pasa a ser el «anterior» de la que viene, y lo amortizado
    también, sin que nadie lo teclee."""
    resumen = calcular(estimacion)
    return Estimacion(
        numero=numero, periodo_inicio=inicio, periodo_fin=fin,
        renglones=[
            RenglonEstimado(
                clave=r.clave, description=r.description, unit=r.unit,
                unit_price=r.unit_price, quantity_contract=r.quantity_contract,
                quantity_period=0.0, quantity_previous=r.quantity_accumulated,
            )
            for r in estimacion.renglones
        ],
        anticipo_pct=estimacion.anticipo_pct,
        retencion_pct=estimacion.retencion_pct,
        amortizado_previo=round(estimacion.amortizado_previo + resumen.amortizacion, 2),
        monto_contrato=estimacion.monto_contrato,
    )
