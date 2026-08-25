"""Finiquito: la cuenta que cierra el contrato.

Cuando los trabajos terminan, alguien tiene que sentarse a cuadrar todo lo que
pasó en la obra contra todo lo que se pagó, y esa cuenta es el finiquito. La
**RLOPSRM art. 168** la pide dentro del plazo pactado y **el art. 170** dice qué
lleva: lo ejecutado, lo pagado, los saldos a favor de quien sea, y las razones
de cada uno.

El finiquito casi nunca da cero, y las tres razones de que no dé son las que
este módulo calcula:

**La retención vuelve.** El fondo de garantía se descontó de cada estimación
para asegurar la obra, no para quedárselo. Al cierre se devuelve, salvo que se
sustituya por fianza. Es, casi siempre, el saldo grande a favor del contratista.

**El anticipo tiene que quedar en ceros.** Si se amortizó de menos —porque la
obra se ejecutó por debajo de lo contratado y las amortizaciones proporcionales
no alcanzaron—, ese remanente lo debe el contratista. Ese es el saldo que más
sorprende a quien no lo vio venir, y por eso sale con su nombre completo.

**Las penas convencionales se aplican aquí.** El atraso se penaliza sobre el
monto de lo no ejecutado en la fecha pactada (**RLOPSRM art. 86**), y el
porcentaje lo fija el contrato, no la ley: el motor no lo inventa, lo pide.

Nada se compensa en silencio: cada saldo aparece con su nombre, su signo y su
razón, y la resta se hace al final y a la vista. Un finiquito que sólo enseña el
resultado es un finiquito que nadie puede revisar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field, computed_field


class SaldoFiniquito(BaseModel):
    """Un renglón de la cuenta final.

    ``importe`` positivo es a favor del contratista, negativo a favor de la
    contratante. El signo se conserva tal cual hasta la suma: compensar antes de
    mostrar es lo que vuelve ilegible un finiquito."""

    concepto: str
    importe: float
    razon: str = ""

    # computed_field y no @property: si no se serializa, la pantalla tiene que
    # volver a deducir el signo, y deducirlo dos veces es deducirlo distinto.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def a_favor(self) -> str:
        return "contratista" if self.importe >= 0 else "contratante"


class Finiquito(BaseModel):
    fecha: str  # ISO
    monto_contrato: float = 0.0
    # Lo que suman todas las estimaciones autorizadas.
    ejecutado: float = 0.0
    # Lo efectivamente pagado (líquidos), para cuadrar contra lo ejecutado.
    pagado: float = 0.0
    anticipo_otorgado: float = 0.0
    anticipo_amortizado: float = 0.0
    retenciones_aplicadas: float = 0.0
    # La retención se devuelve, a menos que se haya sustituido por fianza.
    retencion_sustituida_por_fianza: bool = False
    # Días de atraso y el porcentaje diario que fija el contrato (no la ley).
    dias_atraso: int = 0
    pena_pct_diario: float = 0.0
    otros: list[SaldoFiniquito] = Field(default_factory=list)


@dataclass
class ResumenFiniquito:
    fecha: str
    ejecutado: float = 0.0
    pagado: float = 0.0
    saldos: list[SaldoFiniquito] = field(default_factory=list)
    # Positivo: la contratante le debe al contratista. Negativo: al revés.
    saldo_final: float = 0.0
    avisos: list[str] = field(default_factory=list)

    @property
    def a_favor_de(self) -> str:
        if abs(self.saldo_final) < 0.01:
            return "nadie"
        return "contratista" if self.saldo_final > 0 else "contratante"

    def payload(self) -> dict:
        """La carátula como la ve la pantalla, con los derivados incluidos.

        vars() se salta las @property, y a_favor_de es justo el dato que
        traduce un signo en una frase. Sin él la pantalla lo vuelve a deducir
        por su cuenta, que es como los dos lados terminan diciendo cosas
        distintas del mismo número."""
        return {
            "fecha": self.fecha,
            "ejecutado": self.ejecutado,
            "pagado": self.pagado,
            "saldos": [s.model_dump(mode="json") for s in self.saldos],
            "saldo_final": self.saldo_final,
            "a_favor_de": self.a_favor_de,
            "avisos": list(self.avisos),
        }


def _pena(fin: Finiquito) -> float:
    """Pena convencional por atraso, sobre lo no ejecutado (RLOPSRM art. 86)."""
    faltante = max(fin.monto_contrato - fin.ejecutado, 0.0)
    return round(faltante * fin.pena_pct_diario / 100.0 * fin.dias_atraso, 2)


def calcular(fin: Finiquito) -> ResumenFiniquito:
    res = ResumenFiniquito(fecha=fin.fecha, ejecutado=fin.ejecutado, pagado=fin.pagado)

    diferencia = round(fin.ejecutado - fin.pagado, 2)
    if abs(diferencia) >= 0.01:
        res.saldos.append(
            SaldoFiniquito(
                concepto="Estimaciones ejecutadas y no pagadas"
                if diferencia > 0
                else "Pagos por encima de lo estimado",
                importe=diferencia,
                razon=f"Ejecutado ${fin.ejecutado:,.2f} contra pagado ${fin.pagado:,.2f}.",
            )
        )

    if fin.retenciones_aplicadas > 0:
        if fin.retencion_sustituida_por_fianza:
            res.avisos.append(
                f"La retención de ${fin.retenciones_aplicadas:,.2f} se sustituyó por fianza, "
                "así que no se devuelve en el finiquito."
            )
        else:
            res.saldos.append(
                SaldoFiniquito(
                    concepto="Devolución del fondo de garantía",
                    importe=fin.retenciones_aplicadas,
                    razon="Se retuvo en cada estimación para garantizar los trabajos; al "
                    "cierre se devuelve.",
                )
            )

    remanente = round(fin.anticipo_otorgado - fin.anticipo_amortizado, 2)
    if remanente > 0.01:
        res.saldos.append(
            SaldoFiniquito(
                concepto="Anticipo no amortizado",
                importe=-remanente,
                razon=f"Se otorgaron ${fin.anticipo_otorgado:,.2f} y sólo se amortizaron "
                f"${fin.anticipo_amortizado:,.2f}; el resto es dinero de la contratante que "
                "sigue en poder del contratista.",
            )
        )
        res.avisos.append(
            f"Quedan ${remanente:,.2f} de anticipo sin amortizar. Si la obra se ejecutó por "
            "debajo de lo contratado, las amortizaciones proporcionales no alcanzan y la "
            "diferencia se reintegra en el finiquito."
        )
    elif remanente < -0.01:
        res.avisos.append(
            f"Se amortizaron ${abs(remanente):,.2f} de más sobre el anticipo otorgado. "
            "Revisa las amortizaciones de las estimaciones: se le descontó al contratista "
            "más de lo que recibió."
        )

    pena = _pena(fin)
    if pena > 0:
        res.saldos.append(
            SaldoFiniquito(
                concepto="Pena convencional por atraso",
                importe=-pena,
                razon=f"{fin.dias_atraso} días al {fin.pena_pct_diario:g} % diario sobre "
                f"${round(max(fin.monto_contrato - fin.ejecutado, 0.0), 2):,.2f} no ejecutados "
                "a la fecha pactada (RLOPSRM art. 86).",
            )
        )
    elif fin.dias_atraso > 0 and fin.pena_pct_diario <= 0:
        res.avisos.append(
            f"Hay {fin.dias_atraso} días de atraso registrados pero no se capturó el "
            "porcentaje de pena convencional, que lo fija el contrato. Sin ese dato el "
            "finiquito no la incluye."
        )

    res.saldos.extend(fin.otros)
    res.saldo_final = round(sum(s.importe for s in res.saldos), 2)

    if fin.monto_contrato > 0:
        ejercido_pct = round(fin.ejecutado / fin.monto_contrato * 100.0, 2)
        if ejercido_pct < 95.0:
            res.avisos.append(
                f"Se ejecutó el {ejercido_pct:.1f} % del monto contratado. Un finiquito por "
                "debajo de lo pactado necesita explicar qué no se hizo: conceptos cancelados, "
                "cantidades menores, o una terminación anticipada."
            )
    return res
