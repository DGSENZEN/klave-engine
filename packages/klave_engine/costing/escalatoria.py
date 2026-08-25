"""Ajuste de costos: cuando los insumos suben y el contrato sigue diciendo lo
mismo.

Un contrato de obra pública se firma con precios de una fecha y se ejecuta
durante meses o años. Cuando los insumos suben, la ley no obliga al contratista
a comerse la diferencia: la **LOPSRM art. 57** abre tres procedimientos de
revisión y el **art. 58** manda que el ajuste se pague en la estimación
siguiente a su autorización.

Este módulo hace la aritmética y se niega a hacer lo demás. En concreto:

**Los índices no se inventan.** El factor sale de índices del INPP publicados
por el INEGI, y el motor no tiene ninguno guardado ni lo va a estimar. Sin los
dos índices —el de la fecha base y el de la fecha de ajuste— no hay factor, y
lo que sale es la petición del dato, no un número aproximado. Un ajuste de
costos con índices inventados no es un cálculo optimista: es un cobro sin
sustento, y se detecta en la primera revisión.

**Sólo se ajusta lo que falta por ejecutar.** El ajuste aplica a la obra
pendiente a la fecha en que ocurrió el incremento (RLOPSRM art. 173). Lo ya
estimado se pagó a los precios de entonces y no se vuelve a tocar; incluirlo es
el error que convierte una solicitud legítima en una observación.

**El atraso propio no se premia.** Si la obra va tarde por causa del
contratista, esos trabajos se ajustan con los índices que les habrían
correspondido según el programa, no con los del mes en que finalmente se
hicieron (RLOPSRM art. 176). De otro modo atrasarse pagaría.

La fecha base es la del acto de presentación y apertura de proposiciones, no la
de la firma del contrato ni la del arranque de la obra: son fechas distintas y
usar la equivocada mueve el factor entero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


class Indice(BaseModel):
    """Un índice de precios con sus valores por periodo.

    ``valores`` va de periodo ISO (``2026-03``) a valor publicado. Se captura o
    se importa de la publicación; el motor no rellena los meses que falten ni
    interpola entre dos, porque un índice interpolado no lo publicó nadie y en
    una revisión no hay dónde ir a comprobarlo."""

    nombre: str
    fuente: str = ""
    # La publicación de la que salieron los valores, para poder ir a verla.
    publicacion: str = ""
    valores: dict[str, float] = Field(default_factory=dict)

    def valor(self, periodo: str) -> float | None:
        return self.valores.get(periodo)


class RenglonAjuste(BaseModel):
    """Un concepto con lo que le falta por ejecutar a la fecha del ajuste."""

    clave: str
    description: str
    unit: str
    unit_price: float
    quantity_contract: float
    # Lo ya estimado: se pagó a los precios de entonces y no se ajusta.
    quantity_executed: float = 0.0
    # Lo que debió estar ejecutado según el programa. Cuando lo ejecutado es
    # menor por causa del contratista, la diferencia no se ajusta a este mes.
    quantity_programada: float | None = None

    @property
    def quantity_pendiente(self) -> float:
        return round(max(self.quantity_contract - self.quantity_executed, 0.0), 4)

    @property
    def importe_pendiente(self) -> float:
        return round(self.quantity_pendiente * self.unit_price, 2)

    @property
    def atraso(self) -> float:
        """Lo que el programa pedía y no se hizo. 0 si va al corriente."""
        if self.quantity_programada is None:
            return 0.0
        return round(max(self.quantity_programada - self.quantity_executed, 0.0), 4)


class SolicitudAjuste(BaseModel):
    """Una solicitud de ajuste: qué periodo, contra qué base, con qué índice."""

    numero: int = 1
    # Del acto de presentación y apertura de proposiciones. No es la firma del
    # contrato ni el arranque de la obra.
    periodo_base: str = ""
    periodo_ajuste: str = ""
    indice: Indice | None = None
    renglones: list[RenglonAjuste] = Field(default_factory=list)
    # Si el atraso es imputable al contratista, su obra atrasada no se ajusta a
    # este periodo (RLOPSRM art. 176).
    atraso_imputable_al_contratista: bool = False


@dataclass
class ResumenAjuste:
    numero: int
    periodo_base: str = ""
    periodo_ajuste: str = ""
    indice_base: float | None = None
    indice_ajuste: float | None = None
    factor: float | None = None
    importe_pendiente: float = 0.0
    importe_ajustable: float = 0.0
    importe_ajuste: float = 0.0
    avisos: list[str] = field(default_factory=list)

    @property
    def calculable(self) -> bool:
        return self.factor is not None


def _pedir_indices(sol: SolicitudAjuste, res: ResumenAjuste) -> bool:
    """Deja dicho qué falta para poder calcular. True si ya se puede."""
    if sol.indice is None:
        res.avisos.append(
            "No hay índice cargado. El factor sale de índices del INPP publicados por el "
            "INEGI y el motor no guarda ninguno: captura la publicación que vas a usar. "
            "Un ajuste con índices inventados es un cobro sin sustento."
        )
        return False
    if not sol.periodo_base or not sol.periodo_ajuste:
        res.avisos.append(
            "Falta el periodo base o el de ajuste. La fecha base es la del acto de "
            "presentación y apertura de proposiciones, no la de la firma del contrato."
        )
        return False

    res.indice_base = sol.indice.valor(sol.periodo_base)
    res.indice_ajuste = sol.indice.valor(sol.periodo_ajuste)
    faltan = [
        p
        for p, v in ((sol.periodo_base, res.indice_base), (sol.periodo_ajuste, res.indice_ajuste))
        if v is None
    ]
    if faltan:
        res.avisos.append(
            f"El índice «{sol.indice.nombre}» no tiene valor para {', '.join(faltan)}. "
            "No se interpola entre dos periodos: un índice interpolado no lo publicó "
            "nadie y en una revisión no hay dónde ir a comprobarlo."
        )
        return False
    if not res.indice_base:
        res.avisos.append(
            f"El índice del periodo base ({sol.periodo_base}) es cero: no se puede dividir "
            "entre él. Revisa la captura."
        )
        return False
    return True


def calcular(sol: SolicitudAjuste) -> ResumenAjuste:
    """El ajuste sobre lo que falta por ejecutar, o la razón por la que no sale."""
    res = ResumenAjuste(
        numero=sol.numero,
        periodo_base=sol.periodo_base,
        periodo_ajuste=sol.periodo_ajuste,
    )
    res.importe_pendiente = round(sum(r.importe_pendiente for r in sol.renglones), 2)

    # Lo ya estimado se pagó a los precios de entonces: no entra, ni aunque el
    # incremento sea real. Incluirlo es lo que convierte una solicitud legítima
    # en una observación.
    ejecutado = round(
        sum(r.quantity_executed * r.unit_price for r in sol.renglones), 2
    )
    if ejecutado > 0:
        res.avisos.append(
            f"Quedan fuera ${ejecutado:,.2f} ya estimados: se pagaron a los precios de "
            "entonces. El ajuste aplica a la obra pendiente a la fecha del incremento "
            "(RLOPSRM art. 173)."
        )

    ajustable = res.importe_pendiente
    if sol.atraso_imputable_al_contratista:
        atrasado = round(sum(r.atraso * r.unit_price for r in sol.renglones), 2)
        if atrasado > 0:
            ajustable = round(ajustable - atrasado, 2)
            res.avisos.append(
                f"${atrasado:,.2f} corresponden a obra atrasada por causa del contratista y "
                "se ajustan con los índices que les tocaban según el programa, no con los "
                "de este periodo (RLOPSRM art. 176)."
            )
        elif not any(r.quantity_programada is not None for r in sol.renglones):
            res.avisos.append(
                "Se marcó el atraso como imputable al contratista pero ningún renglón trae "
                "la cantidad programada, así que no hay contra qué medirlo. Captura el "
                "programa o quita la marca."
            )
    res.importe_ajustable = ajustable

    if not _pedir_indices(sol, res):
        return res

    base = res.indice_base or 0.0
    alza = res.indice_ajuste or 0.0
    res.factor = round(alza / base, 6)
    # El factor menos uno: lo que subió, que es lo que se paga de más.
    res.importe_ajuste = round(ajustable * (res.factor - 1.0), 2)

    if res.factor < 1.0:
        res.avisos.append(
            f"El factor sale en {res.factor:.4f}: el índice bajó entre {sol.periodo_base} y "
            f"{sol.periodo_ajuste}. El ajuste procede en los dos sentidos y este sale a "
            "favor de la contratante."
        )
    if not sol.renglones:
        res.avisos.append(
            "No hay renglones en la solicitud: sin obra pendiente el factor no se aplica "
            "a nada."
        )
    return res
