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
dicen, y gana la lectura más repetida: nunca se escoge en silencio. Una nota sólo da sus reglas si
nada de ella las niega, las acota a un elemento o se quedó sin leer (``_lo_que_la_cambia``); si
no, la nota entera es un aviso: un valor equivocado es peor que uno que falta.

Dos listas distintas salen de aquí y no se mezclan: las contradicciones son el plano contra sí
mismo (copias de la tabla o de una nota que se desmienten, una nota contra la tabla); los avisos
son lo que no se pudo leer o se leyó con una salvedad (una celda ilegible o fuera de rango, un
texto con cifras que no cayó en ninguna celda, un renglón en blanco que cortó la tabla, un
encabezado que no se pudo leer, un rango de recubrimiento, una varilla completada con la
estándar)."""

import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from klave_engine.detection.frames import SheetFrame
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.estructura.armado import NUMEROS
from klave_engine.estructura.asociacion import ancla_texto
from klave_engine.estructura.dato import PRECEDENCIA, Dato, Fuente, elegir, para_hoja
from klave_engine.estructura.frases import (
    ELEMENTO,
    EN_SUS_ELEMENTOS,
    EXCEPCION,
    MEDIDA,
    Frase,
    Lectura,
    en_blanco,
    es_neutra,
    leer_frases,
    numeros_libres,
    validar,
    varilla_de,
)
from klave_engine.estructura.notas import (
    Nota,
    donde_estan,
    leer_notas_con_renglones,
    limpiar_texto,
    mayusculas_sin_acentos,
)
from klave_engine.estructura.oraciones import NEGACION
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
            nombres = f": {donde_estan(hojas)}" if len(hojas) <= 4 else ""
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
            donde = donde_estan([hoja for hoja, _ in con])
            frases.append(
                f"La varilla #{numero} está en la tabla de varillas de {donde} "
                f"y falta en la de {donde_estan(sin)}."
            )
        for campo in CAMPOS_VARILLA:
            grupos: dict[float | None, list[str]] = defaultdict(list)
            for hoja, fila in con:
                grupos[getattr(fila, campo)].append(hoja)
            if len(grupos) > 1:
                lecturas = " y ".join(
                    f"{_cm(valor)} en {donde_estan(hojas)}" for valor, hojas in grupos.items()
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
                hojas=[tabla.hoja],
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
    ``{"angulo", "recto_diametros"}``. ``primer_estribo_m`` y ``anclajes_declarados_m`` van por
    familia (``trabe``, ``castillo``…) y sólo traen las que el plano dice. Lo que el plano no
    dice queda en ``None`` (o vacío). ``contradicciones`` es lo que el plano se desmiente a sí
    mismo; ``avisos``, lo que no se pudo leer o se leyó con una salvedad: no se mezclan.

    Cada regla es el ``Dato`` elegido entre todas las hojas (gana la lectura que más hojas
    repiten); ``para(hoja)`` da las reglas como las resuelve una hoja, que manda sobre lo suyo."""

    tabla_varillas: Dato
    recubrimiento_m: dict[str, Dato]
    gancho_estribo: Dato
    gancho_grapa: Dato
    soldar_desde_numero: Dato | None = None
    traslape_max_numero: Dato | None = None
    primer_estribo_m: dict[str, Dato] = {}
    anclajes_declarados_m: dict[str, Dato] = {}
    plantilla_espesor_m: Dato | None = None
    contradicciones: list[str] = []
    avisos: list[str] = []

    def para(self, hoja: str) -> "Reglas":
        """Las reglas como las resuelve ``hoja``: cada hoja dice sus propias reglas (la de
        cimentación puede traslapar hasta el #6 y la de plantas hasta el #8) y esas son las que
        valen para lo que está en ella. Cada regla se vuelve a elegir entre las lecturas de la
        hoja (``para_hoja``); una hoja sin copia propia de una regla se queda con la elegida
        entre todas, con su ``en_conflicto`` a la vista. Las contradicciones y los avisos son los
        del plano entero. Todo lo que devuelve es una copia: quien lo edita no toca las ``Reglas``
        de las que salió. (Es un trabajo por hoja, no por elemento: quien lo necesita muchas veces
        guarda el resultado de cada hoja.)"""

        def una(dato: Dato | None) -> Dato | None:
            return None if dato is None else para_hoja(dato, hoja)

        def varias(datos: dict[str, Dato]) -> dict[str, Dato]:
            return {clave: para_hoja(dato, hoja) for clave, dato in datos.items()}

        return self.model_copy(
            update={
                "contradicciones": list(self.contradicciones),
                "avisos": list(self.avisos),
                "tabla_varillas": para_hoja(self.tabla_varillas, hoja),
                "recubrimiento_m": varias(self.recubrimiento_m),
                "gancho_estribo": para_hoja(self.gancho_estribo, hoja),
                "gancho_grapa": para_hoja(self.gancho_grapa, hoja),
                "soldar_desde_numero": una(self.soldar_desde_numero),
                "traslape_max_numero": una(self.traslape_max_numero),
                "primer_estribo_m": varias(self.primer_estribo_m),
                "anclajes_declarados_m": varias(self.anclajes_declarados_m),
                "plantilla_espesor_m": una(self.plantilla_espesor_m),
            }
        )


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
    tabla, _, _, _ = _tabla_completa([])
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
        (r"MUROS?\s+DE\s+(?:CONCRETO|CONTENCION)", ("muro_concreto",)),
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
_COMILLAS = "\"”″'"
_UN_VALOR_EN_CM = re.compile(r"\d\s*CMS?\b")
# Las frases que una nota numerada puede decir, y las que cualquier texto (un rótulo, una cota).
_FRASES_DE_NOTA = frozenset(
    "traslape soldar soldar_rango primer_estribo gancho gancho_par gancho_dos tramo plantilla "
    "anclaje recubrimiento recubrimiento_lista inerte acompana_soldar acompana_traslape".split()
)
_FRASES_DE_TEXTO = frozenset({"plantilla", "anclaje"})

