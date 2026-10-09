"""El armado de un elemento como estructura, no como texto, y el parser que no pierde nada.

Un texto de armado («4#5+2#4», «2E+1G#3EXT@10» / «CENTRO@15», «LS #4@20 A/S») se lee en
grupos de varillas longitudinales, juegos de estribos con sus zonas y parrillas. La regla
es que nada se pierde en silencio: cada ``#`` y cada ``@`` del texto termina dentro de la
estructura o en ``avisos`` con el pedazo que no se pudo leer. Una malla sólo se toma en
las familias que llevan parrilla; en un castillo, una columna o una trabe un ``#n@s``
suelto se avisa, nunca se convierte en malla.

Los textos canónicos (``texto_longitudinal``, ``texto_estribos``, ``texto_parrillas``,
``texto_armado``) vuelven a dar la misma estructura al leerse otra vez."""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

# Las llaves de ``costing.steel.BAR_KG_PER_M``, en su orden. Se escriben aquí y no se
# importan porque ``costing.steel`` leerá el armado con este módulo (un ciclo de
# importación); una prueba garantiza que las dos listas no se separen.
NUMEROS: tuple[str, ...] = ("2", "2.5", "3", "4", "5", "6", "7", "8", "10", "12")

FAMILIAS_CON_PARRILLA = frozenset(
    {"losa", "muro", "muro_concreto", "zapata", "dado", "losa_cimentacion"}
)

Forma = Literal["perimetral", "rombo", "interior", "grapa", "liga"]


class GrupoVarillas(BaseModel):
    """«4#5»: cuántas varillas y de qué número."""

    cantidad: int
    numero: str
    posicion: Literal["esquina", "cara", "lecho_sup", "lecho_inf", "ambos"] | None = None


class Zona(BaseModel):
    """Un tramo del elemento con su separación de estribos («EXT@10», «CENTRO@20», «@15»)."""

    tramo: Literal["todo", "extremos", "centro"]
    separacion_m: float | None
    longitud_m: float | None = None


class JuegoEstribos(BaseModel):
    """«2E#3»: ``cantidad`` es la n de «nE» (piezas por juego); las ``formas`` se asignan
    después, una por pieza, con su fuente en ``formas_fuente``."""

    tipo: Literal["estribo", "grapa", "liga"]
    cantidad: int
    numero: str
    zonas: list[Zona] = []
    referencia: str | None = None  # «VER CORTE»: el armado se remite a otro dibujo
    formas: list[Forma] = []
    formas_fuente: str | None = None


class Parrilla(BaseModel):
    """«LS #4@20 A/S»: número, separación, lecho y sentidos (``None`` si el texto no lo dice)."""

    numero: str
    separacion_m: float
    lecho: Literal["sup", "inf", "unico"]
    sentidos: Literal["ambos", "x", "y"] | None


class Armado(BaseModel):
    longitudinales: list[GrupoVarillas] = []
    estribos: list[JuegoEstribos] = []
    parrillas: list[Parrilla] = []
    texto_original: str = ""
    avisos: list[str] = []

    def vacio(self) -> bool:
        """Verdadero si el texto no dio ni varillas, ni estribos, ni parrillas (los avisos
        no cuentan: un texto ilegible sigue siendo un armado vacío)."""
        return not (self.longitudinales or self.estribos or self.parrillas)


# ------------------------------------------------------------------ gramática
# Las expresiones sólo reconocen piezas, y un número es siempre una ficha entera («#32» no
# es «#3», «@1520» no es «@152»). Si lo que rodea a una pieza la deja a medias lo decide
# ``_revisar`` sobre el texto real; lo que nadie leyó lo revisa ``_residuo``.

_NUM = (
    "(?:" + "|".join(re.escape(n) for n in sorted(NUMEROS, key=len, reverse=True)) + r")(?!\d|\.\d)"
)
_SEP = r"[1-9]\d{0,2}(?:\.\d{1,2})?(?!\d|\.\d)"  # cm, de 1 a 999.99
_CM = r"(?:\s?CMS?\.?)?(?:\s?C\s*/\s*C)?"  # la unidad y «C/C», pegadas a la separación
# Opcionalmente a través del salto de línea: «2E#3EXT@10» / «CENTRO@20» son un solo juego.
_LINEA = r"(?:\s*\|)?\s*"
_LS = r"(?:LS|L\.S\.?|LECHO\s+SUP\w*\.?)"
_LI = r"(?:LI|L\.I\.?|LECHO\s+INF\w*\.?)"
_AMBOS = r"(?:A\s*/\s*S|A\.?S\.?|AMBOS\s+SENTIDOS|AMBAS\s+DIRECCIONES)"
_CUENTA = r"[1-9]\d?"  # piezas o varillas: de 1 a 99
_CUENTA_P = rf"(?:\(\s*{_CUENTA}\s*\)|{_CUENTA})"  # «2E» o «(2)E»
_JUNTA = r"\s*(?:Y|\+|/|-|,|&)\s*"  # «EYG», «2E+1G», «E/G», «2E-1G», «2E,1G», «2E & 1G»
_E = r"E(?:ST(?:RIBOS?|\.)?|\.)?"
_G = r"G(?:RAPAS?|\.)?"

