"""Las reglas de armado del proyecto, leídas del plano: la tabla de varillas, las notas numeradas
y lo que el dibujante declara en el dibujo (un anclaje, la plantilla).

La tabla de varillas es la tabla estándar de las hojas estructurales: por número de varilla,
el anclaje (LA1, LA2), el traslape (LT1, LT2), las patas del gancho (LG1–LG3) y el radio de
doblez r, todo en centímetros. Cuando el plano la trae manda el plano —viaja en los bloques de
notas y especificaciones, así que hay una copia por cada vez que se inserta (20 en Marina, una
por hoja)—; cuando no, se usa la estándar y se dice que es un supuesto. Una varilla que la tabla
del plano no trae se completa con la de la estándar, y se avisa.

Las notas dan el resto: recubrimientos por familia, ganchos de estribos y grapas, hasta qué
varilla se traslapa y desde cuál se suelda, el primer estribo; los textos sueltos, los anclajes
declarados y la plantilla. Cada regla es un ``Dato`` con su fuente; lo que el plano no dice es
``supuesto`` (o no hay). Las copias que dicen lo mismo se cuentan; las que no, se marcan y se
dicen, y gana la lectura más repetida: nunca se escoge en silencio.

Dos listas distintas salen de aquí y no se mezclan: las contradicciones son el plano contra sí
mismo (copias de la tabla o de una nota que se desmienten, una nota contra la tabla); los avisos
son lo que no se pudo leer o se leyó con una salvedad (una celda ilegible o fuera de rango, un
texto con cifras que no cayó en ninguna celda, un renglón en blanco que cortó la tabla, un
encabezado que no se pudo leer, un rango de recubrimiento, una varilla completada con la
estándar)."""