# Lo que hace falta para sospechar que un texto dice una regla que no se supo leer.
_CLAVES_DE_REGLA = re.compile(
    r"TRASLAP|SOLDAR|PRIMER\s+ESTRIBO|DOBLEZ|GANCHO|PLANTILLA|RECUBRIMIENTO|ANCLAJE"
)
_MARCA_DE_VARILLA = r"(?:#|NUMERO|NUM\.?|\bN[O°º]\.?)"
_LIMITE = re.compile(
    r"\b(?:HASTA|MAXIM[OA]S?|LIMITE|MAYOR(?:ES)?|MENOR(?:ES)?|ADELANTE|A\s+PARTIR|DESDE"
    r"|MAS\s+DE(?:L|\s+LA)?)\b"
    # «DEL No. 3 AL No. 6»: el «AL» de un rango entre dos varillas marcadas
    rf"|\bA(?:L|\s+LA)\s+{_MARCA_DE_VARILLA}\s*\d"
)
# Un número pelado donde va una varilla («HASTA 6», «DESDE EL 8», «HASTA 12 MM») cuenta, salvo
# que lo siga lo que dice que no lo es: una longitud, un porcentaje, las veces del diámetro, una
# cuenta («HASTA 2 VARILLAS POR SECCION», «HASTA 3 DE LAS 6», «HASTA 2 A LA VEZ»).
_NO_ES_UNA_VARILLA_PELADA = (
    r"(?!\s*(?:%|POR\s*CIENTO|CMS?\b|M\b|MTS?\b|KG|VECES|[Ø⌀]|DIAM\w*|[.,]?\d|/"
    rf"|[{_COMILLAS}]|VARILLAS?\b|BARRAS?\b|VARS?\b|PIEZAS?\b|REDONDOS?\b|EMPALMES?\b"
    r"|TRASLAPES?\b|POR\b|EN\s+UNA\b|DE\s+(?:LAS|LOS|CADA|ELLAS|ELLOS)\b|A\s+LA\s+VEZ"
    r"|AL\s+MISMO))"
)
_SIN_TABLA_NI_FIGURA = (
    r"(?<!TABLA )(?<!NOTA )(?<!FIGURA )(?<!DETALLE )(?<!PLANO )(?<!HOJA )(?<!ARTICULO )"
    r"(?<!ART\. )(?<!INCISO )"
)
# Una varilla marcada como tal: «#8», «No. 8», «NUMERO 8», «VARILLA 8», «DEL 8». Con la palabra
# clave cerca, basta para sospechar una regla.
_VARILLA_MARCADA = re.compile(
    rf"{_SIN_TABLA_NI_FIGURA}{_MARCA_DE_VARILLA}\s*\d{{1,2}}(?:[.,]\d)?\b(?!\s*(?:%|CMS?\b|VECES))"
    r"|\bDEL\s+\d{1,2}(?:[.,]\d)?\b(?!\s*(?:%|CMS?\b|VECES|[.,]?\d))"
    # «TRASLAPES HASTA VARILLA 6», «LAS VARILLAS DE 8 EN ADELANTE»
    r"|\bVARILLAS?\s+(?:DE\s+)?\d{1,2}(?:[.,]\d)?\b(?!\s*(?:%|CMS?\b|VECES|[.,]?\d))"
)
# Lo demás que puede ser una varilla, pero también otra cosa (una placa de 3/8", una cuenta, un
# diámetro en milímetros): sólo con un límite cerca.
_REFERENCIA_A_VARILLA = re.compile(
    rf"{_VARILLA_MARCADA.pattern}"
    # en pulgadas: «3/4"», «1"», «5/8 PULG»
    rf"|\b\d+(?:\s+\d+)?\s*/\s*\d+\s*(?:[{_COMILLAS}]|PULG)|\b\d+\s*[{_COMILLAS}]"
    # un diámetro: «DIAMETRO 12», «DIAMETRO DE 12 MM»
    r"|\bDIAMETROS?\s+(?:DE\s+)?\d+"
    # un número pelado o una fracción sin unidad donde va una varilla
    r"|\b(?:HASTA|DESDE|A\s+PARTIR\s+DE(?:L|\s+LA)?|AL)\s+(?:(?:EL|LA)\s+)?(?:VARILLAS?\s+)?"
    rf"\d{{1,2}}(?:[.,]\d)?\b{_NO_ES_UNA_VARILLA_PELADA}"
    r"|\b(?:HASTA|DESDE|A\s+PARTIR\s+DE(?:L|\s+LA)?|AL|DEL)\s+(?:(?:EL|LA)\s+)?(?:VARILLAS?\s+)?"
    r"\d+(?:\s+\d+)?\s*/\s*\d+"
)


def _habla_de_una_varilla(ventana: str) -> bool:
    """Si cerca de la palabra clave hay una varilla: una marcada, u otra con un límite."""
    return bool(
        _VARILLA_MARCADA.search(ventana)
        or (_LIMITE.search(ventana) and _REFERENCIA_A_VARILLA.search(ventana))
    )


# Una fracción sin comillas ni «PULG»: no se sabe si son pulgadas.
_FRACCION_SIN_UNIDAD = re.compile(rf"\b\d+(?:\s+\d+)?\s*/\s*\d+\b(?!\s*(?:[{_COMILLAS}]|PULG))")
_ESTRIBOS_O_GRAPAS = re.compile(r"ESTRIBO|GRAPA")
_GANCHO_O_DOBLEZ = re.compile(r"GANCHO|DOBLEZ")
_ALGUN_NUMERO = re.compile(r"\d")
_ANGULO_EN_TEXTO = re.compile(r"(\d{2,3})\s*(?:°|º|GRADOS)")
_DOS_ANGULOS = re.compile(r"(\d{2,3})\s*(?:°|º|GRADOS)?\s*Y\s*(\d{2,3})\s*(?:°|º|GRADOS)")
_PRIMER_ESTRIBO_A = re.compile(rf"PRIMER\s+ESTRIBO\b.*?\bA\s+({_NUM})\s*CMS?\b")
_A_UNA_DISTANCIA = re.compile(rf"\bA\s+{_NUM}\s*CMS?\b")
_LONGITUD = re.compile(rf"{_NUM}\s*(?:CMS?|MTS?|MM|M)\b")
# Un anclaje con su medida que ninguna frase conocida cubre entera («VER 100CM ANCLAJE DE…», «60
# CM DE ANCLAJE EN DALA»: el que entra en una dala no es el de la dala).
_ANCLAJE_CON_MEDIDA = re.compile(
    rf"{_NUM}\s*CMS?\.?\s+(?:DE\s+)?ANCLAJE\s+(?:DE|EN)\s+[A-Z]"
    rf"|ANCLAJE\s+(?:DE|EN)\s+(?:(?:LOS|LAS|EL|LA)\s+)?[A-Z]+\s*[:=]?\s*{_NUM}\s*CMS?\b"
)
# Cuánto se mira alrededor de la palabra clave: antes y después, en letras.
_ANTES, _DESPUES = 100, 140

# --- la nota entera -----------------------------------------------------------------------------
# Lo que anula una nota entera: «N/A», «(NOTA CANCELADA)», «ANULADA», «SUPRIMIDA», «ELIMINADA»…
_ANULADA = re.compile(
    r"(?<![A-Z])N/A(?![A-Z])|\b(?:ANULAD[AO]S?|CANCELAD[AO]S?|SUPRIMID[AO]S?|ELIMINAD[AO]S?"
    r"|SIN\s+EFECTO|NO\s+APLICA)\b"
)
# Lo que extiende o recorta a qué varillas o elementos va una regla: «… Y MAYORES TAMBIEN», «ASI
# COMO LAS MENORES», «Y LAS DEMAS», «SOLO EN…».
_AMPLIA_O_RECORTA = re.compile(
    r"\b(?:MAYOR(?:ES)?|MENOR(?:ES)?|DEMAS|TAMBIEN|ASI\s+COMO|IGUALMENTE|TODAS?|TODOS|RESTO"
    r"|SOLO|SOLAMENTE|UNICAMENTE)\b"
)
# Las palabras con que una cláusula dice una regla (las del aviso de lo que no se leyó).
_PALABRA_DE_REGLA = re.compile(
    r"TRASLAP|SOLDA|GANCHO|DOBLE[ZC]|PRIMER\s+ESTRIBO|PLANTILLA|RECUBRIMIENTO|ANCLAJE"
)
# Las reglas por familia: otro elemento no las cambia (es de otra familia).
_POR_FAMILIA = ("recubrimiento", "primer_estribo", "anclaje")
_TEMA_DE_LA_REGLA = {
    "traslape": "hasta qué varilla se traslapa",
    "soldar": "desde qué varilla se suelda",
    "primer_estribo": "el primer estribo",
    "gancho_estribo": "los ganchos de estribos y grapas",
    "gancho_grapa": "los ganchos de estribos y grapas",
    "plantilla": "el espesor de la plantilla",
    "recubrimiento": "el recubrimiento",
    "anclaje": "el anclaje",
}
_TEMA_DE_LA_PALABRA = (
    (re.compile("TRASLAP"), "traslape"),
    (re.compile("SOLDA"), "soldar"),
    (re.compile(r"PRIMER\s+ESTRIBO"), "primer_estribo"),
    (re.compile("GANCHO|DOBLEZ"), "gancho_estribo"),
    (re.compile("PLANTILLA"), "plantilla"),
    (re.compile("RECUBRIMIENTO"), "recubrimiento"),
)


