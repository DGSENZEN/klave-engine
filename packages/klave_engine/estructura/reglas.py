"""Las reglas de armado que el plano dicta: la tabla de varillas (anclajes, traslapes, ganchos).

La tabla de varillas es la tabla estándar de las hojas estructurales: por número de varilla,
el anclaje (LA1, LA2), el traslape (LT1, LT2), las patas del gancho (LG1–LG3) y el radio de
doblez r, todo en centímetros. Cuando el plano la trae manda el plano —viaja en los bloques de
notas y especificaciones, así que hay una copia por cada vez que se inserta (20 en Marina, una
por hoja)—; cuando no, se usa la estándar y se dice que es un supuesto.

Dos listas distintas salen de aquí y no se mezclan: las contradicciones son las copias que se
desmienten entre sí; los avisos son lo que no se pudo leer de una tabla (una celda ilegible o
fuera de rango, un texto con cifras que no cayó en ninguna celda, un renglón en blanco que
cortó la tabla, un encabezado que no se pudo leer)."""

import re
from collections import defaultdict
from collections.abc import Callable

from pydantic import BaseModel

from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.estructura.armado import NUMEROS
from klave_engine.estructura.dato import Dato, elegir
from klave_engine.estructura.tablas import (
    Tabla,
    TextoSinCelda,
    fila_para_avisar,
    leer_tablas,
    parece_celda,
)

CAMPOS_VARILLA = ("LA1", "LA2", "LT1", "LT2", "LG1", "LG2", "LG3", "r")
ANCLA_VARILLA = "VARILLA"
ENCABEZADOS_VARILLA = (ANCLA_VARILLA, *CAMPOS_VARILLA)
_TITULO = "TABLA DE VARILLAS"
# Un valor de la tabla (cm) fuera de esto es un error de dedo o de lectura, no una longitud.
_MINIMO_CM = 1.0
_MAXIMO_CM = 400.0


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


_LETRAS = "A-Za-zÁÉÍÓÚÜÑáéíóúüñ"
# Lo que acompaña al número en una etiqueta: «#», «No.», «Nº», «VAR», «VARILLA», «Ø», «%%C».
_ADORNO_DE_ETIQUETA = re.compile(
    rf"[#Ø⌀∅]|%%[Cc]|(?<![{_LETRAS}])(?:VARILLAS?|VAR|NO|N[º°])\.?(?![{_LETRAS}])",
    re.IGNORECASE,
)
_SEPARADOR_DE_ETIQUETA = re.compile(r"[()\[\]=:;\-–—]")
# Un número de varilla escrito de alguna manera: una fracción de pulgada («3/8"», «1 1/4"»),
# pulgadas enteras («1"») o el número («3», «2.5», «2,5»).
_ATOMO = re.compile(
    r"""(?:(?P<entero>\d+)\s+)?(?P<num>\d+)\s*/\s*(?P<den>\d+)\s*["”″']{0,2}
    |(?P<pulgadas>\d+)\s*["”″']{1,2}
    |(?P<numero>\d+(?:[.,]\d+)?)""",
    re.VERBOSE,
)
# La varilla de cada fracción de pulgada, con su número mexicano (octavos de pulgada).
_PULGADAS = {
    (0, 1, 4): "2",
    (0, 5, 16): "2.5",
    (0, 3, 8): "3",
    (0, 1, 2): "4",
    (0, 5, 8): "5",
    (0, 3, 4): "6",
    (0, 7, 8): "7",
    (1, 0, 1): "8",
    (1, 1, 4): "10",
    (1, 1, 2): "12",
}