import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from klave_engine.detection.frames import SheetFrame
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.estructura.armado import NUMEROS
from klave_engine.estructura.asociacion import ancla_texto
from klave_engine.estructura.dato import Dato, Fuente, elegir
from klave_engine.estructura.notas import (
    Nota,
    donde_estan,
    en_hojas,
    leer_notas_con_renglones,
    limpiar_texto,
    mayusculas_sin_acentos,
)
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
            nombres = f": {en_hojas(hojas)}" if len(hojas) <= 4 else ""
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
            donde = en_hojas([hoja for hoja, _ in con])
            frases.append(
                f"La varilla #{numero} está en la tabla de varillas de {donde} "
                f"y falta en la de {en_hojas(sin)}."
            )
        for campo in CAMPOS_VARILLA:
            grupos: dict[float | None, list[str]] = defaultdict(list)
            for hoja, fila in con:
                grupos[getattr(fila, campo)].append(hoja)
            if len(grupos) > 1:
                lecturas = " y ".join(
                    f"{_cm(valor)} en {en_hojas(hojas)}" for valor, hojas in grupos.items()
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


# --- Las reglas del proyecto: la tabla, las notas numeradas y lo que el plano declara -------------

# El recubrimiento (m) que se usa cuando el plano no lo dice: lo corriente en México.
RECUBRIMIENTO_SUPUESTO: dict[str, float] = {
    "zapata": 0.05,
    "dado": 0.05,
    "pilote": 0.05,
    "contratrabe": 0.05,
    "losa_cimentacion": 0.05,
    "columna": 0.05,
    "trabe": 0.04,
    "losa": 0.04,
    "muro_concreto": 0.04,
    "castillo": 0.03,
    "dala": 0.03,
    "cerramiento": 0.03,
}
_GANCHO_ESTRIBO = {"angulo": 135, "recto_diametros": 10}
_GANCHO_GRAPA = {"angulo": 180, "recto_diametros": 10}
# Lo posible, en cm: fuera de esto es un error de dedo o de lectura, no una regla.
_COBERTURA_CM = (0.5, 15.0)
_PRIMER_ESTRIBO_CM = (1.0, 30.0)
_ANCLAJE_CM = (5.0, 400.0)
_PLANTILLA_CM = (2.0, 20.0)


class Reglas(BaseModel):
    """Las reglas de armado del proyecto, cada una un ``Dato`` con su fuente.

    ``tabla_varillas`` es la tabla del plano (``cuadro``) con la estándar para las varillas que el
    plano no trae, o la estándar entera (``supuesto``). ``recubrimiento_m`` trae todas las
    familias: de la nota, o el supuesto. ``gancho_estribo`` y ``gancho_grapa`` valen
    ``{"angulo", "recto_diametros"}``. Lo que el plano no dice queda en ``None`` (o vacío).
    ``contradicciones`` es lo que el plano se desmiente a sí mismo; ``avisos``, lo que no se pudo
    leer o se leyó con una salvedad: no se mezclan."""

    tabla_varillas: Dato
    recubrimiento_m: dict[str, Dato]
    gancho_estribo: Dato
    gancho_grapa: Dato
    soldar_desde_numero: Dato | None = None
    traslape_max_numero: Dato | None = None
    primer_estribo_m: Dato | None = None
    primer_estribo_familias: list[str] = []
    anclajes_declarados_m: dict[str, Dato] = {}
    plantilla_espesor_m: Dato | None = None
    contradicciones: list[str] = []
    avisos: list[str] = []


def _recubrimientos_supuestos() -> dict[str, Dato]:
    return {
        familia: Dato(
            valor=valor,
            fuente="supuesto",
            texto=f"Recubrimiento estándar de {familia}: el plano no lo dice",
        )
        for familia, valor in RECUBRIMIENTO_SUPUESTO.items()
    }


def _gancho_supuesto(estribo: bool) -> Dato:
    valor = dict(_GANCHO_ESTRIBO if estribo else _GANCHO_GRAPA)
    nombre = "estribo" if estribo else "grapa"
    return Dato(
        valor=valor,
        fuente="supuesto",
        texto=f"Gancho estándar de {nombre}: {valor['angulo']}° y tramo recto de 10Ø",
    )


def reglas_estandar() -> Reglas:
    """Las reglas cuando el plano no dice nada: todo es supuesto (o no hay)."""
    tabla, _, _ = tabla_de_varillas([])
    return Reglas(
        tabla_varillas=tabla,
        recubrimiento_m=_recubrimientos_supuestos(),
        gancho_estribo=_gancho_supuesto(True),
        gancho_grapa=_gancho_supuesto(False),
    )


# Las palabras con las que las notas nombran a los elementos, en mayúsculas y sin acentos. Cada
# palabra se retira del texto al usarla: «LOSAS DE CIMENTACION» no es también «CIMENTACION».
_PALABRAS_DE_COBERTURA: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = tuple(
    (re.compile(patron), familias)
    for patron, familias in (
        (r"LOSAS?\s+DE\s+CIMENTACION", ("losa_cimentacion",)),
        (r"CIMENTACION", ("zapata", "dado", "pilote", "contratrabe", "losa_cimentacion")),
        (r"ZAPATAS?", ("zapata",)),
        (r"DADOS?", ("dado",)),
        (r"PILOTES?", ("pilote",)),
        (r"CONTRATRABES?", ("contratrabe",)),
        (r"TRABES?", ("trabe",)),
        (r"COLUMNAS?", ("columna",)),
        (r"LOSAS?", ("losa",)),
        (r"MUROS?\s+DE\s+CONCRETO", ("muro_concreto",)),
        (r"CASTILLOS?", ("castillo",)),
        (r"CADENAS?|DALAS?", ("dala",)),
        (r"CERRAMIENTOS?", ("cerramiento",)),
    )
)
# El primer estribo se pone en las vigas y, si la nota lo dice, en otros elementos; «trabes»
# incluye a las contratrabes.
_PALABRAS_DE_ESTRIBO: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = tuple(
    (re.compile(patron), familias)
    for patron, familias in (
        (r"CONTRATRABES?", ("contratrabe",)),
        (r"TRABES?", ("trabe", "contratrabe")),
        (r"COLUMNAS?", ("columna",)),
        (r"CASTILLOS?", ("castillo",)),
        (r"CADENAS?|DALAS?", ("dala",)),
        (r"CERRAMIENTOS?", ("cerramiento",)),
    )
)
_ELEMENTO_DE_ANCLAJE = {
    "CASTILLO": "castillo",
    "COLUMNA": "columna",
    "DALA": "dala",
    "CADENA": "dala",
    "CERRAMIENTO": "cerramiento",
    "TRABE": "trabe",
    "CONTRATRABE": "contratrabe",
    "DADO": "dado",
    "ZAPATA": "zapata",
    "MURO": "muro_concreto",
}

_NUM = r"\d+(?:[.,]\d+)?"
_COBERTURA = re.compile(rf"({_NUM})(?:\s*A\s*({_NUM}))?\s*CMS?\b\.?\s+(?:LIBRES?\s+)?EN\s+")
_UN_VALOR_EN_CM = re.compile(r"\d\s*CMS?\b")
_FIN_DE_LISTA = re.compile(r"\.(?:\s|$)|\bEN\s+CASO\b|\bSERAN?\b|\bCUANDO\b|\bSI\b")
_TRASLAPAR_HASTA = re.compile(
    r"TRASLAPAR\s+(?:LA\s+)?VARILLAS?\s+HASTA\s+EL\s+(?:#|N[O°º]\.?)\s*(\d+(?:[.,]\d)?)"
)
_SOLDAR_DESDE = re.compile(
    r"DEL\s+(?:#|N[O°º]\.?)\s*(\d+(?:[.,]\d)?)\s+Y\s+DIAMETROS\s+MAYORES\s+SE\s+SOLDAR\w*"
)
_PRIMER_ESTRIBO = re.compile(rf"PRIMER\s+ESTRIBO\s+(?:[A-Z]+\s+){{0,3}}?A\s+({_NUM})\s*CMS?\b")
_DOBLEZ = re.compile(
    r"DOBLEZ(?:ES)?\s+A\s+(\d{2,3})\s*(?:°|º|GRADOS)\s*Y\s*(\d{2,3})\s*(?:°|º|GRADOS)"
)
_TRAMO_RECTO = re.compile(rf"RECTO\s+DE\s+({_NUM})\s*(?:Ø|⌀|DIAMETROS?)")
_ARTICULO = r"(?:LOS\s+|LAS\s+|LA\s+|EL\s+)?"
_ANCLAJES = (
    re.compile(
        rf"(?P<n>{_NUM})\s*CMS?\.?\s+(?:DE\s+)?ANCLAJE\s+(?:DE|EN)\s+{_ARTICULO}(?P<p>[A-Z]+)"
    ),
    re.compile(rf"ANCLAJE\s+(?:DE|EN)\s+{_ARTICULO}(?P<p>[A-Z]+)\s*[:=]?\s*(?P<n>{_NUM})\s*CMS?\b"),
)
_PLANTILLAS = (
    re.compile(rf"PLANTILLA\s+(?:DE\s+)?(?P<n>{_NUM})\s*CMS?\b"),
    re.compile(rf"PLANTILLA\b[^.]{{0,120}}?\bESPESOR\s+(?:DE\s+)?(?P<n>{_NUM})\s*CMS?\b"),
)


@dataclass
class _Lectura:
    """Una lectura de una regla: su ``Dato`` y las hojas donde el plano lo dice así."""

    dato: Dato
    hojas: list[str]
    familias: list[str] = field(default_factory=list)


class _Lecturas:
    """Todo lo que el plano dice de cada regla, antes de decidir entre lecturas."""

    def __init__(self) -> None:
        self.por_regla: dict[str, list[_Lectura]] = defaultdict(list)
        self.avisos: list[str] = []

    def poner(
        self, regla: str, dato: Dato, hojas: list[str], familias: list[str] | None = None
    ) -> None:
        self.por_regla[regla].append(_Lectura(dato, hojas, familias or []))

    def avisar(self, frase: str) -> None:
        if frase not in self.avisos:
            self.avisos.append(frase)


def _numero(texto: str) -> float:
    return float(texto.replace(",", "."))


def _metros(centimetros: float) -> float:
    return round(centimetros / 100, 4)


def _metros_en_cm(metros: float) -> str:
    return _cm(round(metros * 100, 4))


def _listar(nombres: list[str]) -> str:
    if len(nombres) <= 1:
        return "".join(nombres)
    return f"{', '.join(nombres[:-1])} y {nombres[-1]}"


def _familias_en(
    texto: str, palabras: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...]
) -> list[str]:
    """Los elementos que nombra ``texto`` (mayúsculas, sin acentos), en el orden en que aparecen."""
    encontradas: list[tuple[int, tuple[str, ...]]] = []
    restante = texto
    for patron, familias in palabras:
        for m in patron.finditer(restante):
            encontradas.append((m.start(), familias))
        restante = patron.sub(lambda m: " " * len(m.group(0)), restante)
    nombres: list[str] = []
    for _, familias in sorted(encontradas):
        nombres += [f for f in familias if f not in nombres]
    return nombres


