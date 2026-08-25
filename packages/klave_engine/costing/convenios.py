"""Convenios modificatorios: cuando la obra deja de caber en su contrato.

Una estimación ya avisa que un concepto rebasó la cantidad contratada y hasta
aquí ese aviso no tenía salida: no había dónde registrar el convenio que lo
resuelve. Así que el residente lo firmaba fuera del sistema y el contrato que
la aplicación creía tener dejaba de ser el real — que es la forma más callada
de perder el control de una obra.

La ley pone un techo duro y es el punto de todo este módulo. **LOPSRM art. 59**:
los convenios no pueden exceder, en conjunto, el **25 %** del monto o del plazo
pactados originalmente, ni implicar variaciones sustanciales al proyecto. Pasado
ese punto no hay convenio que valga: se requiere un contrato nuevo, con su
licitación.

Ese 25 % se cuenta **acumulado y sobre el original**, no sobre el contrato ya
convenido, y ahí es donde se equivoca todo el mundo: tres convenios del 10 %
cada uno no son tres veces «dentro del límite», son un 30 % que rebasa. El
módulo los suma siempre contra el monto original y lo dice antes de firmar el
que rompe el techo, no después.

Lo que un convenio hace con las cantidades es aditivo y explícito: un renglón
nuevo entra al catálogo, y uno existente cambia su cantidad contratada. Nada
se toca en silencio — el catálogo contratado es el que se firmó más los
convenios que se firmaron encima, y cada renglón sabe de cuál viene.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from .estimaciones import Estimacion

# El techo del art. 59, en por ciento del monto y del plazo originales.
TECHO_PCT = 25.0

TipoConvenio = Literal["monto", "plazo", "ambos"]


class RenglonConvenio(BaseModel):
    """Un concepto que el convenio agrega al contrato o cuya cantidad cambia.

    ``quantity`` es la cantidad **nueva** del renglón, no el incremento: así se
    lee igual que el catálogo y no hay que sumar de cabeza para saber qué
    quedó contratado."""

    clave: str
    description: str
    unit: str
    unit_price: float
    quantity: float
    # Lo que decía el contrato antes de este convenio; 0 para un concepto que
    # no existía.
    quantity_anterior: float = 0.0

    @property
    def delta_cantidad(self) -> float:
        return round(self.quantity - self.quantity_anterior, 4)

    @property
    def delta_importe(self) -> float:
        return round(self.delta_cantidad * self.unit_price, 2)

    @property
    def es_nuevo(self) -> bool:
        return self.quantity_anterior <= 0


class Convenio(BaseModel):
    numero: int
    fecha: str  # ISO
    tipo: TipoConvenio = "monto"
    # Por qué se modifica. La ley pide causa justificada y un revisor la busca.
    motivo: str = ""
    renglones: list[RenglonConvenio] = Field(default_factory=list)
    # Días naturales que se agregan al plazo (0 si el convenio es sólo de monto).
    dias_plazo: int = 0

    @property
    def importe(self) -> float:
        """Lo que este convenio agrega (o resta) al monto del contrato."""
        return round(sum(r.delta_importe for r in self.renglones), 2)


@dataclass
class EstadoContrato:
    """El contrato como quedó: el original más lo convenido, contra el techo."""

    monto_original: float
    plazo_original_dias: int
    monto_convenido: float = 0.0
    dias_convenidos: int = 0
    avisos: list[str] = field(default_factory=list)

    @property
    def monto_vigente(self) -> float:
        return round(self.monto_original + self.monto_convenido, 2)

    @property
    def plazo_vigente_dias(self) -> int:
        return self.plazo_original_dias + self.dias_convenidos

    @property
    def monto_pct(self) -> float:
        if self.monto_original <= 0:
            return 0.0
        return round(self.monto_convenido / self.monto_original * 100.0, 2)

    @property
    def plazo_pct(self) -> float:
        if self.plazo_original_dias <= 0:
            return 0.0
        return round(self.dias_convenidos / self.plazo_original_dias * 100.0, 2)

    @property
    def rebasa_techo(self) -> bool:
        return self.monto_pct > TECHO_PCT or self.plazo_pct > TECHO_PCT


def estado(
    convenios: list[Convenio],
    monto_original: float,
    plazo_original_dias: int,
    monto_capturado: float | None = None,
) -> EstadoContrato:
    """Cómo quedó el contrato con todos sus convenios, y qué tan cerca del techo.

    Se acumula siempre contra el monto original: tres convenios del 10 % no son
    tres veces «dentro del límite», son un 30 % que rebasa el art. 59.

    ``monto_capturado`` es lo que dicen las estimaciones que vale el contrato.
    Debería coincidir con el catálogo de la convocante y cuando no coincide el
    porcentaje pierde sentido, porque se está midiendo contra una base que no
    es la que se está cobrando. En ese caso el número sale igual —esconderlo no
    ayuda a nadie— pero acompañado de la advertencia de que las dos fuentes no
    dicen lo mismo. Un porcentaje seguro sobre una base equivocada es peor que
    ningún porcentaje."""
    st = EstadoContrato(
        monto_original=monto_original,
        plazo_original_dias=plazo_original_dias,
        monto_convenido=round(sum(c.importe for c in convenios), 2),
        dias_convenidos=sum(c.dias_plazo for c in convenios),
    )

    if st.monto_pct > TECHO_PCT:
        st.avisos.append(
            f"Los convenios suman {st.monto_pct:.1f} % del monto original "
            f"(${st.monto_convenido:,.2f} sobre ${monto_original:,.2f}) y el art. 59 de la "
            f"LOPSRM los limita al {TECHO_PCT:g} % en conjunto. Pasado ese punto no hay "
            "convenio que valga: se requiere un contrato nuevo."
        )
    elif st.monto_pct > TECHO_PCT * 0.8:
        margen = round(monto_original * TECHO_PCT / 100 - st.monto_convenido, 2)
        st.avisos.append(
            f"Los convenios van en {st.monto_pct:.1f} % del monto original; el techo del "
            f"art. 59 es {TECHO_PCT:g} %. Quedan ${margen:,.2f} antes de necesitar otro "
            "contrato."
        )

    if st.plazo_pct > TECHO_PCT:
        st.avisos.append(
            f"Los convenios suman {st.plazo_pct:.1f} % del plazo original "
            f"({st.dias_convenidos} días sobre {plazo_original_dias}) y el art. 59 lo limita "
            f"al {TECHO_PCT:g} %."
        )

    if monto_capturado is not None and monto_original > 0 and monto_capturado > 0:
        brecha = abs(monto_capturado - monto_original) / monto_original * 100.0
        if brecha > 1.0:
            st.avisos.append(
                f"El catálogo de la convocante suma ${monto_original:,.2f} y las "
                f"estimaciones se calculan sobre ${monto_capturado:,.2f}. Mientras no "
                "coincidan, el porcentaje contra el techo del art. 59 se está midiendo "
                "sobre una base distinta de la que se cobra."
            )

    sustanciales = [c for c in convenios if any(r.es_nuevo for r in c.renglones)]
    if sustanciales:
        nuevos = sum(1 for c in sustanciales for r in c.renglones if r.es_nuevo)
        st.avisos.append(
            f"{nuevos} concepto{'s' if nuevos > 1 else ''} "
            f"{'entran' if nuevos > 1 else 'entra'} por convenio y no "
            f"{'estaban' if nuevos > 1 else 'estaba'} en el catálogo original. "
            "El art. 59 también prohíbe las variaciones sustanciales al proyecto: revisa "
            "que sean del mismo trabajo y no de otro."
        )
    return st


def catalogo_vigente(
    contratado: dict[str, float], convenios: list[Convenio]
) -> dict[str, float]:
    """Las cantidades contratadas después de los convenios firmados.

    El catálogo vigente es el que se firmó más lo que se convino encima, en
    orden: un convenio posterior manda sobre uno anterior para el mismo
    renglón, porque eso es lo que significa modificar."""
    vigente = dict(contratado)
    for convenio in sorted(convenios, key=lambda c: c.numero):
        for renglon in convenio.renglones:
            vigente[renglon.clave] = renglon.quantity
    return vigente


def desde_estimacion(estimacion: Estimacion, numero: int, fecha: str) -> Convenio:
    """El borrador de convenio que resuelve lo que una estimación no pudo cobrar.

    Nace con la cantidad ya ejecutada como nueva cantidad contratada, que es
    exactamente la razón por la que hizo falta el convenio. El motivo lo escribe
    una persona: la ley pide causa justificada y el motor no la tiene — sabe que
    se excedió, no por qué, y esa diferencia es la que revisa un auditor."""
    return Convenio(
        numero=numero,
        fecha=fecha,
        tipo="monto",
        renglones=[
            RenglonConvenio(
                clave=r.clave,
                description=r.description,
                unit=r.unit,
                unit_price=r.unit_price,
                quantity=r.quantity_accumulated,
                quantity_anterior=r.quantity_contract,
            )
            for r in estimacion.renglones
            if r.excede_contrato
        ],
    )