@dataclass
class _Lectura:
    """Una lectura de una regla: su ``Dato`` y las hojas donde el plano lo dice así."""

    dato: Dato
    hojas: list[str]


class _Lecturas:
    """Todo lo que el plano dice de cada regla, antes de decidir entre lecturas."""

    def __init__(self) -> None:
        self.por_regla: dict[str, list[_Lectura]] = defaultdict(list)
        self.leidas: set[str] = set()  # reglas que leyó el texto en curso (ver ``_vigilar``)
        self._avisos: dict[str, list[str]] = {}

    def poner(self, regla: str, dato: Dato) -> None:
        """Una lectura más. La misma lectura (mismo texto, mismo valor) no cuenta dos veces."""
        self.leidas.add(regla.split(":")[0])
        for otra in self.por_regla[regla]:
            if otra.dato.entidades == dato.entidades and repr(otra.dato.valor) == repr(dato.valor):
                return
        self.por_regla[regla].append(_Lectura(dato, dato.hojas or [dato.hoja]))

    def avisar(self, frase: str, hojas: list[str] | None = None) -> None:
        """Un aviso; el mismo de varias hojas sale una vez, diciendo cuáles."""
        self._avisos.setdefault(frase, []).extend(hojas or [])

    def avisos(self) -> list[str]:
        return [
            f"{frase} (en {donde_estan(hojas)})" if hojas else frase
            for frase, hojas in self._avisos.items()
        ]

    def unir(self, otra: "_Lecturas") -> None:
        """Las lecturas y los avisos de ``otra`` (lo que dijo un texto), aquí."""
        for regla, lecturas in otra.por_regla.items():
            for lectura in lecturas:
                self.poner(regla, lectura.dato)
        for frase, hojas in otra._avisos.items():
            self.avisar(frase, hojas)


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
) -> tuple[list[str], str]:
    """Los elementos que nombra ``texto`` (mayúsculas, sin acentos), en el orden en que aparecen,
    y el texto sin las palabras que se reconocieron."""
    encontradas: list[tuple[int, tuple[str, ...]]] = []
    restante = texto
    for patron, familias in palabras:
        for m in patron.finditer(restante):
            encontradas.append((m.start(), familias))
        restante = patron.sub(lambda m: " " * len(m.group(0)), restante)
    nombres: list[str] = []
    for _, familias in sorted(encontradas):
        nombres += [f for f in familias if f not in nombres]
    return nombres, restante


def _cita(texto: str, inicio: int, fin: int, largo: int = 200) -> str:
    """El tramo del texto que respalda una lectura, sin pasar de ``largo`` letras antes."""
    return texto[max(0, inicio, fin - largo) : fin].strip(" ,;:")


@dataclass
class _Origen:
    """De dónde sale un texto que se lee: su hoja, sus entidades, la fuente, cuántas copias y el
    encabezado bajo el que está (``seccion``)."""

    texto: str
    fuente: Fuente
    hoja: str
    hojas: list[str]
    entidades: list[str]
    copias: int
    donde: str  # cómo se nombra en un aviso: «La nota 4 de REFUERZO»
    es_nota: bool = True
    seccion: str = ""

    def dato(self, valor: Any, cita: str) -> Dato:
        return Dato(
            valor=valor,
            fuente=self.fuente,
            hoja=self.hoja,
            hojas=list(self.hojas),
            texto=cita,
            entidades=list(self.entidades),
            copias=self.copias,
        )

    @property
    def hojas_del_aviso(self) -> list[str] | None:
        """Un texto suelto dice en qué hojas está; una nota se nombra por su número."""
        return None if self.es_nota else self.hojas


# --- las frases leídas, una por una -----------------------------------------------------------

# Cada elemento de una lista de recubrimientos, con sus familias. «TRABES DE CIMENTACION» son las
# contratrabes; «LOSAS DE CIMENTACION», la losa de cimentación. Otro «X DE Y» no se reconoce.
_DE_CIMENTACION = ("zapata", "dado", "pilote", "contratrabe", "losa_cimentacion")
_MIEMBROS_DE_COBERTURA: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = tuple(
    (re.compile(patron), familias)
    for patron, familias in (
        (r"ELEMENTOS\s+(?:ESTRUCTURALES\s+)?DE\s+CIMENTACION|CIMENTACION", _DE_CIMENTACION),
        (r"LOSAS?\s+DE\s+CIMENTACION", ("losa_cimentacion",)),
        (r"(?:TRABES?|VIGAS?)\s+DE\s+CIMENTACION", ("contratrabe",)),
        (r"CONTRATRABES?(?:\s+DE\s+CIMENTACION)?", ("contratrabe",)),
        (r"ZAPATAS?(?:\s+DE\s+CIMENTACION)?", ("zapata",)),
        (r"DADOS?(?:\s+DE\s+CIMENTACION)?", ("dado",)),
        (r"PILOTES?(?:\s+DE\s+CIMENTACION)?", ("pilote",)),
        (r"TRABES?", ("trabe",)),
        (r"COLUMNAS?", ("columna",)),
        (r"LOSAS?", ("losa",)),
        (r"MUROS?\s+DE\s+(?:CONCRETO|CONTENCION)", ("muro_concreto",)),
        (r"CASTILLOS?", ("castillo",)),
        (r"CADENAS?|DALAS?", ("dala",)),
        (r"CERRAMIENTOS?", ("cerramiento",)),
    )
)
_MEDIDA = re.compile(MEDIDA)
_SEPARA_MIEMBROS = re.compile(r"\s*,\s*|\s+(?:Y|E)\s+")
_COLA_DE_LA_LISTA = re.compile(r"(?:\s*,|\s+(?:Y|E)(?:\s+TAMBIEN)?)?\s*$")