def _cita(texto: str, inicio: int, fin: int, largo: int = 200) -> str:
    """El tramo del texto que respalda una lectura, sin pasar de ``largo`` letras antes."""
    return texto[max(0, inicio, fin - largo) : fin].strip(" ,;:")


@dataclass
class _Origen:
    """De dónde sale un texto que se lee: su hoja, sus entidades, la fuente y cuántas copias."""

    texto: str
    fuente: Fuente
    hoja: str
    hojas: list[str]
    entidades: list[str]
    copias: int
    donde: str  # cómo se nombra en un aviso: «La nota 4 de REFUERZO»

    def dato(self, valor: Any, cita: str) -> Dato:
        return Dato(
            valor=valor,
            fuente=self.fuente,
            hoja=self.hoja,
            texto=cita,
            entidades=list(self.entidades),
            copias=self.copias,
        )


def _recubrimientos_de(o: _Origen, mayus: str, lecturas: _Lecturas) -> None:
    if "RECUBRIMIENTO" not in mayus:
        return
    encontrados = list(_COBERTURA.finditer(mayus))
    if not encontrados and _UN_VALOR_EN_CM.search(mayus):
        lecturas.avisar(
            f"{o.donde} habla del recubrimiento con una medida en cm pero no dice «N CM EN "
            "<elementos>»; no se usa."
        )
    for k, m in enumerate(encontrados):
        fin = encontrados[k + 1].start() if k + 1 < len(encontrados) else len(mayus)
        resto = mayus[m.end() : fin]
        corte = _FIN_DE_LISTA.search(resto)
        lista = resto[: corte.start()] if corte else resto
        cita = _cita(o.texto, m.start(), m.end() + len(lista))
        bajo, alto = _numero(m.group(1)), (_numero(m.group(2)) if m.group(2) else None)
        minimo = bajo if alto is None or bajo <= alto else alto
        familias = _familias_en(lista, _PALABRAS_DE_COBERTURA)
        if not familias:
            lecturas.avisar(
                f"{o.donde} da un recubrimiento de {m.group(1)} cm «{lista.strip(' ,')}» pero no "
                "se reconoce a qué elementos; no se usa."
            )
            continue
        if not _COBERTURA_CM[0] <= minimo <= _COBERTURA_CM[1]:
            lecturas.avisar(
                f"{o.donde} da un recubrimiento de {minimo:g} cm para {_listar(familias)}, fuera "
                f"de lo posible ({_COBERTURA_CM[0]:g}–{_COBERTURA_CM[1]:g} cm); no se usa."
            )
            continue
        if alto is not None:
            escrito = m.group(1) if minimo == bajo else m.group(2)
            lecturas.avisar(
                f"El recubrimiento de {_listar(familias)} va de {m.group(1)} a {m.group(2)} cm "
                f"({o.donde[0].lower()}{o.donde[1:]}); se toma el mínimo ({escrito} cm)."
            )
        for familia in familias:
            lecturas.poner(f"recubrimiento:{familia}", o.dato(_metros(minimo), cita), o.hojas)


