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
    se pudo leer: conserva ``texto`` y deja ``valor`` vacío en vez de inventarlo.

    ``hoja`` es la primera hoja donde se lee el valor y ``hojas`` todas las que lo dicen (la
    primera incluida, o vacío si el dato es de una sola hoja): un dato que juntó las copias de
    veinte hojas sabe cuáles son."""

    valor: Any = None
    fuente: Fuente
    hoja: str = ""
    hojas: list[str] = []
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

    Las tuplas se vuelcan como listas, así que ``(20, 40)`` y ``[20, 40]`` son el mismo valor.
    Es total: un valor que ``json`` no puede volcar (claves de tipos mezclados, claves que no
    son texto o número, ciclos) se compara por su ``repr`` en vez de reventar."""
    try:
        return json.dumps(valor, sort_keys=True, default=_a_json)
    except (TypeError, ValueError, RecursionError):
        return repr(valor)


def hojas_de(dato: Dato) -> list[str]:
    """Todas las hojas donde se lee el valor de ``dato``: ``hoja`` primero, luego ``hojas``."""
    return list(dict.fromkeys([*([dato.hoja] if dato.hoja else []), *dato.hojas]))


def elegir(datos: list[Dato], *, preferir_hoja: str | None = None) -> Dato | None:
    """Escoge entre varios datos del mismo concepto; ``None`` si no hay ninguno.

    Gana el rango más alto de ``PRECEDENCIA``. Dentro de ese rango los datos se agrupan por
    valor: un solo valor (aunque repetido) no es conflicto y sus ``copias`` se suman; con
    varios valores se marca ``en_conflicto`` y gana el grupo con algún dato de
    ``preferir_hoja`` (un dato la tiene si es su ``hoja`` o está en sus ``hojas``), si no el
    más repetido (cuenta las ``copias`` que cada dato ya trae: un dato de 12 copias pesa más
    que dos de 1), si no el de la hoja menor. El dato elegido es el de ``preferir_hoja`` si el
    grupo ganador lo trae, si no el primero que llegó; sus ``hojas`` son las de todo el grupo.

    Todo lo demás queda en ``alternativas``, plano: primero los otros datos recibidos y luego
    lo que el elegido ya traía (la alternativa de un perdedor viaja dentro de él, sin
    desplegarse). Así elegir de nuevo sobre un dato ya elegido no borra su conflicto, sus
    copias ni la lectura que perdió. No modifica los datos recibidos."""
    if not datos:
        return None
    mejor = max(PRECEDENCIA[d.fuente] for d in datos)

    grupos: dict[str, list[int]] = {}  # posiciones en ``datos``, en el orden en que llegaron
    for i, d in enumerate(datos):
        if PRECEDENCIA[d.fuente] == mejor:
            grupos.setdefault(_clave(d.valor), []).append(i)

    def tiene_la_preferida(i: int) -> bool:
        return preferir_hoja is not None and preferir_hoja in hojas_de(datos[i])

    def orden(grupo: list[int]) -> tuple[bool, int, str]:
        con_preferida = any(tiene_la_preferida(i) for i in grupo)
        return (not con_preferida, -sum(datos[i].copias for i in grupo), datos[grupo[0]].hoja)

    ganador_grupo = min(grupos.values(), key=orden)
    elegido = next((i for i in ganador_grupo if tiene_la_preferida(i)), ganador_grupo[0])
    base = datos[elegido]
    alternativas = [d.model_copy(deep=True) for i, d in enumerate(datos) if i != elegido]
    alternativas += [a.model_copy(deep=True) for a in base.alternativas]
    hojas = list(dict.fromkeys(h for i in [elegido, *ganador_grupo] for h in hojas_de(datos[i])))
    return base.model_copy(
        deep=True,
        update={
            "alternativas": alternativas,
            "en_conflicto": len(grupos) > 1 or base.en_conflicto,
            "copias": sum(datos[i].copias for i in ganador_grupo),
            "hojas": hojas,
        },
    )


def miembros(dato: Dato) -> list[Dato]:
    """Los datos que ``elegir`` juntó en ``dato``: el elegido tal como llegó (con las copias
    que le tocaban, sin sus alternativas ni su conflicto) y cada una de sus alternativas."""
    clave, rango = _clave(dato.valor), PRECEDENCIA[dato.fuente]
    iguales = sum(
        a.copias
        for a in dato.alternativas
        if _clave(a.valor) == clave and PRECEDENCIA[a.fuente] == rango
    )
    base = dato.model_copy(
        deep=True,
        update={"alternativas": [], "en_conflicto": False, "copias": max(1, dato.copias - iguales)},
    )
    return [base, *(a.model_copy(deep=True) for a in dato.alternativas)]


def para_hoja(dato: Dato, hoja: str) -> Dato:
    """El dato como lo resuelve una hoja: cada hoja manda sobre lo suyo.

    Entre las lecturas que ``dato`` juntó, las que dice ``hoja`` (su ``hoja`` o en sus
    ``hojas``) se eligen entre sí —con ``elegir``, preferida ``hoja``— y lo que dicen las demás
    hojas queda en ``alternativas`` sin contar como conflicto: si la hoja se dice una sola vez
    no hay ``en_conflicto``. Una hoja que no tiene copia propia (o un dato sin hojas, como un
    supuesto) se queda con el dato elegido, con su conflicto a la vista. Siempre devuelve un
    dato nuevo (una copia, si no hay nada que elegir): editarlo no toca ``dato``."""
    todos = miembros(dato)
    del_grupo: dict[str, bool] = {}
    for m in todos:
        clave = _clave(m.valor)
        del_grupo[clave] = del_grupo.get(clave, False) or hoja in hojas_de(m)
    if not any(del_grupo.values()):
        return dato.model_copy(deep=True)
    propios = [m for m in todos if del_grupo[_clave(m.valor)]]
    otros = [m for m in todos if not del_grupo[_clave(m.valor)]]
    elegido = elegir(propios, preferir_hoja=hoja)
    assert elegido is not None  # ``propios`` no está vacío
    return elegido.model_copy(update={"alternativas": [*elegido.alternativas, *otros]})