def _numeros_de(texto: str) -> list[str] | None:
    """Los números de varilla que dice una etiqueta, uno por cada forma en que lo escribe
    («#3 (3/8")» da dos: ``["3", "3"]``); ``""`` en el lugar de una forma que no es una varilla
    («3/16"»). ``None`` si la etiqueta trae algo más que un número (palabras, otro texto)."""
    limpio = _ADORNO_DE_ETIQUETA.sub(" ", texto)
    limpio = re.sub(r"(\d)\s*-\s*(\d+/\d+)", r"\1 \2", limpio)  # «1-1/4"»
    limpio = _SEPARADOR_DE_ETIQUETA.sub("|", limpio)
    if re.sub(r"[\s|]", "", _ATOMO.sub(" ", limpio)):
        return None
    numeros: list[str] = []
    for m in _ATOMO.finditer(limpio):
        if m["num"]:
            clave = (int(m["entero"] or 0), int(m["num"]), int(m["den"]))
            numeros.append(_PULGADAS.get(clave, ""))
        elif m["pulgadas"]:
            numeros.append(_PULGADAS.get((int(m["pulgadas"]), 0, 1), ""))
        else:
            numeros.append(m["numero"].replace(",", "."))
    return numeros or None


def numero_de_varilla(texto: str) -> str | None:
    """El número de varilla que dice ``texto``, o ``None`` si no es uno.

    Se leen las maneras comunes de escribirlo: «3», «2.5», «#3», «No. 3», «Nº3», «VAR 3»,
    «VARILLA 3», «Ø3», «%%C3» y las fracciones de pulgada con su número mexicano («3/8"» es
    el 3, «1/2"» el 4, «1"» el 8…). Una etiqueta que da dos formas («#3 (3/8")») debe decir lo
    mismo en las dos. Sólo valen los de ``NUMEROS``: «No.», «(cm)», «9», «2.50», «3/16"» y
    cualquier otra celda de la columna no son un renglón de la tabla."""
    numeros = _numeros_de(texto)
    if not numeros or len(set(numeros)) != 1:
        return None
    return numeros[0] if numeros[0] in NUMEROS else None