def _numero_de_varilla_en(o: _Origen, texto: str, cita: str, lecturas: _Lecturas) -> str | None:
    numero = texto.replace(",", ".")
    if numero in NUMEROS:
        return numero
    lecturas.avisar(f"{o.donde} dice «{cita}» y #{numero} no es un número de varilla; no se usa.")
    return None


def _traslape_y_soldadura_de(o: _Origen, mayus: str, lecturas: _Lecturas) -> None:
    for regla, patron in (("traslape", _TRASLAPAR_HASTA), ("soldar", _SOLDAR_DESDE)):
        for m in patron.finditer(mayus):
            cita = _cita(o.texto, m.start(), m.end())
            numero = _numero_de_varilla_en(o, m.group(1), cita, lecturas)
            if numero is not None:
                lecturas.poner(regla, o.dato(numero, cita), o.hojas)


def _primer_estribo_de(o: _Origen, mayus: str, lecturas: _Lecturas) -> None:
    for m in _PRIMER_ESTRIBO.finditer(mayus):
        centimetros = _numero(m.group(1))
        fin = m.end() + (1 if mayus[m.end() : m.end() + 1] == "." else 0)
        cita = _cita(o.texto, 0, fin)
        familias = _familias_en(mayus[: m.start()], _PALABRAS_DE_ESTRIBO)
        if not _PRIMER_ESTRIBO_CM[0] <= centimetros <= _PRIMER_ESTRIBO_CM[1]:
            lecturas.avisar(
                f"{o.donde} da el primer estribo a {centimetros:g} cm, fuera de lo posible "
                f"({_PRIMER_ESTRIBO_CM[0]:g}–{_PRIMER_ESTRIBO_CM[1]:g} cm); no se usa."
            )
            continue
        if not familias:
            lecturas.avisar(
                f"{o.donde} da el primer estribo a {centimetros:g} cm pero no dice en qué "
                "elementos; no se sabe a cuáles aplica."
            )
        texto = f"{cita} (aplica a: {', '.join(familias)})" if familias else cita
        lecturas.poner("primer_estribo", o.dato(_metros(centimetros), texto), o.hojas, familias)