# La cantidad de un juego no puede ser el número de la varilla anterior («4#3 E#2@15»), una
# separación («@20E#3») ni parte de una medida («15X30 E#2@20»): no la precede una letra, un
# dígito, «#», «@» o «.».
# «nE+mG» y «nG+mE» son el mismo juego de estribos y grapas.
_ESTRIBOS_RE = re.compile(
    r"(?<![A-Z0-9#.@])(?<![#@]\s)"
    rf"(?:(?P<n1>{_CUENTA_P})\s*)?"
    r"(?:"
    rf"(?P<e>{_E})(?:{_JUNTA}(?:(?P<n2>{_CUENTA_P})\s*)?(?P<eg>{_G}))?"
    rf"|(?P<g>{_G})(?:{_JUNTA}(?:(?P<n3>{_CUENTA_P})\s*)?(?P<ge>{_E}))?"
    r"|(?P<l>LIGAS?)"
    r")"
    r"(?:\s+DEL?)?"
    rf"\s*#\s*(?P<num>{_NUM})"
    r"(?:"
    rf"{_LINEA}EXT(?:REMOS?)?\.?\s*@\s*(?P<ext>{_SEP}){_CM}"
    rf"(?:{_LINEA}(?:Y\s+)?CENTRO\s*@\s*(?P<centro>{_SEP}){_CM})?"
    rf"|{_LINEA}@\s*(?P<sep>{_SEP}){_CM}"
    r")?"
    rf"(?:{_LINEA}(?P<ref>VER\s+(?:CORTE|DETALLE)))?"
)

# El cuerpo de una malla; su lecho («LS», «L.I.», «LECHO SUPERIOR») va aparte, delante o detrás.
_MALLA_RE = re.compile(
    rf"#\s*(?P<num>{_NUM})\s*@\s*(?P<sep>{_SEP}){_CM}"
    rf"(?:\s+(?:EN\s+)?(?P<ambos>{_AMBOS})(?![A-Z0-9])"
    r"|\s+(?:EN|SENTIDO)\s+(?P<xy>[XY])(?![A-Z0-9]))?"
)
_LECHO_RE = re.compile(
    rf"(?<![A-Z.])(?:EN\s+)?(?P<l1>{_LS}|{_LI})"
    rf"(?:\s*(?:Y|E|,|\+)\s*(?P<l2>{_LS}|{_LI}))?(?![A-Z.])"
    rf"(?:\s*(?P<ambos>{_AMBOS})(?![A-Z0-9]))?"
)
_ES_LS = re.compile(_LS)
_SENTIDO_XY: dict[str, Literal["x", "y"]] = {"X": "x", "Y": "y"}
# Dos lechos con la misma malla, cuando la malla no dice su lecho («2 PARRILLAS #4@20»);
# es la misma lectura que ``costing.steel.slab_rebar_kg_per_m2`` da a «DOBLEMENTE».
_DOBLE = (
    r"(?:DOBLE\s+PARRILLA|DOBLEMENTE\s+ARMAD[AO]|AMBOS\s+LECHOS"
    r"|2\s*(?:PARRILLAS|LECHOS|CAPAS(?:\s+DE)?))"
)
_DOBLE_RE = re.compile(rf"(?<![\w.]){_DOBLE}(?![A-Z])")
_DOBLE_AL_FINAL_RE = re.compile(rf"(?<![\w.]){_DOBLE}\s*$")

_VARILLAS_RE = re.compile(
    rf"(?<![\d.#@])(?P<n>{_CUENTA})\s*(?:VARILLAS|VARS?\.?|V)?\s*#\s*(?P<num>{_NUM})(?!\s*@)"
)
_CIFRA_O_GATO = "0123456789#.@"  # lo que, pegado delante, parte un número (aunque esté leído)

