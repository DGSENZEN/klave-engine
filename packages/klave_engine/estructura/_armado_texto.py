"""El texto de un armado como fichas: un solo lector de lo que rodea a una pieza.

Lo que no es una pieza (un grupo de varillas, un juego de estribos, una malla) se lee aquí
en fichas enteras separadas por ``FRONTERA``: espacio o salto de línea, texto ya consumido,
junta, contexto (medidas, espesores, marcas, referencias, palabras de familia), palabra de
doble lecho, otro multiplicador, sentido, u otra cosa. El hueco después de una pieza, lo
que la precede y el residuo final se miran con esta misma lista; nadie más decide qué es
contexto."""

import re
from dataclasses import dataclass

CONSUMIDO = "\x00"  # lo que una pieza ya tomó, en la vista enmascarada del texto
FRONTERA = " |,+"  # lo que separa una ficha de otra; «|» es el salto de línea
AMBOS = r"(?:A\s*/\s*S|A\.?S\.?|AMBOS\s+SENTIDOS|AMBAS\s+DIRECCIONES)"

_FIN_DE_FICHA = rf"(?=[{re.escape(FRONTERA)}]|$)"
_UNIDAD = r"(?:\s*CMS?\.?)?"
_PALABRAS = (
    r"(?:DALAS?|CADENAS?|CASTILLOS?|COLUMNAS?|CONTRATRABES?|TRABES?|LOSAS?|MUROS?|ZAPATAS?"
    r"|DADOS?|PILOTES?|CERRAMIENTOS?|ARMEX|REFUERZO)"
)
_MARCA = r"[A-Z]{1,4}\s*-\s*\d{1,3}[A-Z]?(?:\.\d{1,2})?"  # K-1, Z-1, CTA-10, K-15A.1
# Contexto: medidas, espesores, marcas, referencias y palabras de familia.
_CONTEXTO = (
    rf"\d+(?:\.\d+)?\s*[X×]\s*\d+(?:\.\d+)?{_UNIDAD}"
    rf"|H\s*=\s*\d+(?:\.\d+)?{_UNIDAD}"
    rf"|{_MARCA}"
    r"|VER\s+(?:CORTE|DETALLE)"
    rf"|{_PALABRAS}"
)
# Dos lechos con la misma malla, cuando la malla no dice su lecho («2 PARRILLAS #4@20»); es
# la misma lectura que ``costing.steel.slab_rebar_kg_per_m2`` da a «DOBLEMENTE». Sólo el
# lector de mallas la consume; en cualquier otro lugar se avisa.
_DOBLE = (
    r"(?:DOBLE\s+PARRILLA|PARRILLA\s+DOBLE|DOBLEMENTE\s+ARMAD[AO]|AMBOS\s+LECHOS"
    r"|(?:2|DOS)\s*(?:PARRILLAS|LECHOS|CAPAS))(?:\s+DE)?"
)
# Cualquier otro multiplicador («DOBLE MALLA», «TRES CAPAS», «ARMADO DOBLE», «DOBLE»,
# «DOBLES», «TRIPLE», «DOBLE-ARMADA», «TRIPLEMENTE ARMADA», «AMBAS CARAS» o «DUPLICADA»
# solos): nunca se lee, siempre se avisa.
_MULTIPLICADOR = (
    r"(?:\d+|DOS|TRES|CUATRO|DOBLES?|TRIPLES?)\s*(?:PARRILLAS?|LECHOS?|CAPAS?|MALLAS?)"
    r"(?:\s+DEL?)?"
    r"|(?:PARRILLAS?|LECHOS?|CAPAS?|MALLAS?|ARMADOS?)\s+(?:DOBLES?|TRIPLES?)"
    r"|(?:DOBLE(?:S|MENTE)?|TRIPLE(?:S|MENTE)?)(?:[\s-]+ARMAD[AO]S?)?"
    r"|AMBAS\s+CARAS|DUPLICAD[AO]S?"
)
# Los sentidos de una malla; sólo valen pegados a ella. Sueltos, «AS» a secas no cuenta: es
# el final de una palabra partida por un salto de línea («TODAS L» / «AS ZONAS»).
_SENTIDO = (
    r"(?:(?:EN\s+)?(?:A\s*/\s*S|A\.S\.?|AMBOS\s+SENTIDOS|AMBAS\s+DIRECCIONES)"
    r"|(?:EN|SENTIDO)\s+[XY])"
)
_FICHA_RE = re.compile(
    rf"(?P<junta>[,+]|Y{_FIN_DE_FICHA})"
    rf"|(?P<contexto>{_CONTEXTO}){_FIN_DE_FICHA}"
    rf"|(?P<doble>\(?\s*{_DOBLE}\s*\)?){_FIN_DE_FICHA}"
    rf"|(?P<multiplicador>\(?\s*(?:{_MULTIPLICADOR})\s*\)?){_FIN_DE_FICHA}"
    rf"|(?P<sentido>{_SENTIDO}){_FIN_DE_FICHA}"
    rf"|(?P<otro>[^{re.escape(FRONTERA)}]+)"
)
DOBLE_RE = re.compile(rf"(?<![\w.])\(?\s*{_DOBLE}\s*\)?{_FIN_DE_FICHA}")
PASA = frozenset({"espacio", "consumido", "contexto"})  # lo que puede rodear a una pieza
ATA = frozenset({"espacio", "contexto", "junta"})  # lo que une una palabra suelta a su pieza
ESTORBA = frozenset({"doble", "multiplicador", "sentido"})  # palabras que nadie tomó
# Una línea que empieza con una junta, con «/» o con una palabra que sólo vale junto a una
# pieza sigue a la anterior.
_SIGUE_LINEA_RE = re.compile(
    rf"\|\s*(?:[/,\-+]|Y(?![A-Z0-9])"
    rf"|\(?\s*(?:{_DOBLE}|{_MULTIPLICADOR}|{_SENTIDO})\s*\)?{_FIN_DE_FICHA})"
)
_RESIDUO_RE = re.compile(r"[\d#@/]")