def _ganchos_de(o: _Origen, mayus: str, lecturas: _Lecturas) -> None:
    for m in _DOBLEZ.finditer(mayus):
        antes = mayus[: m.start()]
        estribo, grapa = antes.rfind("ESTRIBO"), antes.rfind("GRAPA")
        angulos = (int(m.group(1)), int(m.group(2)))
        if estribo < 0 or grapa < 0:
            lecturas.avisar(
                f"{o.donde} da dobleces a {angulos[0]}° y {angulos[1]}° pero no dice cuál es de "
                "estribos y cuál de grapas; no se usa."
            )
            continue
        angulo_estribo, angulo_grapa = angulos if estribo < grapa else angulos[::-1]
        recto = _TRAMO_RECTO.search(mayus, m.end())
        if recto is None:
            lecturas.avisar(
                f"{o.donde} da los dobleces pero no dice el tramo recto del gancho; se usa el de "
                f"{_GANCHO_ESTRIBO['recto_diametros']}Ø (supuesto)."
            )
            diametros: float = _GANCHO_ESTRIBO["recto_diametros"]
            fin = m.end()
        else:
            diametros = _numero(recto.group(1))
            fin = recto.end()
        cita = _cita(o.texto, m.start() - 70, fin)
        diametros_en_numero: int | float = int(diametros) if diametros.is_integer() else diametros
        for regla, angulo in (("gancho_estribo", angulo_estribo), ("gancho_grapa", angulo_grapa)):
            valor = {"angulo": angulo, "recto_diametros": diametros_en_numero}
            lecturas.poner(regla, o.dato(valor, cita), o.hojas)