def _miembros(texto: str) -> tuple[list[str], list[str]]:
    """Las familias que nombra una lista de elementos («TRABES Y LOSAS») y los que no se
    reconocen (``ALBERCAS``)."""
    familias: list[str] = []
    desconocidos: list[str] = []
    for miembro in _SEPARA_MIEMBROS.split(texto.strip()):
        miembro = re.sub(r"^(?:LOS|LAS)\s+", "", miembro.strip())
        suyas = next((f for p, f in _MIEMBROS_DE_COBERTURA if p.fullmatch(miembro)), None)
        if suyas is None:
            desconocidos.append(miembro)
        else:
            familias += [f for f in suyas if f not in familias]
    return familias, desconocidos


def _recubrimientos(o: _Origen, lectura: Lectura, lecturas: _Lecturas) -> None:
    """Los recubrimientos de cada renglón de la lista: «N CM EN <elementos>» (un rango «3.0 A 5.0
    CM» toma el mínimo y se avisa; un elemento que no se reconoce se avisa y no se usa)."""
    for f in lectura.validas("recubrimiento", "recubrimiento_lista"):
        inicio, fin = f.lugar("items")
        lista = lectura.texto[inicio:fin]
        medidas = list(_MEDIDA.finditer(lista))
        for k, m in enumerate(medidas):
            en = re.match(EN_SUS_ELEMENTOS, lista[m.end() :])
            assert en is not None  # la frase sólo admite «N CM EN <elementos>»
            hasta = medidas[k + 1].start() if k + 1 < len(medidas) else len(lista)
            texto_miembros = _COLA_DE_LA_LISTA.sub("", lista[m.end() + en.end() : hasta])
            cita = _cita(
                o.texto, inicio + m.start(), inicio + m.end() + en.end() + len(texto_miembros)
            )
            familias, desconocidos = _miembros(texto_miembros)
            a_cm = 100.0 if m["u"].startswith("M") else 1.0
            bajo = round(_numero(m["n"]) * a_cm, 4)
            alto = round(_numero(m["m"]) * a_cm, 4) if m["m"] else None
            minimo = bajo if alto is None or bajo <= alto else alto
            if not familias:
                lecturas.avisar(
                    f"{o.donde} da un recubrimiento de {m['n']} cm «{texto_miembros.strip()}» pero "
                    "no se reconoce a qué elementos; no se usa."
                )
                continue
            if desconocidos:
                lecturas.avisar(
                    f"{o.donde} da {minimo:g} cm para {_listar(familias)} y también nombra "
                    f"«{' '.join(desconocidos)}», que no se reconoce como un elemento; no se usa "
                    "para eso."
                )
            if not _COBERTURA_CM[0] <= minimo <= _COBERTURA_CM[1]:
                lecturas.avisar(
                    f"{o.donde} da un recubrimiento de {minimo:g} cm para {_listar(familias)}, "
                    f"fuera de lo posible ({_COBERTURA_CM[0]:g}–{_COBERTURA_CM[1]:g} cm); no se "
                    "usa."
                )
                continue
            if alto is not None:
                escrito = m["n"] if minimo == bajo else m["m"]
                lecturas.avisar(
                    f"El recubrimiento de {_listar(familias)} va de {m['n']} a {m['m']} cm "
                    f"({o.donde[0].lower()}{o.donde[1:]}); se toma el mínimo ({escrito} cm)."
                )
            for familia in familias:
                lecturas.poner(f"recubrimiento:{familia}", o.dato(_metros(minimo), cita))


def _varilla(o: _Origen, f: Frase, nombre: str, cita: str, lecturas: _Lecturas) -> str | None:
    """El número de varilla del grupo ``nombre`` de la frase; si no es una varilla, un aviso."""
    con_cola = nombre == "b" and f.m.groupdict().get("cola") is not None
    v = varilla_de(f.m, nombre, con_cola=con_cola)
    if v.tipo == "num":
        escrito = v.escrito.replace(",", ".")
        numero = escrito if escrito in NUMEROS else None
        quien = f"#{v.escrito} no es un número de varilla"
    elif v.tipo == "pulg":
        numero = numero_de_varilla(v.pulgadas)
        quien = f"«{v.escrito}» no es un número de varilla"
    else:
        numero, quien = None, f"«{v.escrito}» no se sabe si son pulgadas"
    if numero is not None and v.equivalencia:
        otra = numero_de_varilla(re.sub(r"\s*PULG(?:ADAS?)?\.?", '"', v.equivalencia))
        if otra != numero:
            numero, quien = None, f"«{v.escrito}» y «{v.equivalencia}» no son la misma varilla"
    if numero is None:
        lecturas.avisar(f"{o.donde} dice «{cita}» y {quien}; no se usa.")
    return numero


def _varilla_mayor_de(f: Frase) -> bool:
    """Si el rango de soldadura de ``f`` llega a la varilla mayor («DEL No. 7 AL No. 12»): sólo
    entonces dice desde cuál se suelda en adelante."""
    v = varilla_de(f.m, "b")
    numero = numero_de_varilla(v.pulgadas) if v.tipo == "pulg" else v.escrito.replace(",", ".")
    return numero == NUMEROS[-1]


def _traslape_y_soldadura(o: _Origen, lectura: Lectura, lecturas: _Lecturas) -> None:
    for f in lectura.validas("traslape", "soldar", "soldar_rango"):
        cita = _cita(o.texto, f.inicio, f.fin)
        # Un rango («DEL 3 AL 6») dice dos varillas: las dos tienen que serlo.
        desde = _varilla(o, f, "a", cita, lecturas) if f.m.groupdict().get("a") else ""
        if desde is None:
            continue
        if f.regla == "soldar_rango":
            lecturas.poner("soldar", o.dato(desde, cita))
            continue
        # En un rango el límite del traslape es el de arriba.
        numero = _varilla(o, f, "b", cita, lecturas)
        if numero is not None:
            lecturas.poner(f.regla, o.dato(numero, cita))


def _primer_estribo(o: _Origen, lectura: Lectura, lecturas: _Lecturas) -> None:
    """El primer estribo de cada familia que la frase nombra (o, si no nombra ninguna, las del
    encabezado de la nota: «COLUMNAS :»)."""
    for f in lectura.validas("primer_estribo"):
        centimetros = _numero(f.m["n"])
        cita = _cita(o.texto, f.inicio, f.fin)
        texto_familias = " ".join(g for g in (f.m["fam"], f.m.groupdict().get("fam2")) if g)
        familias, _ = _familias_en(texto_familias, _PALABRAS_DE_ESTRIBO)
        if not familias:
            familias, _ = _familias_en(mayusculas_sin_acentos(o.seccion), _PALABRAS_DE_ESTRIBO)
        if not _PRIMER_ESTRIBO_CM[0] <= centimetros <= _PRIMER_ESTRIBO_CM[1]:
            lecturas.avisar(
                f"{o.donde} da el primer estribo a {centimetros:g} cm, fuera de lo posible "
                f"({_PRIMER_ESTRIBO_CM[0]:g}–{_PRIMER_ESTRIBO_CM[1]:g} cm); no se usa."
            )
            continue
        if not familias:
            lecturas.avisar(
                f"{o.donde} da el primer estribo a {centimetros:g} cm pero no dice en qué "
                "elementos; no se sabe a cuáles aplica y no se usa."
            )
        for familia in familias:
            lecturas.poner(f"primer_estribo:{familia}", o.dato(_metros(centimetros), cita))