def leer_tablas_de_varillas(
    textos: list[NormalizedEntity],
    hoja_de: Callable[[NormalizedEntity], str],
    *,
    hueco_maximo: float = 2.5,
) -> list[Tabla]:
    """Las tablas de varillas de ``textos``: sus renglones son sólo números de varilla.

    ``hueco_maximo`` es el de ``leer_tablas``: cuántos pasos entre renglones puede haber en
    blanco sin que la tabla se corte."""
    return leer_tablas(
        textos,
        ENCABEZADOS_VARILLA,
        ANCLA_VARILLA,
        hoja_de,
        fila_valida=lambda texto: numero_de_varilla(texto) is not None,
        fila_probable=lambda texto: _numeros_de(texto) is not None,
        hueco_maximo=hueco_maximo,
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
    """Las filas de una tabla leída, con un aviso por cada celda que no se pudo leer, que no es
    plausible o que se repite. Los avisos no nombran la hoja: ``tabla_de_varillas`` la añade."""
    filas: dict[str, FilaVarilla] = {}
    avisos: list[str] = []
    etiquetas = [fila.get(ANCLA_VARILLA, "") for fila in tabla.filas]
    ultimo_valido = max(
        (i for i, e in enumerate(etiquetas) if numero_de_varilla(e) is not None), default=-1
    )
    for i, fila in enumerate(tabla.filas):
        etiqueta = etiquetas[i]
        numero = numero_de_varilla(etiqueta)
        if numero is None:
            con_valores = any(parece_celda(v) for c, v in fila.items() if c != ANCLA_VARILLA)
            if con_valores or fila_para_avisar(etiqueta, i < ultimo_valido):  # no es esconder
                avisos.append(_aviso_fila_descartada(etiqueta))
            continue  # «No.», «(cm)» y demás: no son un renglón
        valores: dict[str, float | None] = {}
        for campo in CAMPOS_VARILLA:
            valor = _centimetros(fila[campo]) if campo in fila else None
            if isinstance(valor, str):
                avisos.append(
                    f"la celda {campo} de la varilla #{numero} dice «{valor}» y no es un "
                    "número; queda sin valor"
                )
                valor = None
            elif valor is not None and not _MINIMO_CM <= valor <= _MAXIMO_CM:
                avisos.append(
                    f"la celda {campo} de la varilla #{numero} dice {valor:g}, fuera de lo "
                    f"posible ({_MINIMO_CM:g}–{_MAXIMO_CM:g} cm); queda sin valor"
                )
                valor = None
            valores[campo] = valor
        leida = FilaVarilla(**valores)
        if numero in filas and filas[numero] != leida:
            avisos.append(
                f"la varilla #{numero} aparece dos veces con valores distintos; vale la primera"
            )
        filas.setdefault(numero, leida)
    # Una fila sin un solo valor legible no es un dato: taparía la estándar con nada.
    vacias = [n for n, f in filas.items() if all(getattr(f, c) is None for c in CAMPOS_VARILLA)]
    if filas and len(vacias) == len(filas):
        avisos.append("ninguna celda de valores de la tabla se pudo leer; no se usa")
        return {}, avisos
    for numero in vacias:
        avisos.append(f"la varilla #{numero} no trae ningún valor legible; no se usa")
        del filas[numero]
    return filas, avisos


def _aviso_fila_descartada(texto: str) -> str:
    numeros = _numeros_de(texto) or []
    if "" not in numeros and len(set(numeros)) > 1:
        dicen = " y ".join(f"#{n}" for n in dict.fromkeys(numeros))
        return f"la fila «{texto}» dice varillas distintas ({dicen}); no se lee"
    return f"la fila «{texto}» no es un número de varilla; no se lee"


def _como_varilla(texto: str | None) -> str:
    """«#8» si el texto es un número de varilla; si no, el texto tal cual."""
    if texto is None:
        return ""
    numero = numero_de_varilla(texto)
    return f"#{numero}" if numero is not None else f"«{texto}»"


def _avisos_sin_celda(sin: list[TextoSinCelda]) -> list[str]:
    """Una frase por cada texto con cifras de la tabla que no entró en ninguna celda; lo que
    quedó tras un hueco va junto en una sola."""
    avisos: list[str] = []
    tras_el_hueco = [s for s in sin if s.motivo == "tras_un_hueco"]
    for s in sin:
        cerca = f" (la fila más cercana es {_como_varilla(s.renglon)})" if s.renglon else ""
        if s.motivo == "fuera_de_columna":
            avisos.append(
                f"el texto «{s.texto}» está dentro de la tabla pero no cae en ninguna columna"
                f"{cerca}; no se usa"
            )
        elif s.motivo == "fuera_de_renglon":
            columna = f" (columna {s.columna})" if s.columna else ""
            avisos.append(
                f"el texto «{s.texto}»{columna} no está sobre la línea de ninguna varilla"
                f"{cerca}; no se usa"
            )
        elif s.motivo == "fila_descartada":
            avisos.append(_aviso_fila_descartada(s.texto))
    if tras_el_hueco:
        # Se nombran todos los renglones que no se leen; las celdas, por cuántas son. En la
        # columna de las varillas sólo cuentan los que son o parecen una varilla: una nota o
        # una unidad que sigue ahí no es un renglón que falte.
        filas = [
            s.texto
            for s in tras_el_hueco
            if s.columna == ANCLA_VARILLA
            and (numero_de_varilla(s.texto) or fila_para_avisar(s.texto, False))
        ]
        celdas = sum(1 for s in tras_el_hueco if s.columna != ANCLA_VARILLA)
        de_celdas = f" (con {celdas} textos más en sus celdas)" if celdas else ""
        if filas:
            nombres = ", ".join(f"«{t}»" for t in filas)
            avisos.append(
                f"la tabla sigue después de un hueco y esos renglones no se leen: {nombres}"
                f"{de_celdas}"
            )
        else:
            avisos.append(f"la tabla sigue después de un hueco y {celdas} textos no se leen")
    return avisos


def _cm(valor: float | None) -> str:
    if valor is None:
        return "sin valor"
    return f"{valor:g} cm"


def _en_hojas(hojas: list[str]) -> str:
    """Las hojas donde se lee algo; con muchas copias, cuántas."""
    distintas = list(dict.fromkeys(hojas))
    if len(distintas) > 4:
        return f"{len(distintas)} copias"
    return ", ".join(distintas)


def _unir_avisos(por_tabla: list[tuple[str, list[str]]]) -> list[str]:
    """Los avisos de todas las tablas, uno por frase: la misma frase en varias copias es una
    sola con cuántas copias la traen."""
    donde: dict[str, list[str]] = {}
    for hoja, avisos in por_tabla:
        for aviso in dict.fromkeys(avisos):
            donde.setdefault(aviso, []).append(hoja)
    frases = []
    for aviso, hojas in donde.items():
        if len(hojas) == 1:
            frases.append(f"Tabla de varillas ({hojas[0]}): {aviso}.")
        else:
            nombres = f": {_en_hojas(hojas)}" if len(hojas) <= 4 else ""
            frases.append(f"Tabla de varillas (en {len(hojas)} copias{nombres}): {aviso}.")
    return frases


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


def tabla_de_varillas(tablas: list[Tabla]) -> tuple[Dato, list[str], list[str]]:
    """La tabla de varillas del plano, o la estándar como supuesto si el plano no la trae.

    Devuelve ``(dato, contradicciones, avisos)``. Lee las ``tablas`` que tienen los
    encabezados de la tabla de varillas; sólo los renglones cuyo primer texto es un número de
    varilla cuentan. Dos tablas son copias cuando dicen lo mismo: ``Dato.copias`` es cuántas
    leyó. Si difieren, gana la lectura repetida (si no, la de la hoja menor, como ``elegir``),
    ``en_conflicto`` queda marcado y ``contradicciones`` trae una frase por cada diferencia
    con la varilla, el campo y los dos valores: sólo las copias que se desmienten están ahí.

    ``avisos`` es todo lo demás que no se pudo leer, sin adivinar: una celda que no es un
    número o que no cabe en 1–400 cm (queda vacía), una varilla repetida, un texto con
    cifras dentro de la tabla que no cayó en ninguna celda, la tabla que sigue después de un
    hueco, una fila con cifras que no es una varilla de ``NUMEROS`` (o que dice dos varillas
    distintas), una fila sin un solo valor legible (no se usa, para no tapar a la estándar
    con nada; si son todas, no se usa la tabla), un renglón de encabezados que no se pudo
    leer (en orden, sin una ficha repetida). La misma frase en varias copias sale una vez, con
    cuántas copias la traen. Aun si ninguna tabla se pudo leer y se devuelve la estándar, los
    avisos dicen qué tabla del plano se dejó."""
    datos: list[Dato] = []
    leidas: list[tuple[str, dict[str, FilaVarilla]]] = []
    por_tabla: list[tuple[str, list[str]]] = []
    for tabla in tablas:
        if tuple(tabla.encabezados) != ENCABEZADOS_VARILLA:
            continue
        filas, avisos_de_celdas = _filas_de(tabla)
        avisos = [*tabla.avisos, *_avisos_sin_celda(tabla.sin_celda), *avisos_de_celdas]
        if avisos:
            por_tabla.append((tabla.hoja, avisos))
        if not filas:
            continue
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
    avisos_finales = _unir_avisos(por_tabla)
    dato = elegir(datos)
    if dato is None:
        estandar = {n: f.model_copy() for n, f in TABLA_ESTANDAR.items()}
        supuesto = Dato(valor=estandar, fuente="supuesto", texto=f"{_TITULO} estándar")
        return supuesto, [], avisos_finales
    return dato, _contradicciones(leidas), avisos_finales