def _anclajes_y_plantilla_de(o: _Origen, mayus: str, lecturas: _Lecturas) -> None:
    """Los anclajes que el plano declara («100CM ANCLAJE DE CASTILLO») y la plantilla."""
    if "ANCLAJE" in mayus:
        for patron in _ANCLAJES:
            for m in patron.finditer(mayus):
                cita = _cita(o.texto, m.start(), m.end())
                palabra = m.group("p")
                familia = next(
                    (f for p, f in _ELEMENTO_DE_ANCLAJE.items() if palabra.startswith(p)), None
                )
                centimetros = _numero(m.group("n"))
                if familia is None:
                    lecturas.avisar(
                        f"El plano declara un anclaje de {centimetros:g} cm «{cita}» para "
                        f"«{palabra}», que no se reconoce como un elemento; no se usa."
                    )
                elif not _ANCLAJE_CM[0] <= centimetros <= _ANCLAJE_CM[1]:
                    lecturas.avisar(
                        f"El anclaje de {familia} dice {centimetros:g} cm «{cita}», fuera de lo "
                        f"posible ({_ANCLAJE_CM[0]:g}–{_ANCLAJE_CM[1]:g} cm); no se usa."
                    )
                else:
                    lecturas.poner(
                        f"anclaje:{familia}", o.dato(_metros(centimetros), cita), o.hojas
                    )
    if "PLANTILLA" in mayus:
        for patron in _PLANTILLAS:
            hallada = patron.search(mayus)
            if hallada is None:
                continue
            cita = _cita(o.texto, hallada.start(), hallada.end())
            centimetros = _numero(hallada.group("n"))
            if _PLANTILLA_CM[0] <= centimetros <= _PLANTILLA_CM[1]:
                lecturas.poner("plantilla", o.dato(_metros(centimetros), cita), o.hojas)
            else:
                lecturas.avisar(
                    f"La plantilla dice {centimetros:g} cm «{cita}», fuera de lo posible "
                    f"({_PLANTILLA_CM[0]:g}–{_PLANTILLA_CM[1]:g} cm); no se usa."
                )
            break


def _hoja_de_marcos(frames: list[SheetFrame]) -> Callable[[NormalizedEntity], str]:
    """La hoja de una entidad: el código del marco que la contiene (en su archivo); sin marco, el
    archivo."""

    def hoja(e: NormalizedEntity) -> str:
        punto = ancla_texto(e)
        for marco in frames:
            if marco.source_file in ("", e.source_file) and marco.contains(punto):
                return marco.code or marco.frame_id
        return e.source_file

    return hoja


def _tabla_completa(
    tablas: list[Tabla],
) -> tuple[Dato, set[str], list[str], list[str]]:
    """La tabla de varillas de ``Reglas``: la del plano con la estándar para cada varilla que el
    plano no trae. Devuelve la tabla, las varillas que son del plano, las contradicciones y los
    avisos."""
    dato, contradicciones, avisos = tabla_de_varillas(tablas)
    if dato.fuente != "cuadro":
        return dato, set(), contradicciones, avisos
    del_plano = set(dato.valor)
    faltan = [n for n in NUMEROS if n not in del_plano and n in TABLA_ESTANDAR]
    if faltan:
        for numero in faltan:
            dato.valor[numero] = TABLA_ESTANDAR[numero].model_copy()
        dato.valor = {n: dato.valor[n] for n in sorted(dato.valor, key=float)}
        nombres = _listar([f"#{n}" for n in faltan])
        dato.texto = f"{dato.texto}; {nombres} de la tabla estándar (supuesto)"
        plural = len(faltan) > 1
        avisos = [
            *avisos,
            f"La tabla de varillas del plano no trae {'las varillas' if plural else 'la varilla'} "
            f"{nombres}: se {'usan las' if plural else 'usa la'} de la tabla estándar (supuesto).",
        ]
    return dato, del_plano, contradicciones, avisos


def _agrupar(lecturas: list[_Lectura]) -> list[tuple[Any, list[str], int]]:
    """Las lecturas por valor: ``(valor, hojas, copias)``, la más repetida primero."""
    grupos: dict[str, tuple[Any, list[str], int]] = {}
    for lectura in lecturas:
        valor, hojas, copias = grupos.get(repr(lectura.dato.valor), (lectura.dato.valor, [], 0))
        grupos[repr(lectura.dato.valor)] = (
            valor,
            hojas + lectura.hojas,
            copias + lectura.dato.copias,
        )
    return sorted(grupos.values(), key=lambda g: (-g[2], g[1][0]))


