"""Las reglas de armado que el plano dicta: la tabla de varillas (anclajes, traslapes, ganchos).

La tabla de varillas es la tabla estándar de las hojas estructurales: por número de varilla,
el anclaje (LA1, LA2), el traslape (LT1, LT2), las patas del gancho (LG1–LG3) y el radio de
doblez r, todo en centímetros. Cuando el plano la trae manda el plano —en Marina vive en tres
copias—; cuando no, se usa la estándar y se dice que es un supuesto."""

import re
from collections import defaultdict
from collections.abc import Callable

from pydantic import BaseModel

from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.estructura.armado import NUMEROS
from klave_engine.estructura.dato import Dato, elegir
from klave_engine.estructura.tablas import Tabla, leer_tablas

CAMPOS_VARILLA = ("LA1", "LA2", "LT1", "LT2", "LG1", "LG2", "LG3", "r")
ANCLA_VARILLA = "VARILLA"
ENCABEZADOS_VARILLA = (ANCLA_VARILLA, *CAMPOS_VARILLA)
_TITULO = "TABLA DE VARILLAS"


class FilaVarilla(BaseModel):
    """Lo que la tabla dice de un número de varilla, en cm. ``None``: la tabla no lo trae."""

    LA1: float | None = None
    LA2: float | None = None
    LT1: float | None = None
    LT2: float | None = None
    LG1: float | None = None
    LG2: float | None = None
    LG3: float | None = None
    r: float | None = None


def _estandar() -> dict[str, FilaVarilla]:
    filas = {
        "2.5": (30, 30, 30, 40, 20, 10, 5, 4),
        "3": (30, 35, 35, 50, 20, 15, 5, 4),
        "4": (35, 45, 50, 65, 30, 15, 5, 6),
        "5": (40, 60, 60, 80, 35, 20, 10, 7),
        "6": (50, 70, 70, 100, 40, 25, 10, 9),
        "8": (85, 115, None, None, 55, 30, 10, 11),
        "10": (130, 180, None, None, 65, 40, 15, 14),
        "12": (185, 255, None, None, 80, 50, 15, 17),
    }
    return {
        numero: FilaVarilla(**dict(zip(CAMPOS_VARILLA, valores, strict=True)))
        for numero, valores in filas.items()
    }


# La tabla del PDF estándar: a partir de #8 no hay traslape (se suelda).
TABLA_ESTANDAR: dict[str, FilaVarilla] = _estandar()

_VACIO = frozenset({"-", "--", "—", "–", "N/A", "NA"})
_NUMERO_EN_CM = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:CM)?", re.IGNORECASE)


def numero_de_varilla(texto: str) -> str | None:
    """El número de varilla que dice ``texto`` («2.5», «#3», «10»), o ``None`` si no es uno.

    Sólo valen los de ``NUMEROS``: «No.», «(cm)» y cualquier otra celda de la columna no son
    un renglón de la tabla."""
    limpio = texto.strip().removeprefix("#").strip().replace(",", ".")
    return limpio if limpio in NUMEROS else None


def leer_tablas_de_varillas(
    textos: list[NormalizedEntity], hoja_de: Callable[[NormalizedEntity], str]
) -> list[Tabla]:
    """Las tablas de varillas de ``textos``: sus renglones son sólo números de varilla."""
    return leer_tablas(
        textos,
        ENCABEZADOS_VARILLA,
        ANCLA_VARILLA,
        hoja_de,
        fila_valida=lambda texto: numero_de_varilla(texto) is not None,
    )


def _centimetros(texto: str) -> float | None | str:
    """El número de la celda; ``None`` si la celda dice que no hay valor; el texto si no se lee."""
    limpio = " ".join(texto.split())
    if not limpio or limpio.upper() in _VACIO:
        return None
    m = _NUMERO_EN_CM.fullmatch(limpio)
    if m is None:
        return limpio
    return float(m.group(1).replace(",", "."))