def _tramo_recto(f: Frase, lectura: Lectura) -> tuple[float, int] | None:
    """Los diámetros del tramo recto del gancho ``f`` y dónde acaba lo que lo dice: el de su
    frase, o el de una frase «… TRAMO RECTO DE 10Ø» que la sigue en su oración."""
    if f.m.groupdict().get("recto"):
        return _numero(f.m["recto"]), f.lugar("tq")[1]
    for g in lectura.validas("tramo", "gancho", "gancho_par", "gancho_dos"):
        if g.oracion != f.oracion or g.desde <= f.hasta:
            continue
        if g.regla != "tramo":
            return None  # otro gancho: su tramo es suyo
        return _numero(g.m["recto"]), g.lugar("tq")[1]
    return None


def _ganchos(o: _Origen, lectura: Lectura, lecturas: _Lecturas) -> None:
    """Los ganchos de estribos y grapas: el ángulo de cada quien, con su tramo recto."""
    for f in lectura.validas("gancho", "gancho_par", "gancho_dos"):
        tramo = _tramo_recto(f, lectura)
        if tramo is None:
            lecturas.avisar(
                f"{o.donde} da el gancho pero no dice el tramo recto; se usa el de "
                f"{_GANCHO_ESTRIBO['recto_diametros']}Ø (supuesto)."
            )
            tramo = (float(_GANCHO_ESTRIBO["recto_diametros"]), f.fin)
        diametros, hasta = tramo
        recto: int | float = int(diametros) if float(diametros).is_integer() else diametros
        cita = _cita(o.texto, f.inicio, max(hasta, f.fin))
        quienes = [("q1", "a1")] if f.regla == "gancho" else [("q1", "a1"), ("q2", "a2")]
        for quien, angulo in quienes:
            regla = "gancho_estribo" if f.m[quien].startswith("ESTRIBO") else "gancho_grapa"
            valor = {"angulo": int(f.m[angulo]), "recto_diametros": recto}
            lecturas.poner(regla, o.dato(valor, cita))


def _plantilla_y_anclajes(o: _Origen, lectura: Lectura, lecturas: _Lecturas) -> None:
    """La plantilla y los anclajes que el plano declara («100CM ANCLAJE DE CASTILLO»)."""
    for f in lectura.validas("plantilla"):
        unidad = f.m["u"]
        a_cm = 0.1 if unidad == "MM" else (100.0 if unidad.startswith("M") else 1.0)
        centimetros = round(_numero(f.m["n"]) * a_cm, 4)
        cita = _cita(o.texto, f.inicio, f.fin)
        if _PLANTILLA_CM[0] <= centimetros <= _PLANTILLA_CM[1]:
            lecturas.poner("plantilla", o.dato(_metros(centimetros), cita))
        else:
            lecturas.avisar(
                f"La plantilla dice {centimetros:g} cm «{cita}», fuera de lo posible "
                f"({_PLANTILLA_CM[0]:g}–{_PLANTILLA_CM[1]:g} cm); no se usa."
            )
    for f in lectura.validas("anclaje"):
        cita = _cita(o.texto, f.inicio, f.fin)
        palabra = f.m["p"]
        familia = next(
            (fa for p, fa in _ELEMENTO_DE_ANCLAJE.items() if palabra.startswith(p)), None
        )
        centimetros = _numero(f.m["n"])
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
            lecturas.poner(f"anclaje:{familia}", o.dato(_metros(centimetros), cita))


# --- la nota entera: sus lecturas valen sólo si nada de ella las niega, las acota o se quedó sin
# leer ------------------------------------------------------------------------------------------


def _familias_que_nombra(texto: str) -> set[str]:
    """Las familias que un texto nombra (``?`` si nombra un elemento que no es de ninguna)."""
    familias = set(_familias_en(texto, _PALABRAS_DE_COBERTURA)[0])
    return familias or ({"?"} if ELEMENTO.search(texto) else set())


def _lo_que_la_cambia(o: _Origen, lectura: Lectura, reglas: set[str]) -> str | None:
    """Lo que hace que las lecturas de un texto no valgan, o ``None`` si valen todas.

    Las lecturas (``reglas``: «traslape», «recubrimiento:trabe»…) valen sólo si:
    (a) cada cláusula que nombra una regla se leyó entera (o es una frase que se sabe que no da
        una regla: la proporción por sección de Marina, «SIN TRASLAPES» junto a lo que se suelda);
    (b) ninguna niega, anula o exceptúa («NO …», «N/A», «(NOTA CANCELADA)», «SALVO …») ni amplía o
        recorta a qué varillas va («… Y MAYORES TAMBIEN», «ASI COMO LAS MENORES»);
    (c) nada la acota a un elemento («EN COLUMNAS», «PARA COLUMNAS», «NO ASI EN …», un encabezado
        como «COLUMNAS :» o «NOTAS PARA LOSAS :»). Una regla por familia (recubrimiento, primer
        estribo, anclaje) se lee sólo para las familias que dice: otro elemento en otra oración es
        de otra familia (se avisa aparte); en su misma oración, con una cifra, o nombrando una
        familia que se leyó, la cambia;
    (d) ninguna cláusula sin leer trae un número (un valor sobreentendido: «… #6. LUEGO HASTA EL
        #5»).
    Los encabezados generales («NOTAS GENERALES…», «REFUERZO», «MATERIALES»,
    «ESPECIFICACIONES…», «NOTAS DE CIMENTACION») no nombran ningún elemento: no acotan."""
    globales = any(r.split(":")[0] not in _POR_FAMILIA for r in reglas)
    leidas = {r.split(":")[1] for r in reglas if ":" in r}
    texto = lectura.texto
    anulada = _ANULADA.search(texto)
    if anulada:
        return o.texto[anulada.start() : anulada.end()]
    encabezado = _familias_que_nombra(mayusculas_sin_acentos(o.seccion))
    if encabezado and (globales or leidas - _con_sus_contratrabes(encabezado)):
        return o.seccion
    por_familia_en = {f.oracion for f in lectura.validas("primer_estribo", "recubrimiento")}
    por_familia_en |= {f.oracion for f in lectura.validas("recubrimiento_lista")}
    for k, oracion in enumerate(lectura.oraciones):
        cubiertas = {
            i for f in lectura.validas() if f.oracion == k for i in range(f.desde, f.hasta + 1)
        }
        for i, pieza in enumerate(oracion.piezas):
            trozo = texto[pieza.inicio : pieza.fin]
            if i in cubiertas or es_neutra(trozo):
                continue
            if (
                _PALABRA_DE_REGLA.search(trozo)
                or NEGACION.search(trozo)
                or EXCEPCION.search(trozo)
                or _AMPLIA_O_RECORTA.search(trozo)
            ):
                return o.texto[pieza.inicio : pieza.fin]
            nombradas = _familias_que_nombra(trozo)
            numeros = numeros_libres(trozo)
            if nombradas:
                if globales or nombradas & leidas or (numeros and k in por_familia_en):
                    return o.texto[pieza.inicio : pieza.fin]
            elif numeros:
                return o.texto[pieza.inicio : pieza.fin]
    return None