def _frase_del_conflicto(
    nombre: str, lecturas: list[_Lectura], formato: Callable[[Any], str]
) -> str:
    partes = [f"{formato(valor)} en {donde_estan(hojas)}" for valor, hojas, _ in _agrupar(lecturas)]
    return f"El plano no dice lo mismo sobre {nombre}: {_listar(partes)}."


def _lista_de_varillas(numeros: list[str]) -> str:
    return _listar([f"#{n}" for n in numeros])


def _contradicciones_de_la_soldadura(
    tabla: Dato, del_plano: set[str], soldaduras: list[_Lectura]
) -> list[str]:
    """La tabla de varillas del plano da traslape para varillas que la nota manda soldar. Sólo
    cuentan las varillas que el plano trae (``del_plano``): las que se completan con la tabla
    estándar son un supuesto, no una lectura."""
    frases: list[str] = []
    grupos = _agrupar(soldaduras)
    for desde, hojas, _ in grupos:
        con_traslape = [
            n
            for n in NUMEROS
            if float(n) >= float(desde)
            and n in del_plano
            and (tabla.valor[n].LT1 is not None or tabla.valor[n].LT2 is not None)
        ]
        if not con_traslape:
            continue
        de_cual = f" (nota de {donde_estan(hojas)})" if len(grupos) > 1 else ""
        frases.append(
            f"La tabla de varillas da traslape para {_lista_de_varillas(con_traslape)}, pero la "
            f"nota dice que del #{desde} en adelante se suelda{de_cual}."
        )
    return frases


def _textos_sueltos(
    entidades: list[NormalizedEntity], consumidas: set[str]
) -> list[tuple[NormalizedEntity, str]]:
    """Los textos del dibujo que no son renglones de una nota: los de texto y los de las cotas
    con texto escrito a mano."""
    sueltos: list[tuple[NormalizedEntity, str]] = []
    for e in entidades:
        if e.entity_id in consumidas:
            continue
        crudo = e.text if e.is_textual else None
        if e.entity_type == EntityType.dimension:
            crudo = e.properties.get("display_text")
        if isinstance(crudo, str) and crudo.strip():
            sueltos.append((e, limpiar_texto(crudo)))
    return sueltos


