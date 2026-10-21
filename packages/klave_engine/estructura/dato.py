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


# R143: lo que se lee del plano (o lo decide alguien): ni la IA (por confirmar, nunca tapa al
# plano) ni el supuesto de Klave. Un valor leído de estas fuentes gana a un ilegible de cualquier
# rango.
_LEIDAS = frozenset(PRECEDENCIA) - {"ia", "supuesto"}


def _leido(dato: Dato) -> bool:
    """Si ``dato`` dice un valor leído (R143): de una fuente que lee el plano y no ilegible."""
    return dato.fuente in _LEIDAS and not dato.ilegible and dato.valor is not None


def elegir(datos: list[Dato], *, preferir_hoja: str | None = None) -> Dato | None:
    """Escoge entre varios datos del mismo concepto; ``None`` si no hay ninguno.

    Gana el rango más alto de ``PRECEDENCIA``. Un dato ilegible no se puede pesar (R143, que
    amplía R76): si hay algún valor leído (``_leido``), los ilegibles de cualquier rango no
    compiten —quedan en ``alternativas`` y, si alguno es de rango igual o mayor que el del
    ganador, el resultado queda ``en_conflicto``—; la IA y el supuesto nunca cuentan como leídos,
    así que un ilegible del plano siempre le gana a la IA. Dentro del rango ganador los datos se
    agrupan por valor: un solo valor (aunque repetido) no es conflicto y sus ``copias`` se suman;
    con varios valores se marca ``en_conflicto`` y gana el grupo con algún dato de
    ``preferir_hoja`` (un dato la tiene si es su ``hoja`` o está en sus ``hojas``), si no el más
    repetido (cuenta las ``copias`` que cada dato ya trae: un dato de 12 copias pesa más que dos de
    1), si no el de la hoja menor. El dato elegido es el de ``preferir_hoja`` si el grupo ganador
    lo trae, si no el primero que llegó; sus ``hojas`` son las de todo el grupo.

    Todo lo demás queda en ``alternativas``, plano: primero los otros datos recibidos y luego
    lo que el elegido ya traía (la alternativa de un perdedor viaja dentro de él, sin
    desplegarse). Así elegir de nuevo sobre un dato ya elegido no borra su conflicto, sus
    copias ni la lectura que perdió. El resultado está ``en_conflicto`` si hay más de un valor
    o si algún dato del grupo ganador ya lo estaba, llegue en el orden que llegue (R13). No
    modifica los datos recibidos."""
    if not datos:
        return None
    hay_leidos = any(_leido(d) for d in datos)
    compiten = [i for i, d in enumerate(datos) if not (hay_leidos and d.ilegible)]
    mejor = max(PRECEDENCIA[datos[i].fuente] for i in compiten)
    # R143: un ilegible apartado de rango igual o mayor que el ganador es un desacuerdo a la vista.
    ilegible_encima = hay_leidos and any(
        d.ilegible and PRECEDENCIA[d.fuente] >= mejor for d in datos
    )

    grupos: dict[str, list[int]] = {}  # posiciones en ``datos``, en el orden en que llegaron
    for i in compiten:
        if PRECEDENCIA[datos[i].fuente] == mejor:
            grupos.setdefault(_clave(datos[i].valor), []).append(i)

    def tiene_la_preferida(i: int) -> bool:
        return preferir_hoja is not None and preferir_hoja in hojas_de(datos[i])

    def orden(grupo: list[int]) -> tuple[bool, bool, int, str]:
        con_preferida = any(tiene_la_preferida(i) for i in grupo)
        ilegible = all(datos[i].ilegible for i in grupo)
        return (
            not con_preferida,
            ilegible,
            -sum(datos[i].copias for i in grupo),
            datos[grupo[0]].hoja,
        )

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
            # R13: un conflicto que ya traía cualquier dato del grupo ganador sigue a la vista,
            # sea cual sea el orden en que llegaron (no sólo el del elegido).
            "en_conflicto": len(grupos) > 1
            or ilegible_encima
            or any(datos[i].en_conflicto for i in ganador_grupo),
            "copias": sum(datos[i].copias for i in ganador_grupo),
            "hojas": hojas,
        },
    )


def miembros(dato: Dato) -> list[Dato]:
    """Los datos que ``elegir`` juntó en ``dato``: el elegido tal como llegó (con las copias
    que le tocaban, sin sus alternativas ni su conflicto, y sólo con sus propias hojas: las de
    las copias que se le juntaron son de ellas, M-1) y cada una de sus alternativas."""
    clave, rango = _clave(dato.valor), PRECEDENCIA[dato.fuente]
    iguales = [
        a for a in dato.alternativas if _clave(a.valor) == clave and PRECEDENCIA[a.fuente] == rango
    ]
    de_las_copias = {h for a in iguales for h in hojas_de(a)}
    propias = [h for h in hojas_de(dato) if h == dato.hoja or h not in de_las_copias]
    base = dato.model_copy(
        deep=True,
        update={
            "alternativas": [],
            "en_conflicto": False,
            "copias": max(1, dato.copias - sum(a.copias for a in iguales)),
            "hojas": [] if propias in ([], [dato.hoja]) else propias,
        },
    )
    return [base, *(a.model_copy(deep=True) for a in dato.alternativas)]


def para_hoja(dato: Dato, hoja: str) -> Dato:
    """El dato como lo resuelve una hoja: cada hoja manda sobre lo suyo, sin deshacer lo que el
    dato ya decidió (R141).

    Compiten las lecturas que dice ``hoja`` (su ``hoja`` o en sus ``hojas``) del rango del dato
    elegido —una de menor rango nunca desplaza al ganador: la IA no le gana al plano ni una
    lectura a una decisión ``humano``— y, si el elegido es un valor leído, sólo las leídas: una
    copia ilegible de la hoja no tapa el valor que otra hoja sí leyó (R143). Entre ellas se
    elige con ``elegir``, preferida ``hoja``, junto con las copias del mismo valor de las demás
    hojas (sus ``copias`` y sus ``hojas`` cuentan), así que el dato que resulta es la copia de la
    propia hoja (M-1); lo que dicen las demás hojas queda en ``alternativas`` sin contar como
    conflicto. Una hoja sin lectura propia que compita (o un dato sin hojas, como un supuesto)
    se queda con el dato elegido, con su conflicto a la vista. Siempre devuelve un dato nuevo
    (una copia, si no hay nada que elegir): editarlo no toca ``dato``."""
    todos = miembros(dato)
    rango = PRECEDENCIA[dato.fuente]
    leido = _leido(dato)

    def compite(m: Dato) -> bool:
        return PRECEDENCIA[m.fuente] >= rango and (not leido or _leido(m))

    suyos = {_clave(m.valor) for m in todos if compite(m) and hoja in hojas_de(m)}
    if not suyos:
        return dato.model_copy(deep=True)
    propios = [m for m in todos if compite(m) and _clave(m.valor) in suyos]
    otros = [m for m in todos if not (compite(m) and _clave(m.valor) in suyos)]
    elegido = elegir(propios, preferir_hoja=hoja)
    assert elegido is not None  # ``propios`` no está vacío
    return elegido.model_copy(update={"alternativas": [*elegido.alternativas, *otros]})