def _con_sus_contratrabes(familias: set[str]) -> set[str]:
    """«TRABES» en un encabezado incluye a las contratrabes (como en el primer estribo)."""
    return familias | ({"contratrabe"} if "trabe" in familias else set())


def _avisar_la_nota(
    o: _Origen, lectura: Lectura, reglas: set[str], por: str, lecturas: _Lecturas
) -> None:
    """Un solo aviso por una nota cuyas lecturas no valen: qué dice y qué lo impide."""
    temas = [_TEMA_DE_LA_REGLA[r.split(":")[0]] for r in sorted(reglas)]
    temas += [_TEMA_DE_LA_REGLA[r] for p, r in _TEMA_DE_LA_PALABRA if p.search(lectura.texto)]
    todo = " ".join(o.texto.split())
    cita = todo if len(todo) <= 250 else f"{todo[:249]}…"
    lo_que = " ".join(por.split()).strip(" .")
    lecturas.avisar(
        f"{o.donde} dice {_listar(list(dict.fromkeys(temas)))}, pero «{lo_que}» "
        f"lo niega, lo acota o no se pudo leer; no se usa nada de lo que dice («{cita}»).",
        o.hojas_del_aviso,
    )


# --- lo que un texto nombra con un número y no se leyó ---------------------------------------

_HASTA_QUE_VARILLA_SE_TRASLAPA = _TEMA_DE_LA_REGLA["traslape"]
_DESDE_QUE_VARILLA_SE_SUELDA = _TEMA_DE_LA_REGLA["soldar"]
_GANCHOS = _TEMA_DE_LA_REGLA["gancho_estribo"]
_PRIMER = _TEMA_DE_LA_REGLA["primer_estribo"]
_PLANTILLA = _TEMA_DE_LA_REGLA["plantilla"]
_RECUBRIMIENTO = _TEMA_DE_LA_REGLA["recubrimiento"]
# (tema, regla que lo lee, palabra clave, lo que se pide cerca de ella en lo que no se leyó)
_SOSPECHAS: tuple[tuple[str, str, re.Pattern[str], Callable[[str], bool]], ...] = (
    (_HASTA_QUE_VARILLA_SE_TRASLAPA, "traslape", re.compile("TRASLAP"), _habla_de_una_varilla),
    (
        _DESDE_QUE_VARILLA_SE_SUELDA,
        "soldar",
        re.compile("SOLDAR|SOLDADURA"),
        _habla_de_una_varilla,
    ),
    (
        _PRIMER,
        "primer_estribo",
        re.compile(r"PRIMER\s+ESTRIBO"),
        lambda ventana: bool(_ALGUN_NUMERO.search(ventana)),
    ),
    (
        _PLANTILLA,
        "plantilla",
        re.compile("PLANTILLA"),
        lambda ventana: bool(numeros_libres(ventana) or _LONGITUD.search(ventana)),
    ),
    (
        _RECUBRIMIENTO,
        "recubrimiento",
        re.compile("RECUBRIMIENTO"),
        lambda ventana: bool(numeros_libres(ventana)),
    ),
)
# Lo que queda sin leer de una regla por familia que sí se leyó en el mismo texto: el valor de
# otra familia («… EN TRABES … A 5 CM. EN COLUMNAS A 10 CM.»): se dice, no se tira.
_SOBRAS: tuple[tuple[str, str, Callable[[str], re.Match[str] | None]], ...] = (
    ("primer_estribo", _PRIMER, _A_UNA_DISTANCIA.search),
    ("recubrimiento", _RECUBRIMIENTO, lambda resto: next(iter(numeros_libres(resto)), None)),
)


def _sin_leer_cerca(
    resto: str, clave: re.Pattern[str], cerca: Callable[[str], bool]
) -> re.Match[str] | None:
    """La palabra clave que quedó sin leer con lo que se pide cerca, también sin leer."""
    for m in clave.finditer(resto):
        if cerca(resto[max(0, m.start() - _ANTES) : min(len(resto), m.end() + _DESPUES)]):
            return m
    return None


def _lo_no_leido(o: _Origen, lectura: Lectura, resto: str, posicion: int) -> str:
    """Lo que no se leyó de la oración de ``posicion`` (y de la siguiente, si está colgada: puede
    ser lo que la cambió), como está escrito, a lo más 100 letras antes de ``posicion``."""
    k = lectura.oracion_de(posicion)
    oracion = lectura.oraciones[k]
    fin = oracion.fin
    if k + 1 < len(lectura.oraciones) and lectura.oraciones[k + 1].colgada:
        fin = lectura.oraciones[k + 1].fin
    trozo = resto[oracion.inicio : fin]
    inicio = max(oracion.inicio + len(trozo) - len(trozo.lstrip()), posicion - 100)
    fin = min(oracion.inicio + len(trozo.rstrip()), posicion + 200)
    return o.texto[inicio:fin].strip(" ,;:")


def _avisar_sin_leer(o: _Origen, tema: str, regla: str, cita: str, lecturas: _Lecturas) -> None:
    """El aviso de una regla que el texto nombra y no se leyó. Un texto que no es una nota
    numerada sólo se lee para la plantilla y los anclajes: de lo demás se dice que lo nombra."""
    if not o.es_nota and regla != "plantilla":
        lecturas.avisar(
            f"{o.donde} habla de {tema} pero no es una nota numerada: no se lee como regla.",
            o.hojas,
        )
        return
    fraccion = _FRACCION_SIN_UNIDAD.search(cita) if regla in ("traslape", "soldar") else None
    nota = (
        f"; «{' '.join(fraccion.group(0).split())}» no se sabe si son pulgadas" if fraccion else ""
    )
    lecturas.avisar(
        f"{o.donde} habla de {tema} pero no se pudo leer («{cita}»){nota}; no se usa.",
        o.hojas_del_aviso,
    )


def _ganchos_sin_leer(o: _Origen, lectura: Lectura, resto: str, lecturas: _Lecturas) -> None:
    """Los ganchos que el texto dice y no se leyeron. Una oración con dos ángulos que no dice cuál
    es de estribos y cuál de grapas, o con uno solo que nombra a los dos, se dice qué pasó; si no,
    un gancho de estribos o grapas (lo dice su oración) con un ángulo sin leer en cualquier parte
    del texto da el aviso de siempre."""
    especificos = False
    for oracion in lectura.oraciones if o.es_nota else []:
        sin_leer = resto[oracion.inicio : oracion.fin]
        dicha = lectura.texto[oracion.inicio : oracion.fin]
        angulos = list(_ANGULO_EN_TEXTO.finditer(sin_leer))
        if not angulos or not _GANCHO_O_DOBLEZ.search(sin_leer):
            continue
        estribos, grapas = "ESTRIBO" in dicha, "GRAPA" in dicha
        dos = _DOS_ANGULOS.search(sin_leer)
        if dos is not None and not estribos and not grapas:
            especificos = True
            lecturas.avisar(
                f"{o.donde} da dobleces a {int(dos.group(1))}° y {int(dos.group(2))}° pero no "
                "dice cuál es de estribos y cuál de grapas; no se usa."
            )
        elif len(angulos) == 1 and estribos and grapas:
            especificos = True
            lecturas.avisar(
                f"{o.donde} da un gancho a {int(angulos[0].group(1))}° pero no dice si es de "
                "estribos o de grapas; no se usa."
            )
    if especificos or not _ANGULO_EN_TEXTO.search(resto):
        return
    for m in _GANCHO_O_DOBLEZ.finditer(resto):
        inicio, fin = lectura.oracion_extendida(lectura.oracion_de(m.start()))
        if _ESTRIBOS_O_GRAPAS.search(lectura.texto, inicio, fin):
            cita = _lo_no_leido(o, lectura, resto, m.start())
            _avisar_sin_leer(o, _GANCHOS, "gancho_estribo", cita, lecturas)
            return