# El contexto que puede ir junto a una pieza sin dejarla a medias: medidas, espesores,
# marcas, sentidos, referencias y palabras de familia. Siempre se busca en su lugar real.
_PALABRAS = (
    r"(?:DALAS?|CADENAS?|CASTILLOS?|COLUMNAS?|CONTRATRABES?|TRABES?|LOSAS?|MUROS?|ZAPATAS?"
    r"|DADOS?|PILOTES?|CERRAMIENTOS?|ARMEX|REFUERZO)"
)
_MARCA = r"[A-Z]{1,4}\s*-\s*\d{1,3}[A-Z]?(?:\.\d{1,2})?"  # K-1, Z-1, CTA-10, K-15A.1
_CONTEXTO_RE = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)?\s*[X×]\s*\d+(?:\.\d+)?(?![\w.])"
    r"|(?<![\w.])H\s*=\s*\d+(?:\.\d+)?(?![\w.])"
    rf"|(?<![\w.\-]){_MARCA}(?![\w.])"
    rf"|(?<![A-Z]){_AMBOS}(?![A-Z0-9])"
    r"|(?<![A-Z])EN\s+[XY](?![A-Z0-9])"
    r"|(?<![A-Z])VER\s+(?:CORTE|DETALLE)(?![A-Z])"
    rf"|(?<![A-Z]){_PALABRAS}(?![A-Z])"
)
# Una junta une la pieza con la que sigue justo después; nunca queda suelta.
_JUNTA_RE = re.compile(r"[,+]|Y(?![A-Z0-9])")
_FRONTERA = " |,+"
# Una línea que empieza con una junta o con «/» sigue a la anterior.
_SIGUE_LINEA_RE = re.compile(r"\|\s*(?:[/,\-+]|Y(?![A-Z0-9]))")
_PEGADO_RE = re.compile(r"[^ ]*$")
# Una cuenta suelta delante de una pieza la deja a medias: «4 », «4 VARS », «4 VARILLAS DE »,
# «4 PZAS », «(4) », «4-», «4VARS », «4 DE », «4 X », «3 PARRILLAS ». No es cuenta el número
# de una marca («K-1 ») ni el final de una medida («15 X 30 », «H=20 »).
_CUENTA_ANTES_RE = re.compile(
    r"(?<![\w.=\-×#@])(?<![=X×]\s)(?:\(\s*\d+\s*\)|\d+)"
    r"\s*(?:-|[X×](?![A-Z0-9])|(?:VARILLAS?|VARS?\.?|V|PZAS?\.?|PIEZAS?|PARRILLAS?|LECHOS?"
    r"|CAPAS?|MALLAS?|DEL?)(?:\s+DEL?)?)?\s*$"
)
_MULTIPLICADOR_ANTES_RE = re.compile(
    r"(?<![\w.])(?:DOBLES?|TRIPLES?|DOS|TRES|CUATRO)\s+(?:PARRILLAS?|MALLAS?|LECHOS?|CAPAS?)"
    r"(?:\s+DEL?)?\s*$"
)
# Una cabeza de estribo que no se leyó delante de una malla («ESTRIBOS: #3@20»).
_CABEZA_ANTES_RE = re.compile(
    r"(?<![\w.])\d*(?:E|EST|ESTR|ESTRIBOS?|G|GRAPAS?|LIGAS?|EYG)[.:,]?(?:\s+DEL?)?\s*$"
)
_NUMERO_EN_CITA_RE = re.compile(r"[#Ø]\s*(\d+(?:\.\d+)?)")
_RESIDUO_RE = re.compile(r"[\d#@/]")
_ANTES_DE_FICHA = " |,+("  # el contexto del residuo es una ficha entera: nunca medio número
_DESPUES_DE_FICHA = " |,+)"
# Justo antes de una malla, una palabra de lecho que no se reconoció como marca («A/SLI»)
# o un plural sin cuenta («… LECHOS», «… PARRILLAS»): la malla no se sabe cuántas son.
_LECHO_SUELTO_ANTES_RE = re.compile(
    r"(?:L\.?[SI]\.?|LECHO\s+(?:SUP|INF)\w*\.?|(?:[^\s|]+\s+)?(?:PARRILLAS|LECHOS|CAPAS|MALLAS))"
    r"(?:\s+DEL?)?\s*$"
)
_FEMENINAS = frozenset(
    {"columna", "trabe", "contratrabe", "dala", "cadena", "losa", "zapata", "pila", "viga"}
)
_CONSUMIDO = "\x00"


# ------------------------------------------------------------------ lectura


@dataclass
class _Pieza:
    """Un pedazo del texto que una de las tres pasadas reconoció. Se toma (su estructura entra
    al armado o su ``aviso`` se emite) sólo si lo que la rodea es contexto."""

    inicio: int
    fin: int
    malla: bool = False
    estribos: list[JuegoEstribos] = field(default_factory=list)
    parrillas: list[Parrilla] = field(default_factory=list)
    varillas: list[GrupoVarillas] = field(default_factory=list)
    aviso: str | None = None  # reconocida pero no se toma: malla fuera de lugar, lecho ambiguo


def _normalizar(texto: str) -> tuple[str, str]:
    """El texto para leer y el texto para citar, de la misma longitud: los dos en mayúsculas
    y con los espacios juntos; el de leer escribe ``#`` donde el plano puso «Ø» o «%%C», el
    de citar deja «Ø» para que el aviso diga lo que dice el plano."""
    t = texto.upper().replace("%%%", "%").replace("%%C", "Ø").replace("⌀", "Ø")
    t = re.sub(r"\s+", " ", t.replace("\\P", " | ")).strip()
    return t.replace("Ø", "#"), t


def _metros(cm: str) -> float:
    return float(cm) / 100