@dataclass(frozen=True)
class Ficha:
    """Un pedazo entero de lo que rodea a una pieza: espacio o salto de línea, texto ya
    consumido, junta, contexto, palabra de doble lecho, otro multiplicador, sentido, u otro."""

    tipo: str
    inicio: int
    fin: int


# Los guiones de Unicode («K–7», «K‑7», «K—7»): el de leer los escribe «-» (R68.7).
_A_GUION = str.maketrans({g: "-" for g in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"})


# El número de una varilla escrito con palabras (R87): «No. 3», «N° 3», «NO.3», «NUM. 3» es
# «#3», nunca la cuenta de unos estribos.
_NUMERO_CON_PALABRA = re.compile(
    r"(?<![A-Z])(?:N[°º]\.?|NO\.|N[UÚ]M\.?)\s*(\d{1,2}(?:\.5)?)(?![\d/])"
)
# Una varilla en pulgadas, sólo en octavos exactos y donde va el número de la varilla: tras una
# cuenta y la palabra de la varilla («4 VARS 3/8"») o tras la cabeza de unos estribos («E 1/4 @
# 15»). Otra medida no se traduce: el parser la avisa.
_PULGADAS = {"1/4": "2", "3/8": "3", "1/2": "4", "5/8": "5", "3/4": "6", "7/8": "7", "1": "8"}
_EN_PULGADAS = re.compile(
    r"((?<![\w.#@])\d{1,2}\s*(?:VARILLAS|VARS?\.?|V)\s*(?:DEL?\s+)?"
    r"|(?<![A-Z0-9])(?:\d{1,2}\s*)?(?:EYG|E|G|EST\.?|ESTRIBOS?|GRAPAS?)\s*)"
    r"(?:(1/4|3/8|1/2|5/8|3/4|7/8)(?:\s*(?:\"|''|PULG\.?))?|(1)\s*(?:\"|''|PULG\.?))(?![\d/])"
)


def _con_el_mismo_largo(m: re.Match[str], escrito: str) -> str:
    """``escrito`` («#3») en el lugar de lo que encontró ``m``, rellenado con espacios: el texto
    para leer y el de citar tienen que medir lo mismo."""
    return escrito + " " * (len(m.group(0)) - len(escrito))


def traducciones(texto: str) -> list[tuple[int, int]]:
    """Dónde ``normalizar`` escribió un número de varilla en lugar de lo que dice el plano («No.
    3», «3/8"»), en las posiciones del texto normalizado: lo que se cite de ahí se cita entero,
    como lo escribió el plano (R92)."""
    t = texto.upper().replace("%%%", "%").replace("%%C", "Ø").replace("⌀", "Ø")
    t = re.sub(r"\s+", " ", t.replace("\\P", " | ")).strip()
    leer = t.replace("Ø", "#").translate(_A_GUION)
    tramos = [m.span() for m in _NUMERO_CON_PALABRA.finditer(leer)]
    leer = _NUMERO_CON_PALABRA.sub(lambda m: _con_el_mismo_largo(m, f"#{m.group(1)}"), leer)
    tramos += [(m.start() + len(m.group(1)), m.end()) for m in _EN_PULGADAS.finditer(leer)]
    return sorted(tramos)


def normalizar(texto: str) -> tuple[str, str]:
    """El texto para leer y el texto para citar, de la misma longitud: los dos en mayúsculas
    y con los espacios juntos; el de leer escribe ``#`` donde el plano puso «Ø» o «%%C», «-»
    donde puso un guion de Unicode y el número de la varilla donde lo escribió con palabras
    («No. 3» → «#3») o en octavos de pulgada («3/8"» → «#3», R87); el de citar deja lo que dice
    el plano."""
    t = texto.upper().replace("%%%", "%").replace("%%C", "Ø").replace("⌀", "Ø")
    t = re.sub(r"\s+", " ", t.replace("\\P", " | ")).strip()
    leer = t.replace("Ø", "#").translate(_A_GUION)
    leer = _NUMERO_CON_PALABRA.sub(lambda m: _con_el_mismo_largo(m, f"#{m.group(1)}"), leer)

    def pulgadas(m: re.Match[str]) -> str:
        numero = _PULGADAS[m.group(2) or m.group(3)]
        varilla = m.group(0)[len(m.group(1)) :]
        return m.group(1) + f"#{numero}" + " " * (len(varilla) - len(numero) - 1)

    leer = _EN_PULGADAS.sub(pulgadas, leer)
    return leer, t


def fichas(texto: str, a: int, b: int, consumido: list[bool] | None = None) -> list[Ficha]:
    """Las fichas entre ``a`` y ``b``, en su lugar real del texto. Cada ficha termina en una
    frontera; un contexto que no termina en frontera no es contexto sino «otro»."""
    lista: list[Ficha] = []
    pos = a
    while pos < b:
        if consumido is not None and consumido[pos]:
            fin = pos
            while fin < b and consumido[fin]:
                fin += 1
            lista.append(Ficha("consumido", pos, fin))
        elif texto[pos] in " |":
            fin = pos + 1
            lista.append(Ficha("espacio", pos, fin))
        else:
            m = _FICHA_RE.match(texto, pos, b)
            assert m is not None and m.lastgroup is not None
            fin = m.end()
            lista.append(Ficha(m.lastgroup, pos, fin))
        pos = fin
    return lista


def atado(texto: str, a: int, b: int) -> bool:
    """Entre ``a`` y ``b`` sólo hay espacios, saltos de línea, contexto o una junta: lo que
    une una palabra suelta (de doble lecho, de sentido) a la pieza que le sigue o precede."""
    return a <= b and all(f.tipo in ATA for f in fichas(texto, a, b))


def _fin_de_linea(texto: str, desde: int) -> int:
    fin = texto.find("|", desde)
    return len(texto) if fin < 0 else fin


def fin_del_hueco(texto: str, desde: int, inicio_siguiente: int | None) -> int:
    """Hasta dónde llega lo que sigue a una pieza: la pieza siguiente o el fin de la línea
    (una línea que empieza con junta, «/» o una palabra suelta sigue a la anterior)."""
    tope = len(texto) if inicio_siguiente is None else inicio_siguiente
    fin = _fin_de_linea(texto, desde)
    while fin < tope and _SIGUE_LINEA_RE.match(texto, fin):
        fin = _fin_de_linea(texto, fin + 1)
    return min(tope, fin)


def hueco_limpio(
    texto: str, a: int, b: int, inicio_siguiente: int | None, consumido: list[bool]
) -> bool:
    """Lo que hay entre el fin de una pieza (``a``) y ``b`` es sólo contexto, y a lo más una
    junta justo antes de la pieza siguiente. Lo que va pegado a la pieza (sin espacio ni
    junta) nunca es limpio, salvo un punto que cierra la línea («A/S.», «@20.»)."""
    if a == b:
        return True
    if texto[a] not in FRONTERA:
        if texto[a] != "." or texto[a + 1 : b].strip(" |") != "":
            return False
        a += 1
    for f in fichas(texto, a, b, consumido):
        if f.tipo in PASA:
            continue
        if f.tipo == "junta":
            return inicio_siguiente is not None and (
                texto[f.fin : inicio_siguiente].strip(" |") == ""
            )
        return False
    return True


def residuo(texto: str, cubierto: list[bool]) -> list[tuple[int, int, str]]:
    """Lo que nadie leyó y no es contexto, como tramos (inicio, fin, tipo): una palabra de
    doble lecho u otro ``multiplicador``, un ``sentido`` que ninguna pieza tomó, y cada
    pedazo («otro») con una cifra, «#», «@» o «/». Un «#» o «@» suelto se lleva el número
    que le sigue («@ 20»), un pedazo que le sigue y empieza con «@» se le junta («4#5 @ 20»),
    unos milímetros detrás también («#12 MM»), y lo pegado por una junta sin espacio es un
    solo pedazo («1@6,8@10,10@15»)."""
    tramos: list[tuple[int, int, str]] = []
    sueltos: list[tuple[int, int]] = []
    i, n = 0, len(texto)
    while i < n:
        if cubierto[i]:
            i += 1
            continue
        j = i
        while j < n and not cubierto[j]:
            j += 1
        for f in fichas(texto, i, j):
            if f.tipo == "otro":
                sueltos.append((f.inicio, f.fin))
            elif f.tipo == "doble":
                tramos.append((f.inicio, f.fin, "multiplicador"))
            elif f.tipo in ("multiplicador", "sentido"):
                tramos.append((f.inicio, f.fin, f.tipo))
        i = j

    k = 0
    while k < len(sueltos):
        a, b = sueltos[k]
        if not _RESIDUO_RE.search(texto[a:b]):
            k += 1
            continue
        while k + 1 < len(sueltos):
            a2, b2 = sueltos[k + 1]
            siguiente, entre = texto[a2:b2], texto[b:a2]
            pegados = entre != "" and entre.strip(",+") == ""
            contiguo = entre.strip(" ") == ""
            se_junta = (
                (texto[b - 1] in "#@" and siguiente[0].isdigit())
                or siguiente[0] == "@"
                or siguiente in ("MM", "MMS")
            )
            if not (pegados or (contiguo and se_junta)):
                break
            b = b2
            k += 1
        tramos.append((a, b, "otro"))
        k += 1
    return tramos