def _primer_estribo_sin_familias(
    o: _Origen, lectura: Lectura, resto: str, lecturas: _Lecturas
) -> bool:
    """Una oración que da el primer estribo sin nombrar ningún elemento: se dice que no se sabe a
    cuáles aplica (aunque no se lea, no hay nada que usar). Devuelve si lo dijo."""
    if not o.es_nota:
        return False
    for oracion in lectura.oraciones:
        sin_leer = resto[oracion.inicio : oracion.fin]
        m = _PRIMER_ESTRIBO_A.search(sin_leer)
        dicha = lectura.texto[oracion.inicio : oracion.fin]
        if m is None or NEGACION.search(dicha) or _familias_en(dicha, _PALABRAS_DE_ESTRIBO)[0]:
            continue
        lecturas.avisar(
            f"{o.donde} da el primer estribo a {_numero(m.group(1)):g} cm pero no dice en qué "
            "elementos; no se sabe a cuáles aplica y no se usa."
        )
        return True
    return False


def _vigilar(o: _Origen, lectura: Lectura, lecturas: _Lecturas) -> None:
    """Una regla que el texto nombra con un número a la vista y que no se leyó se avisa: lo que
    no se sabe leer —o que una negación, una excepción o una cláusula de antes cambia— no se
    pierde en silencio. ``lectura.resto`` es el texto sin lo que se leyó. (Un texto cuyas
    lecturas no valen ya dio su aviso por la nota entera: aquí sólo llegan los que no leyeron
    nada y los que valen enteros.)

    Una nota que leyó una regla por familia y deja sin leer el valor de otra familia lo dice. Un
    texto que no es una nota numerada (un texto suelto, uno de varias líneas) no se lee como regla
    de traslape, soldadura, primer estribo, ganchos ni recubrimiento: se avisa que lo dice. (La
    plantilla y los anclajes sí se leen en cualquier texto.)"""
    # Lo que se sabe leer pero no da una regla («SE COLOCARA PLANTILLA DE CONCRETO POBRE») no tapa
    # su palabra clave: si nada la leyó, su número a la vista se avisa.
    sin_regla = ("inerte", "acompana_soldar", "acompana_traslape")
    resto = en_blanco(lectura.texto, [f for f in lectura.validas() if f.regla not in sin_regla])
    dichos: set[str] = set()
    if _primer_estribo_sin_familias(o, lectura, resto, lecturas):
        dichos.add(_PRIMER)
    for tema, regla, clave, cerca in _SOSPECHAS:
        if tema in dichos or (regla == "recubrimiento" and not o.es_nota):
            continue
        m = _sin_leer_cerca(resto, clave, cerca)
        if m is not None:
            dichos.add(tema)
            _avisar_sin_leer(o, tema, regla, _lo_no_leido(o, lectura, resto, m.start()), lecturas)
    for regla, tema, sobra in _SOBRAS:
        if regla not in lecturas.leidas or tema in dichos:
            continue
        m = sobra(resto)
        if m is not None:
            dichos.add(tema)
            cita = _lo_no_leido(o, lectura, resto, m.start())
            lecturas.avisar(
                f"{o.donde} dice {tema} y además algo que no se pudo leer («{cita}»); eso no se "
                "usa.",
                o.hojas_del_aviso,
            )
    _ganchos_sin_leer(o, lectura, resto, lecturas)
    anclaje = _ANCLAJE_CON_MEDIDA.search(resto)
    if anclaje is not None:
        cita = _lo_no_leido(o, lectura, resto, anclaje.start())
        lecturas.avisar(
            f"{o.donde} declara un anclaje con su medida que no se pudo leer («{cita}»); no se "
            "usa.",
            o.hojas_del_aviso,
        )
    if not o.es_nota and "RECUBRIMIENTO" in resto and _UN_VALOR_EN_CM.search(resto):
        lecturas.avisar(
            f"{o.donde} habla del recubrimiento pero no es una nota numerada: no se lee como "
            "regla.",
            o.hojas,
        )


def _leer_texto(o: _Origen, lecturas: _Lecturas) -> None:
    """Todo lo que un texto dice de las reglas. Lo que dice se lee aparte y sólo se usa si la nota
    entera lo deja (``_lo_que_la_cambia``); si no, la nota es un solo aviso."""
    mayus = mayusculas_sin_acentos(o.texto)
    permitidas = _FRASES_DE_NOTA if o.es_nota else _FRASES_DE_TEXTO
    if "RECUBRIMIENTO" not in mayus:  # una lista de medidas sólo es de recubrimientos en su nota
        permitidas = permitidas - {"recubrimiento_lista"}
    lectura = leer_frases(mayus, permitidas)
    # Un rango de soldadura que no llega a la varilla mayor no dice desde cuál se suelda en
    # adelante: no es una frase que se lea (y lo que dice se avisa).
    for f in lectura.validas("soldar_rango"):
        f.valida = _varilla_mayor_de(f)
    validar(lectura)
    de_la_nota = _Lecturas()
    _recubrimientos(o, lectura, de_la_nota)
    _traslape_y_soldadura(o, lectura, de_la_nota)
    _primer_estribo(o, lectura, de_la_nota)
    _ganchos(o, lectura, de_la_nota)
    _plantilla_y_anclajes(o, lectura, de_la_nota)
    reglas = set(de_la_nota.por_regla)
    por = _lo_que_la_cambia(o, lectura, reglas) if reglas else None
    if por is not None:
        _avisar_la_nota(o, lectura, reglas, por, lecturas)
        return
    _vigilar(o, lectura, de_la_nota)
    lecturas.unir(de_la_nota)


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


def _completar_con_la_estandar(dato: Dato) -> list[str]:
    """Las varillas que la tabla del plano no trae se completan con las de la estándar (también
    en las lecturas que perdieron, para que las copias iguales sigan siéndolo). Devuelve las
    varillas que se completaron en ``dato``."""
    for alternativa in dato.alternativas:
        if alternativa.fuente == "cuadro":
            _completar_con_la_estandar(alternativa)
    faltan = [n for n in NUMEROS if n not in dato.valor and n in TABLA_ESTANDAR]
    if faltan:
        for numero in faltan:
            dato.valor[numero] = TABLA_ESTANDAR[numero].model_copy()
        dato.valor = {n: dato.valor[n] for n in sorted(dato.valor, key=float)}
        dato.texto = (
            f"{dato.texto}; {_listar([f'#{n}' for n in faltan])} de la tabla estándar (supuesto)"
        )
    return faltan