def leer_reglas(entities: list[NormalizedEntity], frames: list[SheetFrame]) -> Reglas:
    """Las reglas del proyecto, leídas del plano: la tabla de varillas, las notas numeradas y los
    textos que declaran un anclaje o la plantilla.

    La hoja de cada lectura es el marco (``frames``) que la contiene. El plano manda sobre el
    supuesto; las copias que dicen lo mismo se cuentan en ``Dato.copias`` y las que no, marcan
    ``en_conflicto`` y se dicen en ``contradicciones`` (gana la lectura más repetida, nunca en
    silencio). Cada ``contradicción`` es el plano contra sí mismo: copias de la tabla que
    difieren, la nota que manda soldar donde la tabla da traslape, copias de una nota que no
    dicen lo mismo, lecturas de una regla que no coinciden. Los ``avisos`` son lo que no se pudo
    usar (una celda ilegible, un rango de recubrimiento, un número que no es varilla) o se
    completó con un supuesto (una varilla que la tabla del plano no trae)."""
    hoja_de = _hoja_de_marcos(frames)
    textos = [e for e in entities if e.is_textual and e.text]
    tabla, del_plano, contradicciones, avisos = _tabla_completa(
        leer_tablas_de_varillas(textos, hoja_de)
    )
    notas, de_las_notas, consumidas = leer_notas_con_renglones(textos, hoja_de)

    lecturas = _Lecturas()
    for nota in notas:
        _leer_nota(nota, lecturas)
    for e, texto in _textos_sueltos(entities, consumidas):
        mayus = mayusculas_sin_acentos(texto)
        if "ANCLAJE" not in mayus and "PLANTILLA" not in mayus:
            continue
        hoja = hoja_de(e)
        origen = _Origen(texto, "detalle", hoja, [hoja], [e.entity_id], 1, "El plano")
        _anclajes_y_plantilla_de(origen, mayus, lecturas)

    por_regla = lecturas.por_regla

    def elegida(regla: str) -> Dato | None:
        return elegir([lectura.dato for lectura in por_regla.get(regla, [])])

    conflictos: list[str] = []

    def decidir(regla: str, nombre: str, formato: Callable[[Any], str]) -> Dato | None:
        dato = elegida(regla)
        if dato is not None and dato.en_conflicto:
            conflictos.append(_frase_del_conflicto(nombre, por_regla[regla], formato))
        return dato

    recubrimientos = _recubrimientos_supuestos()
    for familia in RECUBRIMIENTO_SUPUESTO:
        dato = decidir(
            f"recubrimiento:{familia}",
            f"el recubrimiento de {familia}",
            _metros_en_cm,
        )
        if dato is not None:
            recubrimientos[familia] = dato

    def gancho(regla: str, supuesto: Dato, nombre: str) -> Dato:
        dato = decidir(
            regla,
            nombre,
            lambda v: f"{v['angulo']}° con tramo recto de {v['recto_diametros']:g}Ø",
        )
        return dato if dato is not None else supuesto

    estribo = gancho("gancho_estribo", _gancho_supuesto(True), "el gancho de los estribos")
    grapa = gancho("gancho_grapa", _gancho_supuesto(False), "el gancho de las grapas")
    soldar = decidir("soldar", "la varilla desde la que se suelda", lambda v: f"#{v}")
    traslape = decidir("traslape", "la varilla hasta la que se traslapa", lambda v: f"#{v}")
    primer = decidir("primer_estribo", "el primer estribo", _metros_en_cm)
    familias_del_primero: list[str] = []
    if primer is not None:
        for lectura in por_regla["primer_estribo"]:
            if lectura.dato.valor == primer.valor:
                familias_del_primero += [
                    f for f in lectura.familias if f not in familias_del_primero
                ]
    anclajes: dict[str, Dato] = {}
    for regla in sorted(r for r in por_regla if r.startswith("anclaje:")):
        familia = regla.removeprefix("anclaje:")
        dato = decidir(regla, f"el anclaje de {familia}", _metros_en_cm)
        if dato is not None:
            anclajes[familia] = dato
    plantilla = decidir("plantilla", "el espesor de la plantilla", _metros_en_cm)

    del_choque = _contradicciones_de_la_soldadura(tabla, del_plano, por_regla.get("soldar", []))
    return Reglas(
        tabla_varillas=tabla,
        recubrimiento_m=recubrimientos,
        gancho_estribo=estribo,
        gancho_grapa=grapa,
        soldar_desde_numero=soldar,
        traslape_max_numero=traslape,
        primer_estribo_m=primer,
        primer_estribo_familias=familias_del_primero,
        anclajes_declarados_m=anclajes,
        plantilla_espesor_m=plantilla,
        contradicciones=[*contradicciones, *del_choque, *de_las_notas, *conflictos],
        avisos=list(dict.fromkeys([*avisos, *lecturas.avisos])),
    )


def _leer_nota(nota: Nota, lecturas: _Lecturas) -> None:
    donde = f"La nota {nota.numero} de {nota.seccion}" if nota.seccion else f"La nota {nota.numero}"
    origen = _Origen(nota.texto, "nota", nota.hoja, nota.hojas, nota.entidades, nota.copias, donde)
    mayus = mayusculas_sin_acentos(nota.texto)
    _recubrimientos_de(origen, mayus, lecturas)
    _traslape_y_soldadura_de(origen, mayus, lecturas)
    _primer_estribo_de(origen, mayus, lecturas)
    _ganchos_de(origen, mayus, lecturas)
    _anclajes_y_plantilla_de(origen, mayus, lecturas)