def _filas_de(tabla: Tabla) -> tuple[dict[str, FilaVarilla], list[str]]:
    """Las filas de una tabla leída, con un aviso por cada celda que no se pudo leer o repetir."""
    filas: dict[str, FilaVarilla] = {}
    avisos: list[str] = []
    for fila in tabla.filas:
        numero = numero_de_varilla(fila.get(ANCLA_VARILLA, ""))
        if numero is None:
            continue  # «No.», «(cm)» y demás: no son un renglón
        valores: dict[str, float | None] = {}
        for campo in CAMPOS_VARILLA:
            valor = _centimetros(fila[campo]) if campo in fila else None
            if isinstance(valor, str):
                avisos.append(
                    f"Tabla de varillas ({tabla.hoja}): la celda {campo} de la varilla #{numero} "
                    f"dice «{valor}» y no es un número; queda sin valor."
                )
                valor = None
            valores[campo] = valor
        leida = FilaVarilla(**valores)
        if numero in filas and filas[numero] != leida:
            avisos.append(
                f"Tabla de varillas ({tabla.hoja}): la varilla #{numero} aparece dos veces "
                "con valores distintos; vale la primera."
            )
        filas.setdefault(numero, leida)
    return filas, avisos


def _cm(valor: float | None) -> str:
    if valor is None:
        return "sin valor"
    return f"{valor:g} cm"


def _en_hojas(hojas: list[str]) -> str:
    return ", ".join(dict.fromkeys(hojas))


def _contradicciones(leidas: list[tuple[str, dict[str, FilaVarilla]]]) -> list[str]:
    """Cada diferencia entre copias, una frase por varilla y campo (o por fila que falta)."""
    if len(leidas) < 2:
        return []
    frases: list[str] = []
    numeros = sorted({n for _, filas in leidas for n in filas}, key=float)
    for numero in numeros:
        con = [(hoja, filas[numero]) for hoja, filas in leidas if numero in filas]
        sin = [hoja for hoja, filas in leidas if numero not in filas]
        if sin:
            donde = _en_hojas([hoja for hoja, _ in con])
            frases.append(
                f"La varilla #{numero} está en la tabla de varillas de {donde} "
                f"y falta en la de {_en_hojas(sin)}."
            )
        for campo in CAMPOS_VARILLA:
            grupos: dict[float | None, list[str]] = defaultdict(list)
            for hoja, fila in con:
                grupos[getattr(fila, campo)].append(hoja)
            if len(grupos) > 1:
                lecturas = " y ".join(
                    f"{_cm(valor)} en {_en_hojas(hojas)}" for valor, hojas in grupos.items()
                )
                frases.append(
                    f"Las copias de la tabla de varillas no coinciden en #{numero} {campo}: "
                    f"{lecturas}."
                )
    return frases


def tabla_de_varillas(tablas: list[Tabla]) -> tuple[Dato, list[str]]:
    """La tabla de varillas del plano, o la estándar como supuesto si el plano no la trae.

    Lee las ``tablas`` que tienen los encabezados de la tabla de varillas; sólo los renglones
    cuyo primer texto es un número de varilla cuentan. Dos tablas son copias cuando dicen lo
    mismo: ``Dato.copias`` es cuántas leyó. Si difieren, gana la lectura repetida (si no, la
    de la hoja menor, como ``elegir``), ``en_conflicto`` queda marcado y la lista trae una
    frase por cada diferencia con la varilla, el campo y los dos valores. Una celda que no
    es un número se deja vacía y se avisa en la misma lista: nunca se adivina."""
    datos: list[Dato] = []
    leidas: list[tuple[str, dict[str, FilaVarilla]]] = []
    avisos: list[str] = []
    for tabla in tablas:
        if tuple(tabla.encabezados) != ENCABEZADOS_VARILLA:
            continue
        filas, avisos_tabla = _filas_de(tabla)
        if not filas:
            continue
        avisos += avisos_tabla
        leidas.append((tabla.hoja, filas))
        datos.append(
            Dato(
                valor=filas,
                fuente="cuadro",
                hoja=tabla.hoja,
                texto=_TITULO,
                entidades=tabla.entidades,
            )
        )
    dato = elegir(datos)
    if dato is None:
        estandar = {n: f.model_copy() for n, f in TABLA_ESTANDAR.items()}
        return Dato(valor=estandar, fuente="supuesto", texto=f"{_TITULO} estándar"), []
    return dato, avisos + _contradicciones(leidas)