def _anotar_sin_fila(dato: Dato) -> None:
    """El ``texto`` de la tabla dice de qué varillas no tiene fila ni el plano ni la estándar.
    Se dice en cada copia de la tabla, no sólo en la elegida: la tabla que resuelve una hoja
    puede ser cualquiera de ellas."""
    for alternativa in dato.alternativas:
        if alternativa.fuente == "cuadro":
            _anotar_sin_fila(alternativa)
    sin_fila = [n for n in NUMEROS if n not in dato.valor]
    if not sin_fila:
        return
    plural = len(sin_fila) > 1
    nombres = _listar([f"#{n}" for n in sin_fila])
    if dato.fuente == "cuadro":
        quien = "ni el plano ni la estándar " + ("las traen" if plural else "la trae")
    else:
        quien = "la estándar no " + ("las trae" if plural else "la trae")
    dato.texto = f"{dato.texto}; sin fila para {nombres}: {quien}"


def _tabla_completa(
    tablas: list[Tabla],
) -> tuple[Dato, set[str], list[str], list[str]]:
    """La tabla de varillas de ``Reglas``: la del plano con la estándar para cada varilla que el
    plano no trae. Devuelve la tabla, las varillas que son del plano, las contradicciones y los
    avisos. El ``texto`` de la tabla dice lo que se completó y las varillas que no tiene
    ninguna de las dos (#2 y #7: ni el plano ni la estándar las traen)."""
    dato, contradicciones, avisos = tabla_de_varillas(tablas)
    del_plano = set(dato.valor) if dato.fuente == "cuadro" else set()
    if dato.fuente == "cuadro":
        faltan = _completar_con_la_estandar(dato)
        if faltan:
            plural = len(faltan) > 1
            avisos = [
                *avisos,
                "La tabla de varillas del plano no trae "
                f"{'las varillas' if plural else 'la varilla'} "
                f"{_listar([f'#{n}' for n in faltan])}: se {'usan las' if plural else 'usa la'} "
                "de la tabla estándar (supuesto).",
            ]
    _anotar_sin_fila(dato)
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
    """Lo que no coincide: sólo las lecturas del rango que decide (una nota que quedó por debajo
    de un detalle no entra en el desacuerdo, sigue en las alternativas del dato)."""
    mejor = max(PRECEDENCIA[lectura.dato.fuente] for lectura in lecturas)
    del_rango = [lectura for lectura in lecturas if PRECEDENCIA[lectura.dato.fuente] == mejor]
    partes = [
        f"{formato(valor)} en {donde_estan(hojas)}" for valor, hojas, _ in _agrupar(del_rango)
    ]
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
    """Los textos del dibujo que no son renglones de una nota: los de texto (de una o varias
    líneas) y los de las cotas con texto escrito a mano."""
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

    La hoja de cada lectura es el marco (``frames``) que la contiene; cada ``Dato`` sabe todas
    las hojas que dicen su valor (``hojas``). El plano manda sobre el supuesto; las copias que
    dicen lo mismo se cuentan en ``Dato.copias`` y las que no, marcan ``en_conflicto`` y se
    dicen en ``contradicciones``: el ``Dato`` de cada regla es la lectura que más hojas repiten
    y ``Reglas.para(hoja)`` da la de cada hoja. Cada ``contradicción`` es el plano contra sí
    mismo: copias de la tabla que difieren, la nota que manda soldar donde la tabla da
    traslape, copias de una nota que no dicen lo mismo, lecturas de una regla que no coinciden.
    Los ``avisos`` son lo que no se pudo usar (una celda ilegible, un rango de recubrimiento, un
    número que no es varilla, una regla que un texto nombra y no se supo leer) o se completó con
    un supuesto (una varilla que la tabla del plano no trae)."""
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
        if _CLAVES_DE_REGLA.search(mayus) is None:
            continue
        hoja = hoja_de(e)
        corto = texto if len(texto) <= 70 else f"{texto[:67]}…"
        origen = _Origen(
            texto, "detalle", hoja, [hoja], [e.entity_id], 1, f"El texto «{corto}»", es_nota=False
        )
        _leer_texto(origen, lecturas)

    por_regla = lecturas.por_regla
    conflictos: list[str] = []

    def decidir(regla: str, nombre: str, formato: Callable[[Any], str]) -> Dato | None:
        dato = elegir([lectura.dato for lectura in por_regla.get(regla, [])])
        if dato is not None and dato.en_conflicto:
            conflictos.append(_frase_del_conflicto(nombre, por_regla[regla], formato))
        return dato

    def por_familia(prefijo: str, nombre: str) -> dict[str, Dato]:
        elegidos: dict[str, Dato] = {}
        for regla in sorted(r for r in por_regla if r.startswith(f"{prefijo}:")):
            familia = regla.removeprefix(f"{prefijo}:")
            dato = decidir(regla, f"{nombre} de {familia}", _metros_en_cm)
            if dato is not None:
                elegidos[familia] = dato
        return elegidos

    recubrimientos = {
        **_recubrimientos_supuestos(),
        **por_familia("recubrimiento", "el recubrimiento"),
    }

    def gancho(regla: str, supuesto: Dato, nombre: str) -> Dato:
        dato = decidir(
            regla,
            nombre,
            lambda v: f"{v['angulo']}° con tramo recto de {v['recto_diametros']:g}Ø",
        )
        return dato if dato is not None else supuesto

    return Reglas(
        tabla_varillas=tabla,
        recubrimiento_m=recubrimientos,
        gancho_estribo=gancho(
            "gancho_estribo", _gancho_supuesto(True), "el gancho de los estribos"
        ),
        gancho_grapa=gancho("gancho_grapa", _gancho_supuesto(False), "el gancho de las grapas"),
        soldar_desde_numero=decidir(
            "soldar", "la varilla desde la que se suelda", lambda v: f"#{v}"
        ),
        traslape_max_numero=decidir(
            "traslape", "la varilla hasta la que se traslapa", lambda v: f"#{v}"
        ),
        primer_estribo_m=por_familia("primer_estribo", "el primer estribo"),
        anclajes_declarados_m=por_familia("anclaje", "el anclaje"),
        plantilla_espesor_m=decidir("plantilla", "el espesor de la plantilla", _metros_en_cm),
        contradicciones=[
            *contradicciones,
            *_contradicciones_de_la_soldadura(tabla, del_plano, por_regla.get("soldar", [])),
            *de_las_notas,
            *conflictos,
        ],
        avisos=list(dict.fromkeys([*avisos, *lecturas.avisos()])),
    )


def _leer_nota(nota: Nota, lecturas: _Lecturas) -> None:
    donde = f"La nota {nota.numero} de {nota.seccion}" if nota.seccion else f"La nota {nota.numero}"
    origen = _Origen(
        nota.texto,
        "nota",
        nota.hoja,
        nota.hojas,
        nota.entidades,
        nota.copias,
        donde,
        seccion=nota.seccion,
    )
    _leer_texto(origen, lecturas)