def _cuantos(cuenta: str | None) -> int:
    return int(re.sub(r"\D", "", cuenta)) if cuenta else 1


def _zonas(m: re.Match[str]) -> list[Zona]:
    if m["ext"]:
        zonas = [Zona(tramo="extremos", separacion_m=_metros(m["ext"]))]
        if m["centro"]:
            zonas.append(Zona(tramo="centro", separacion_m=_metros(m["centro"])))
        return zonas
    if m["sep"]:
        return [Zona(tramo="todo", separacion_m=_metros(m["sep"]))]
    return []


def _juegos(m: re.Match[str]) -> list[JuegoEstribos]:
    """Los juegos de una cabeza leída; un juego mixto queda siempre estribo y luego grapa."""
    numero = m["num"]
    referencia = " ".join(m["ref"].split()) if m["ref"] else None

    def juego(tipo: Literal["estribo", "grapa", "liga"], cuenta: str | None) -> JuegoEstribos:
        return JuegoEstribos(
            tipo=tipo,
            cantidad=_cuantos(cuenta),
            numero=numero,
            zonas=_zonas(m),
            referencia=referencia,
        )

    if m["e"]:
        return [juego("estribo", m["n1"])] + ([juego("grapa", m["n2"])] if m["eg"] else [])
    if m["g"]:
        return ([juego("estribo", m["n3"])] if m["ge"] else []) + [juego("grapa", m["n1"])]
    return [juego("liga", m["n1"])]


def _con_articulo(familia: str) -> str:
    return f"{'una' if familia in _FEMENINAS else 'un'} {familia.replace('_', ' ')}"


def _lechos(marca: re.Match[str] | None) -> list[Literal["sup", "inf", "unico"]]:
    """Los lechos que dice una marca («L.S. Y L.I.» son dos); sin marca, único."""
    if marca is None:
        return ["unico"]
    return [
        "sup" if _ES_LS.fullmatch(lecho) else "inf" for lecho in (marca["l1"], marca["l2"]) if lecho
    ]


