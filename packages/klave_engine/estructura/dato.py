"""Un dato de la lectura estructural con su fuente, y la precedencia que decide entre fuentes.

Cada valor que la lectura produce (una sección, un armado, un recubrimiento…) viaja con
quién lo dijo y dónde. Cuando dos fuentes dicen cosas distintas gana la de mayor rango, y
cuando dos del MISMO rango se contradicen el desacuerdo se marca: nunca se elige en silencio."""

import json
from typing import Any, Literal

from pydantic import BaseModel

Fuente = Literal[
    "humano",
    "cuadro",
    "detalle",
    "seccion_dibujada",
    "nota",
    "medido",
    "regla",
    "supuesto",
    "ia",
]

# Mayor número, mayor autoridad. La IA queda al fondo: nunca tapa lo que el plano sí dice.
PRECEDENCIA: dict[str, int] = {
    "humano": 8,
    "cuadro": 7,
    "detalle": 6,
    "seccion_dibujada": 5,
    "nota": 4,
    "medido": 3,
    "regla": 2,
    "supuesto": 1,
    "ia": 0,
}


class Dato(BaseModel):
    """Un valor con su fuente.

    ``alternativas`` guarda lo que dijeron las demás fuentes (las de menor rango y las
    copias o contradicciones del mismo rango). ``ilegible`` es un texto del plano que no
    se pudo leer: conserva ``texto`` y deja ``valor`` vacío en vez de inventarlo."""

    valor: Any = None
    fuente: Fuente
    hoja: str = ""
    texto: str = ""
    entidades: list[str] = []
    alternativas: list["Dato"] = []
    en_conflicto: bool = False
    ilegible: bool = False
    copias: int = 1


Dato.model_rebuild()


def _a_json(objeto: Any) -> Any:
    """Lo que ``json`` no sabe volcar: un modelo pydantic va como su volcado JSON."""
    if isinstance(objeto, BaseModel):
        return objeto.model_dump(mode="json")
    return repr(objeto)


def _clave(valor: Any) -> str:
    """Clave canónica de un valor: la misma antes y después de pasar por ``estructura.json``.

    Las tuplas se vuelcan como listas, así que ``(20, 40)`` y ``[20, 40]`` son el mismo valor."""
    return json.dumps(valor, sort_keys=True, default=_a_json)


def elegir(datos: list[Dato], *, preferir_hoja: str | None = None) -> Dato | None:
    """Escoge entre varios datos del mismo concepto; ``None`` si no hay ninguno.

    Gana el rango más alto de ``PRECEDENCIA``. Dentro de ese rango los datos se agrupan por
    valor: un solo valor (aunque repetido) no es conflicto y sus ``copias`` se cuentan; con
    varios valores se marca ``en_conflicto`` y gana el grupo con algún dato de
    ``preferir_hoja``, si no el más repetido, si no el de la hoja menor. Todo lo demás
    queda en ``alternativas``, plano. No modifica los datos recibidos."""
    if not datos:
        return None
    mejor = max(PRECEDENCIA[d.fuente] for d in datos)

    grupos: dict[str, list[int]] = {}  # posiciones en ``datos``, en el orden en que llegaron
    for i, d in enumerate(datos):
        if PRECEDENCIA[d.fuente] == mejor:
            grupos.setdefault(_clave(d.valor), []).append(i)

    def orden(grupo: list[int]) -> tuple[bool, int, str]:
        con_preferida = preferir_hoja is not None and any(
            datos[i].hoja == preferir_hoja for i in grupo
        )
        return (not con_preferida, -len(grupo), datos[grupo[0]].hoja)

    ganador_grupo = min(grupos.values(), key=orden)
    elegido = ganador_grupo[0]
    return datos[elegido].model_copy(
        deep=True,
        update={
            "alternativas": [d.model_copy(deep=True) for i, d in enumerate(datos) if i != elegido],
            "en_conflicto": len(grupos) > 1,
            "copias": len(ganador_grupo),
        },
    )
