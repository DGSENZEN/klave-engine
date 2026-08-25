"""Bitácora de obra: el medio oficial de comunicación entre las partes.

La bitácora no es un diario de obra ni un cuaderno de notas. La **RLOPSRM
art. 123** la define como el instrumento técnico que constituye el medio de
comunicación entre las partes que firman el contrato, y de ahí sale todo lo
demás: lo que se asienta en ella obliga, y lo que no se asentó no pasó.

**Una nota no se edita.** Ése es el módulo entero. Una bitácora que se puede
corregir no prueba nada, porque cualquier cosa que dijera pudo haberse escrito
después. Cuando una nota salió mal se aclara con otra nota que la referencia y
las dos quedan; la equivocada no desaparece. Es exactamente la razón por la que
la bitácora de papel prohíbe tachaduras, hojas arrancadas y espacios en blanco,
y esas tres prohibiciones aquí se vuelven una: no hay forma de reescribir.

**La numeración es consecutiva y sin huecos.** Un salto en el consecutivo es la
señal clásica de una nota retirada, así que el motor no permite crear la nota 7
si la 6 no existe: no por rigor administrativo, sino porque el hueco es
precisamente lo que un perito busca.

**Cada nota tiene autor y parte.** La bitácora es comunicación entre dos, y una
nota sin saber quién la firma no comunica nada. Residente por la contratante,
superintendente por el contratista: la nota dice cuál de los dos habla.

La nota de apertura (**art. 125**) es la primera y lleva los datos del
contrato. Sin ella la bitácora no está abierta, y las notas que se escriban
antes están en un cuaderno cualquiera.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

TipoNota = Literal["apertura", "ordinaria", "extraordinaria", "cierre"]
Parte = Literal["contratante", "contratista", "supervision"]

ETIQUETA_PARTE: dict[str, str] = {
    "contratante": "Residente de obra (contratante)",
    "contratista": "Superintendente (contratista)",
    "supervision": "Supervisión externa",
}


class BitacoraError(Exception):
    """Lo que impide asentar una nota, dicho para quien la está escribiendo."""


class NotaBitacora(BaseModel):
    """Una nota asentada. Inmutable por diseño: se aclara, no se corrige."""

    numero: int
    fecha: str  # ISO
    tipo: TipoNota = "ordinaria"
    parte: Parte = "contratante"
    autor: str = ""
    cargo: str = ""
    texto: str = ""
    # La nota que ésta aclara, rectifica o responde. La aclarada se queda.
    referencia: int | None = None
    # Marcado al asentarse; sirve para distinguir la fecha del hecho de la
    # fecha en que se escribió, que no siempre son la misma.
    asentada_en: str = ""

    @property
    def parte_larga(self) -> str:
        return ETIQUETA_PARTE.get(self.parte, self.parte)


@dataclass
class EstadoBitacora:
    """Cómo está la bitácora: abierta, cerrada, y qué le falta."""

    notas: list[NotaBitacora] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def abierta(self) -> bool:
        return any(n.tipo == "apertura" for n in self.notas)

    @property
    def cerrada(self) -> bool:
        return any(n.tipo == "cierre" for n in self.notas)

    @property
    def siguiente_numero(self) -> int:
        return max((n.numero for n in self.notas), default=0) + 1

    @property
    def por_parte(self) -> dict[str, int]:
        cuenta: dict[str, int] = {}
        for n in self.notas:
            cuenta[n.parte] = cuenta.get(n.parte, 0) + 1
        return cuenta


def asentar(notas: list[NotaBitacora], nueva: NotaBitacora) -> list[NotaBitacora]:
    """Agrega una nota, o se niega diciendo por qué.

    Devuelve una lista nueva; la que entra no se toca. Todo lo que este módulo
    hace es agregar al final: no hay una función que modifique ni una que
    borre, y esa ausencia es la garantía."""
    numeros = {n.numero for n in notas}

    if nueva.numero in numeros:
        raise BitacoraError(
            f"La nota {nueva.numero} ya está asentada y una nota no se reescribe. "
            "Si salió mal, asienta otra que la aclare: las dos se quedan, que es "
            "lo que hace que la bitácora pruebe algo."
        )

    esperado = max(numeros, default=0) + 1
    if nueva.numero != esperado:
        raise BitacoraError(
            f"La siguiente nota es la {esperado}, no la {nueva.numero}. El consecutivo va "
            "sin huecos: un salto es la señal de una nota retirada y es lo primero que "
            "se revisa."
        )

    if nueva.tipo == "apertura" and notas:
        raise BitacoraError(
            "La nota de apertura es la primera de la bitácora (RLOPSRM art. 125) y ésta "
            "ya tiene notas asentadas."
        )
    if nueva.tipo != "apertura" and not notas:
        raise BitacoraError(
            "La bitácora no está abierta. La primera nota es la de apertura, con los "
            "datos del contrato; sin ella lo que se escriba está en un cuaderno "
            "cualquiera."
        )
    if any(n.tipo == "cierre" for n in notas):
        raise BitacoraError(
            "La bitácora está cerrada. Después de la nota de cierre no se asienta nada; "
            "lo que quede pendiente va en el finiquito."
        )

    if not nueva.texto.strip():
        raise BitacoraError("Una nota sin texto no comunica nada y no se asienta.")
    if not nueva.autor.strip():
        raise BitacoraError(
            "Falta quién firma la nota. La bitácora es comunicación entre dos partes y "
            "una nota sin autor no comunica nada."
        )
    if nueva.referencia is not None and nueva.referencia not in numeros:
        raise BitacoraError(
            f"La nota {nueva.referencia} que se quiere aclarar no existe en esta bitácora."
        )

    return [*notas, nueva]


def estado(notas: list[NotaBitacora]) -> EstadoBitacora:
    """La bitácora leída de corrido, con lo que le falta para servir de prueba."""
    ordenadas = sorted(notas, key=lambda n: n.numero)
    st = EstadoBitacora(notas=ordenadas)

    if not ordenadas:
        st.avisos.append(
            "La bitácora no está abierta. Su primera nota es la de apertura, con los datos "
            "del contrato (RLOPSRM art. 125)."
        )
        return st

    # Un hueco no debería poder existir por asentar(), pero un archivo se puede
    # editar por fuera y entonces el hueco es justo lo que hay que gritar.
    esperados = list(range(1, ordenadas[-1].numero + 1))
    faltantes = [n for n in esperados if n not in {x.numero for x in ordenadas}]
    if faltantes:
        st.avisos.append(
            f"Faltan las notas {', '.join(str(n) for n in faltantes)}. Un hueco en el "
            "consecutivo es la señal de una nota retirada y le quita valor probatorio a "
            "toda la bitácora."
        )

    if not st.abierta:
        st.avisos.append(
            "Hay notas asentadas pero ninguna es la de apertura. Sin ella la bitácora no "
            "está formalmente abierta."
        )

    partes = st.por_parte
    if len(ordenadas) >= 5 and len(partes) == 1:
        quien = ETIQUETA_PARTE.get(next(iter(partes)), next(iter(partes)))
        st.avisos.append(
            f"Las {len(ordenadas)} notas las asentó una sola parte ({quien}). La bitácora "
            "es el medio de comunicación entre las dos (RLOPSRM art. 123); si sólo escribe "
            "una, está sirviendo de diario, no de prueba."
        )

    return st