def _unir(tramos: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Junta los tramos que se enciman."""
    unidos: list[tuple[int, int]] = []
    for a, b in sorted(tramos):
        if unidos and a < unidos[-1][1]:
            unidos[-1] = (unidos[-1][0], max(unidos[-1][1], b))
        else:
            unidos.append((a, b))
    return unidos


def _convencion(
    delante: list[int | None], detras: list[int | None], n_marcas: int
) -> list[int | None] | None:
    """Qué marca de lecho toma cada malla, o ``None`` si el texto no lo deja claro.

    Una marca pegada delante de una malla y no detrás de otra dice «lecho delante»; pegada
    detrás de una y no delante de otra, «lecho detrás». Si el texto da las dos señales, o
    ninguna, es ambiguo; también si una malla se queda sin lecho junto a otras que sí lo
    llevan, o si sobra una marca."""
    pegadas_delante = {k for k in delante if k is not None}
    pegadas_detras = {k for k in detras if k is not None}
    solo_delante = pegadas_delante - pegadas_detras
    solo_detras = pegadas_detras - pegadas_delante
    if solo_delante and not solo_detras:
        usadas = delante
    elif solo_detras and not solo_delante:
        usadas = detras
    else:
        return None
    if None in usadas or set(usadas) != set(range(n_marcas)):
        return None
    return usadas


def _leer_mallas(vista: str, texto: str, letrero: str, familia: str) -> list[_Pieza]:
    """Las mallas del texto con su lecho, como piezas.

    El lecho se escribe delante («LS #4@20 A/S LI #4@20 A/S») o detrás («#4@20 L.S. #3@20
    L.I.»), con una sola convención por texto. Sin marcas, una malla única precedida por
    «DOBLE PARRILLA», «DOBLEMENTE ARMADA», «AMBOS LECHOS», «2 PARRILLAS», «2 LECHOS» o
    «2 CAPAS» son dos lechos. Si no queda claro qué lecho va con qué malla ninguna malla se
    toma: cada una (con las marcas que tiene al lado) se avisa como lecho ambiguo, y una
    marca suelta como lecho sin su malla."""
    mallas = [
        m
        for m in _MALLA_RE.finditer(vista)
        if m.start() == 0 or texto[m.start() - 1] not in _CIFRA_O_GATO
    ]
    if not mallas:
        return []
    marcas = list(_LECHO_RE.finditer(vista))
    dobles = [d for d in _DOBLE_RE.finditer(vista) if d.end() <= mallas[-1].start()]

    def junto(a: int, b: int) -> bool:  # sólo espacios entre a y b, en la misma línea
        return a <= b and vista[a:b].strip(" ") == ""

    def marca_delante(malla: re.Match[str]) -> int | None:
        return next((k for k, m in enumerate(marcas) if junto(m.end(), malla.start())), None)

    def marca_detras(malla: re.Match[str]) -> int | None:
        return next((k for k, m in enumerate(marcas) if junto(malla.end(), m.start())), None)

    delante = [marca_delante(m) for m in mallas]
    detras = [marca_detras(m) for m in mallas]
    # (inicio, fin, lechos, «A/S» de la marca) de cada malla, o None si es ambiguo.
    tomas: list[tuple[int, int, list[Literal["sup", "inf", "unico"]], bool]] | None
    if marcas:
        usadas = _convencion(delante, detras, len(marcas))
        tomas = None
        if usadas is not None:
            tomas = []
            for malla, k in zip(mallas, usadas, strict=True):
                assert k is not None
                marca = marcas[k]
                inicio, fin = min(malla.start(), marca.start()), max(malla.end(), marca.end())
                tomas.append((inicio, fin, _lechos(marca), bool(marca["ambos"])))
    elif dobles and (
        len(mallas) > 1 or not _solo_contexto(texto, dobles[-1].end(), mallas[0].start())
    ):
        tomas = None  # la palabra de doble no se sabe a qué malla va
    elif dobles:
        doble, malla = dobles[-1], mallas[0]
        inicio = doble.start() if junto(doble.end(), malla.start()) else malla.start()
        tomas = [(inicio, malla.end(), ["sup", "inf"], False)]
    else:
        tomas = [(m.start(), m.end(), ["unico"], False) for m in mallas]

    if tomas is None:
        tramos = []
        for malla, antes, despues in zip(mallas, delante, detras, strict=True):
            a, b = malla.start(), malla.end()
            for k in (antes, despues):
                if k is not None:
                    a, b = min(a, marcas[k].start()), max(b, marcas[k].end())
            tramos.append((a, b))
        piezas = [
            _Pieza(a, b, malla=True, aviso=f"lecho ambiguo: «{letrero[a:b].strip()}»: no se toma")
            for a, b in _unir(tramos)
        ]
        al_lado = {k for k in delante + detras if k is not None}
        for k, suelta in enumerate(marcas):
            if k not in al_lado:
                a, b = suelta.start(), suelta.end()
                aviso = f"lecho «{letrero[a:b].strip()}» sin su malla: no se toma"
                piezas.append(_Pieza(a, b, malla=True, aviso=aviso))
        return piezas

    piezas = []
    for malla, (a, b, lechos, ambos_de_la_marca) in zip(mallas, tomas, strict=True):
        if familia not in FAMILIAS_CON_PARRILLA:
            aviso = f"malla «{letrero[a:b].strip()}» en {_con_articulo(familia)}: no se toma"
            piezas.append(_Pieza(a, b, malla=True, aviso=aviso))
            continue
        sentidos: Literal["ambos", "x", "y"] | None = (
            "ambos" if malla["ambos"] or ambos_de_la_marca else _SENTIDO_XY.get(malla["xy"] or "")
        )
        parrillas = [
            Parrilla(
                numero=malla["num"],
                separacion_m=_metros(malla["sep"]),
                lecho=lecho,
                sentidos=sentidos,
            )
            for lecho in lechos
        ]
        piezas.append(_Pieza(a, b, malla=True, parrillas=parrillas))
    return piezas


def _solo_contexto(texto: str, a: int, b: int) -> bool:
    """Entre ``a`` y ``b`` sólo hay espacios y contexto (fichas enteras, en su lugar real)."""
    pos = a
    while pos < b:
        if texto[pos] == " ":
            pos += 1
            continue
        contexto = _CONTEXTO_RE.match(texto, pos)
        if contexto is None or contexto.end() > b:
            return False
        if contexto.end() < len(texto) and texto[contexto.end()] not in _FRONTERA:
            return False
        pos = contexto.end()
    return True


def _fin_de_linea(texto: str, desde: int) -> int:
    fin = texto.find("|", desde)
    return len(texto) if fin < 0 else fin


def _fin_del_hueco(texto: str, desde: int, siguiente: _Pieza | None) -> int:
    """Hasta dónde llega lo que sigue a una pieza: la pieza siguiente o el fin de la línea
    (una línea que empieza con junta o «/» sigue a la anterior)."""
    inicio_siguiente = siguiente.inicio if siguiente else len(texto)
    fin = _fin_de_linea(texto, desde)
    while fin < inicio_siguiente and _SIGUE_LINEA_RE.match(texto, fin):
        fin = _fin_de_linea(texto, fin + 1)
    return min(inicio_siguiente, fin)


def _junta_justa(texto: str, fin_junta: int, siguiente: _Pieza | None) -> bool:
    """Una junta vale si lo único entre ella y la pieza siguiente es espacio o salto de línea."""
    return siguiente is not None and texto[fin_junta : siguiente.inicio].strip(" |") == ""


def _hueco_limpio(texto: str, a: int, b: int, siguiente: _Pieza | None) -> bool:
    """Lo que hay entre el fin de una pieza (``a``) y ``b`` es sólo contexto, buscado en su
    lugar real del texto, y a lo más una junta justo antes de la pieza siguiente. Lo que va
    pegado a la pieza (sin espacio ni junta) nunca es limpio."""
    if a == b:
        return True
    if texto[a] not in _FRONTERA:
        return False
    pos = a
    while pos < b:
        if texto[pos] in " |":
            pos += 1
            continue
        junta = _JUNTA_RE.match(texto, pos)
        if junta is not None and junta.end() <= b:
            return _junta_justa(texto, junta.end(), siguiente)
        contexto = _CONTEXTO_RE.match(texto, pos)
        if contexto is None or contexto.end() > b:
            return False
        if contexto.end() < len(texto) and texto[contexto.end()] not in _FRONTERA:
            return False
        pos = contexto.end()
    return True


def _revisar(texto: str, piezas: list[_Pieza]) -> tuple[list[_Pieza], list[tuple[int, int]]]:
    """Separa las piezas que se toman de los tramos que se avisan enteros.

    Una pieza no se toma, y se avisa con lo que la estorba, si:
    - toca a otra pieza sin espacio ni junta (se avisan las dos juntas: «#4@20 A/S#3@20»), o
      entre las dos hay algo que no es contexto (tampoco se sabe de cuál es: «4#3DALA E#2@20»);
    - lleva algo pegado delante que no sea una junta justo después de la pieza anterior
      («K-2#4», «H=202E+1G#3»);
    - la precede una cuenta suelta o un multiplicador («4 #4@20», «4 DE #4@20»), o a una
      malla una cabeza de estribo o una palabra de lecho que no se leyeron («A/SLI #3@20»);
    - lo que le sigue hasta la pieza siguiente o el fin de la línea no es contexto."""
    buenas: list[_Pieza] = []
    malos: list[tuple[int, int]] = []
    arrastre: int | None = None  # basura entre la pieza anterior y ésta: no se lee ninguna
    for i, p in enumerate(piezas):
        anterior = piezas[i - 1] if i else None
        siguiente = piezas[i + 1] if i + 1 < len(piezas) else None
        desde = max(anterior.fin if anterior else 0, texto.rfind("|", 0, p.inicio) + 1)
        antes = texto[desde : p.inicio]
        hasta = _fin_del_hueco(texto, p.fin, siguiente)
        inicio, fin, mala = p.inicio, p.fin, False
        if arrastre is not None:
            mala, inicio, arrastre = True, arrastre, None

        if anterior is not None and anterior.fin == p.inicio:
            mala, inicio = True, anterior.inicio
        if siguiente is not None and siguiente.inicio == p.fin:
            mala, fin = True, siguiente.fin
        pegado = _PEGADO_RE.search(antes)
        assert pegado is not None
        junta_valida = (
            pegado.group() in (",", "+")
            and anterior is not None
            and texto[anterior.fin : desde + pegado.start()].strip(" |") == ""
        )
        if pegado.group() and not junta_valida:
            mala, inicio = True, min(inicio, desde + pegado.start())
        elif not _DOBLE_AL_FINAL_RE.search(texto, desde, p.inicio):
            # En su lugar real: el número de «K-1 » o de «15 X 30 » no es una cuenta.
            patrones = [_CUENTA_ANTES_RE, _MULTIPLICADOR_ANTES_RE]
            if p.malla:
                patrones += [_CABEZA_ANTES_RE, _LECHO_SUELTO_ANTES_RE]
            for patron in patrones:
                cuenta = patron.search(texto, desde, p.inicio)
                if cuenta is not None:
                    mala, inicio = True, min(inicio, cuenta.start())
                    break
        if not _hueco_limpio(texto, p.fin, hasta, siguiente):
            mala, fin = True, max(fin, hasta)
            if siguiente is not None and hasta == siguiente.inicio:
                arrastre = inicio
        if mala:
            malos.append((inicio, fin))
        else:
            buenas.append(p)
    return buenas, _unir(malos)


def _residuo(texto: str, cubierto: list[bool]) -> list[tuple[int, int]]:
    """Los pedazos que nadie leyó y que no son contexto, con una cifra, «#», «@» o «/»: cada
    uno es un aviso. Un «#» o «@» suelto se lleva el número que le sigue («@ 20»), un pedazo
    que le sigue y empieza con «@» se le junta («4#5 @ 20»), y unos milímetros detrás también
    («#12 MM»)."""
    libre = [not c for c in cubierto]
    i, n = 0, len(texto)
    while i < n:  # el contexto, en su lugar real, dentro de cada tramo sin leer
        if not libre[i]:
            i += 1
            continue
        j = i
        while j < n and libre[j]:
            j += 1
        for patron in (_CONTEXTO_RE, _DOBLE_RE):
            for m in patron.finditer(texto, i, j):
                ficha_entera = (m.start() == 0 or texto[m.start() - 1] in _ANTES_DE_FICHA) and (
                    m.end() == n or texto[m.end()] in _DESPUES_DE_FICHA
                )
                if ficha_entera:
                    for k in range(m.start(), m.end()):
                        libre[k] = False
        i = j

    trozos: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if libre[i] and texto[i] not in " |":
            j = i
            while j < n and libre[j] and texto[j] not in " |":
                j += 1
            trozos.append((i, j))
            i = j
        else:
            i += 1

    avisos: list[tuple[int, int]] = []
    k = 0
    while k < len(trozos):
        a, b = trozos[k]
        if not _RESIDUO_RE.search(texto[a:b]):
            k += 1
            continue
        while k + 1 < len(trozos):
            a2, b2 = trozos[k + 1]
            siguiente = texto[a2:b2]
            contiguo = texto[b:a2].strip(" ") == ""
            se_junta = (
                (texto[b - 1] in "#@" and siguiente[0].isdigit())
                or siguiente[0] == "@"
                or siguiente in ("MM", "MMS")
            )
            if not (contiguo and se_junta):
                break
            b = b2
            k += 1
        avisos.append((a, b))
        k += 1
    return avisos


def _aviso_sin_leer(cita: str) -> str:
    for m in _NUMERO_EN_CITA_RE.finditer(cita):
        if m.group(1) not in NUMEROS:
            return f"sin leer: «{cita}»: no hay varilla del #{m.group(1)}"
    return f"sin leer: «{cita}»"


def parsear_armado(textos: list[str], familia: str) -> Armado:
    """Lee los textos de un armado (en orden, uno por línea) para un elemento de ``familia``.

    Tres pasadas reconocen piezas, en este orden: juegos de estribos (con sus zonas, que
    pueden seguir en la línea siguiente, y su «VER CORTE»), mallas con su lecho (sólo en
    ``FAMILIAS_CON_PARRILLA``; en otra familia se avisan) y grupos de varillas. Cada pieza se
    revisa contra lo que la rodea en el texto real (``_revisar``): se lee entera o se avisa
    entera, nunca a medias. Al final, todo lo que nadie leyó y no es contexto, si lleva una
    cifra, «#», «@» o «/», se avisa (``_residuo``). Los avisos citan el texto como lo
    escribió el plano (en mayúsculas)."""
    lineas = [t.strip() for t in textos if t and t.strip()]
    pares = [p for p in (_normalizar(t) for t in lineas) if p[0]]
    texto = " | ".join(leer for leer, _ in pares)
    letrero = " | ".join(citar for _, citar in pares)
    consumido = [False] * len(texto)
    piezas: list[_Pieza] = []

    def visible() -> str:
        return "".join(_CONSUMIDO if consumido[i] else c for i, c in enumerate(texto))

    def tomar(p: _Pieza) -> None:
        piezas.append(p)
        for i in range(p.inicio, p.fin):
            consumido[i] = True

    # 1. Juegos de estribos: «EYG#3@15» es estribo y grapa, nunca una malla.
    for leido in _ESTRIBOS_RE.finditer(visible()):
        tomar(_Pieza(leido.start(), leido.end(), estribos=_juegos(leido)))
    # 2. Mallas, sólo donde van, con su lecho.
    for malla in _leer_mallas(visible(), texto, letrero, familia):
        tomar(malla)
    # 3. Grupos de varillas: todos, no sólo el primero («4#5+2#4» son dos). Lo que va pegado
    #    delante se mira en el texto real: un número ya leído también parte al siguiente.
    for grupo in _VARILLAS_RE.finditer(visible()):
        if grupo.start() > 0 and texto[grupo.start() - 1] in _CIFRA_O_GATO:
            continue
        varilla = GrupoVarillas(cantidad=int(grupo["n"]), numero=grupo["num"])
        tomar(_Pieza(grupo.start(), grupo.end(), varillas=[varilla]))

    # 4. Cada pieza se toma entera o se avisa entera con lo que la estorba.
    piezas.sort(key=lambda p: p.inicio)
    buenas, malos = _revisar(texto, piezas)
    avisos: list[tuple[int, str]] = []
    armado = Armado(texto_original=" | ".join(lineas))
    for p in buenas:
        if p.aviso is not None:
            avisos.append((p.inicio, p.aviso))
        armado.estribos += p.estribos
        armado.parrillas += p.parrillas
        armado.longitudinales += p.varillas
    for a, b in malos:
        avisos.append((a, _aviso_sin_leer(letrero[a:b].strip())))
        for i in range(a, b):
            consumido[i] = True

    # 5. Lo que nadie leyó: si no es contexto y lleva una cifra, «#», «@» o «/», se avisa.
    for a, b in _residuo(texto, consumido):
        avisos.append((a, _aviso_sin_leer(letrero[a:b].strip(",;: "))))

    armado.avisos = [aviso for _, aviso in sorted(avisos, key=lambda par: par[0])]
    return armado


# ------------------------------------------------------------------ textos canónicos
# Lo que el texto lleva (cantidades, números, separaciones, tramos, referencia, lecho y
# sentidos) se escribe de modo que se lea igual, o el render revienta con ValueError: nunca
# un texto que diga otra cosa. Lo que se asigna después y no viene del texto (``formas``,
# ``formas_fuente``, ``posicion``, ``longitud_m``) no se escribe.

_TRAMOS_ESCRIBIBLES = ((), ("todo",), ("extremos",), ("extremos", "centro"))
_REFERENCIAS = ("VER CORTE", "VER DETALLE")


def _cuenta(cantidad: int) -> int:
    if not 1 <= cantidad <= 99:
        raise ValueError(f"cantidad {cantidad} fuera de 1 a 99: el texto no la puede llevar")
    return cantidad


def _numero(numero: str) -> str:
    if numero not in NUMEROS:
        raise ValueError(f"varilla #{numero} fuera de la tabla: el texto no la puede llevar")
    return numero


def _cm(separacion_m: float | None) -> str:
    if separacion_m is None:
        raise ValueError("zona sin separación: el texto no la puede llevar")
    cm = round(separacion_m * 100, 2)
    if not 1 <= cm <= 999.99 or abs(separacion_m * 100 - cm) > 1e-6:
        raise ValueError(f"separación {separacion_m} m: el texto no la puede llevar")
    return str(int(cm)) if cm == int(cm) else f"{cm:g}"


def _texto_zonas(zonas: list[Zona]) -> str:
    tramos = tuple(z.tramo for z in zonas)
    if tramos not in _TRAMOS_ESCRIBIBLES:
        raise ValueError(f"zonas {list(tramos)}: el texto no las puede llevar")
    prefijos = {"todo": "", "extremos": " EXT", "centro": " CENTRO"}
    return "".join(f"{prefijos[z.tramo]}@{_cm(z.separacion_m)}" for z in zonas)


def _cabeza(j: JuegoEstribos) -> str:
    n = _cuenta(j.cantidad)
    if j.tipo == "liga":
        return "LIGA" if n == 1 else f"{n}LIGAS"
    letra = "E" if j.tipo == "estribo" else "G"
    return letra if n == 1 else f"{n}{letra}"


def texto_longitudinal(a: Armado) -> str:
    """«4#5+2#4»."""
    return "+".join(f"{_cuenta(g.cantidad)}#{_numero(g.numero)}" for g in a.longitudinales)


def texto_estribos(a: Armado) -> str:
    """«EYG#3@15», «2E#3@15», «2E+1G#3 EXT@10 CENTRO@15», «2E#3 VER CORTE».

    Un estribo seguido de una grapa del mismo número, zonas y referencia se escribe junto:
    «EYG» si es uno y uno, «nE+mG» si no."""
    partes = []
    juegos = a.estribos
    i = 0
    while i < len(juegos):
        j = juegos[i]
        siguiente = juegos[i + 1] if i + 1 < len(juegos) else None
        if (
            j.tipo == "estribo"
            and siguiente is not None
            and siguiente.tipo == "grapa"
            and (siguiente.numero, siguiente.zonas, siguiente.referencia)
            == (j.numero, j.zonas, j.referencia)
        ):
            ne, ng = _cuenta(j.cantidad), _cuenta(siguiente.cantidad)
            cabeza = "EYG" if ne == ng == 1 else f"{ne}E+{ng}G"
            i += 2
        else:
            cabeza = _cabeza(j)
            i += 1
        texto = f"{cabeza}#{_numero(j.numero)}{_texto_zonas(j.zonas)}"
        if j.referencia is not None:
            if j.referencia not in _REFERENCIAS:
                raise ValueError(f"referencia «{j.referencia}»: el texto no la puede llevar")
            texto += f" {j.referencia}"
        partes.append(texto)
    return " ".join(partes)


def texto_parrillas(a: Armado) -> str:
    """«LS #4@20 A/S LI #4@20 A/S»; sin lecho cuando es único, sin sufijo si no dice sentidos.

    Siempre con el lecho delante. Mallas con lecho y mallas sin lecho no se pueden escribir
    juntas (el texto no diría a cuál va cada lecho): ValueError."""
    if len({p.lecho == "unico" for p in a.parrillas}) > 1:
        raise ValueError("mallas con lecho y sin lecho juntas: el texto no las distingue")
    lechos = {"sup": "LS ", "inf": "LI ", "unico": ""}
    sentidos = {"ambos": " A/S", "x": " EN X", "y": " EN Y", None: ""}
    return " ".join(
        f"{lechos[p.lecho]}#{_numero(p.numero)}@{_cm(p.separacion_m)}{sentidos[p.sentidos]}"
        for p in a.parrillas
    )


def texto_armado(a: Armado) -> str:
    """Longitudinales, estribos y parrillas, separados por un espacio."""
    return " ".join(
        parte for parte in (texto_longitudinal(a), texto_estribos(a), texto_parrillas(a)) if parte
    )
