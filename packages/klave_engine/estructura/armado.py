"""El armado de un elemento como estructura, no como texto, y el parser que no pierde nada.

Un texto de armado («4#5+2#4», «2E+1G#3EXT@10» / «CENTRO@15», «LS #4@20 A/S») se lee en
grupos de varillas longitudinales, juegos de estribos con sus zonas y parrillas. La regla
es que nada se pierde en silencio: cada pieza del texto se lee entera o se avisa entera,
con lo que la estorba. Una malla sólo se toma en las familias que llevan parrilla; en un
castillo, una columna o una trabe un ``#n@s`` suelto se avisa, nunca se convierte en malla.

Lo que rodea a una pieza lo decide un solo lector de fichas (``_armado_texto``): el hueco
después de la pieza, lo que la precede y el residuo final se miran con la misma lista de
contexto.

Los textos canónicos (``texto_longitudinal``, ``texto_estribos``, ``texto_parrillas``,
``texto_armado``) vuelven a dar la misma estructura al leerse otra vez."""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from klave_engine.estructura._armado_texto import (
    AMBOS,
    ATA,
    CONSUMIDO,
    DOBLE_RE,
    ESTORBA,
    atado,
    fichas,
    fin_del_hueco,
    hueco_limpio,
    normalizar,
    residuo,
)

# Las llaves de ``costing.steel.BAR_KG_PER_M``, en su orden. Se escriben aquí y no se
# importan porque ``costing.steel`` leerá el armado con este módulo (un ciclo de
# importación); una prueba garantiza que las dos listas no se separen.
NUMEROS: tuple[str, ...] = ("2", "2.5", "3", "4", "5", "6", "7", "8", "10", "12")

FAMILIAS_CON_PARRILLA = frozenset(
    {"losa", "muro", "muro_concreto", "zapata", "dado", "losa_cimentacion"}
)

Forma = Literal["perimetral", "rombo", "interior", "grapa", "liga"]
Lecho = Literal["sup", "inf", "unico"]


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
    lecho: Lecho
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


# ------------------------------------------------------------------ gramática de las piezas
# Las expresiones sólo reconocen piezas, y un número es siempre una ficha entera («#32» no
# es «#3», «@1520» no es «@152»). Si lo que rodea a una pieza la deja a medias lo decide
# ``_revisar`` sobre el texto real; lo que nadie leyó lo revisa ``residuo``.

_NUM = (
    "(?:" + "|".join(re.escape(n) for n in sorted(NUMEROS, key=len, reverse=True)) + r")(?!\d|\.\d)"
)
_SEP = r"[1-9]\d{0,2}(?:\.\d{1,2})?(?!\d|\.\d)"  # cm; el rango plausible se revisa aparte
_RANGO_ESTRIBOS = (3.0, 60.0)  # cm
_RANGO_MALLAS = (5.0, 100.0)
_CM = r"(?:\s?CMS?\.?)?(?:\s?C\s*/\s*C)?"  # la unidad y «C/C», pegadas a la separación
# Opcionalmente a través del salto de línea: «2E#3EXT@10» / «CENTRO@20» son un solo juego.
_LINEA = r"(?:\s*\|)?\s*"
_LS = r"(?:LS|L\.S\.?|LECHO\s+SUP\w*\.?)"
_LI = r"(?:LI|L\.I\.?|LECHO\s+INF\w*\.?)"
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

# El cuerpo de una malla con sus sentidos, que van justo delante («A/S #4@20») o justo
# detrás, también en la línea siguiente («#4@20» / «A/S»). Su lecho («LS», «L.I.», «LECHO
# SUPERIOR») va aparte, delante o detrás.
_SALTO_O_ESPACIO = r"(?:\s*\|\s*|\s+)"
_MALLA_RE = re.compile(
    rf"(?:(?<![A-Z])(?:(?:EN\s+)?(?P<ambos0>{AMBOS})|(?:EN|SENTIDO)\s+(?P<xy0>[XY]))\s+)?"
    rf"(?P<cuerpo>#\s*(?P<num>{_NUM})\s*@\s*(?P<sep>{_SEP}){_CM})"
    rf"(?:{_SALTO_O_ESPACIO}(?:EN\s+)?(?P<ambos>{AMBOS})(?![A-Z0-9])"
    rf"|{_SALTO_O_ESPACIO}(?:EN|SENTIDO)\s+(?P<xy>[XY])(?![A-Z0-9]))?"
)
_LECHO_RE = re.compile(
    rf"(?<![A-Z.])(?:EN\s+)?(?P<l1>{_LS}|{_LI})"
    rf"(?:\s*(?:Y|E|,|\+)\s*(?P<l2>{_LS}|{_LI}))?(?![A-Z.])"
    rf"(?:\s*(?P<ambos>{AMBOS})(?![A-Z0-9]))?"
)
_ES_LS = re.compile(_LS)
_SENTIDO_XY: dict[str, Literal["x", "y"]] = {"X": "x", "Y": "y"}

_VARILLAS_RE = re.compile(
    rf"(?<![\d.#@])(?P<n>{_CUENTA})\s*(?:VARILLAS|VARS?\.?|V)?\s*#\s*(?P<num>{_NUM})(?!\s*@)"
)
_CIFRA_O_GATO = "0123456789#.@"  # lo que, pegado delante, parte un número (aunque esté leído)
_PEGADO_RE = re.compile(rf"[^ {CONSUMIDO}]*$")
# Una cuenta suelta delante de una pieza la deja a medias: «4 », «4 VARS », «4 VARILLAS DE »,
# «4 PZAS », «(4) », «4-», «4VARS », «4 DE », «4 X », «3 PARRILLAS ». No es cuenta el número
# de una marca («K-1 ») ni el final de una medida («15 X 30 », «H=20 »).
_CUENTA_ANTES_RE = re.compile(
    r"(?<![\w.=\-×#@])(?<![=X×]\s)(?:\(\s*\d+\s*\)|\d+)"
    r"\s*(?:-|[X×](?![A-Z0-9])|(?:VARILLAS?|VARS?\.?|V|PZAS?\.?|PIEZAS?|PARRILLAS?|LECHOS?"
    r"|CAPAS?|MALLAS?|DEL?)(?:\s+DEL?)?)?\s*$"
)
# Una cabeza de estribo que no se leyó delante de una malla («ESTRIBOS: #3@20»), también
# pegada a otra cosa («.E. #3@20», «XE. #3@20», «(E) #3@20»): no es una malla.
_CABEZA = r"(?:E|EST|ESTR|ESTRIBOS?|G|GRAPAS?|LIGAS?|EYG)"
_CABEZA_ANTES_RE = re.compile(
    rf"(?:(?<![\w.])\d*{_CABEZA}[.:,]?|(?<![^\s|])[^\s|]*?{_CABEZA}[.:)])(?:\s+DEL?)?\s*$"
)
# Justo antes de una malla, una palabra de lecho que no se reconoció como marca («A/SLI»)
# o un plural sin cuenta («… LECHOS», «… PARRILLAS»): la malla no se sabe cuántas son.
_LECHO_SUELTO_ANTES_RE = re.compile(
    r"(?:L\.?[SI]\.?|LECHO\s+(?:SUP|INF)\w*\.?|(?:[^\s|]+\s+)?(?:PARRILLAS|LECHOS|CAPAS|MALLAS))"
    r"(?:\s+DEL?)?\s*$"
)
_NUMERO_EN_CITA_RE = re.compile(r"[#Ø]\s*(\d+(?:\.\d+)?)")
_FEMENINAS = frozenset(
    {"columna", "trabe", "contratrabe", "dala", "cadena", "losa", "zapata", "pila", "viga"}
)


# ------------------------------------------------------------------ lectura


@dataclass
class _Pieza:
    """Un pedazo del texto que una de las tres pasadas reconoció. Se toma (su estructura entra
    al armado o su ``aviso`` se emite) sólo si lo que la rodea es contexto. ``extras`` son las
    fichas que consumió fuera de su tramo (una palabra de doble lecho que concuerda con sus
    marcas «LS … LI …»)."""

    inicio: int
    fin: int
    malla: bool = False
    estribos: list[JuegoEstribos] = field(default_factory=list)
    parrillas: list[Parrilla] = field(default_factory=list)
    varillas: list[GrupoVarillas] = field(default_factory=list)
    aviso: str | None = None  # reconocida pero no se toma: malla fuera de lugar, lecho ambiguo
    extras: list[tuple[int, int]] = field(default_factory=list)


def _metros(cm: str) -> float:
    return float(cm) / 100


def _en_rango(cm: float, rango: tuple[float, float]) -> bool:
    return rango[0] <= cm <= rango[1]


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


def _leer_estribos(vista: str, letrero: str) -> list[_Pieza]:
    """Los juegos de estribos como piezas; una separación fuera de rango avisa el juego entero."""
    piezas = []
    for m in _ESTRIBOS_RE.finditer(vista):
        a, b = m.start(), m.end()
        separaciones = [float(s) for s in (m["ext"], m["centro"], m["sep"]) if s]
        if all(_en_rango(s, _RANGO_ESTRIBOS) for s in separaciones):
            piezas.append(_Pieza(a, b, estribos=_juegos(m)))
        else:
            aviso = f"separación fuera de rango: «{letrero[a:b].strip()}»"
            piezas.append(_Pieza(a, b, aviso=aviso))
    return piezas


def _con_articulo(familia: str) -> str:
    return f"{'una' if familia in _FEMENINAS else 'un'} {familia.replace('_', ' ')}"


def _lechos(marca: re.Match[str]) -> list[Lecho]:
    """Los lechos que dice una marca («L.S. Y L.I.» son dos)."""
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
    L.I.»), con una sola convención por texto. Una palabra de doble lecho («DOBLE PARRILLA»,
    «DOBLEMENTE ARMADA», «AMBOS LECHOS», «2 PARRILLAS», «2 LECHOS», «2 CAPAS») unida por
    contexto a una malla única y sola, delante de ella, la vuelve dos lechos; unida a mallas
    que ya dicen «LS» y «LI» concuerda y se consume; en cualquier otro caso ninguna malla se
    toma: cada una (con las marcas y palabras que tiene al lado) se avisa como lecho ambiguo,
    y una marca suelta como lecho sin su malla."""
    mallas = [
        m
        for m in _MALLA_RE.finditer(vista)
        if m.start("cuerpo") == 0 or texto[m.start("cuerpo") - 1] not in _CIFRA_O_GATO
    ]
    if not mallas:
        return []
    marcas = list(_LECHO_RE.finditer(vista))
    dobles = list(DOBLE_RE.finditer(vista))

    def junto(a: int, b: int) -> bool:  # sólo espacios entre a y b, en la misma línea
        return a <= b and vista[a:b].strip(" ") == ""

    def marca_junto(malla: re.Match[str], delante: bool) -> int | None:
        for k, marca in enumerate(marcas):
            if junto(marca.end(), malla.start()) if delante else junto(malla.end(), marca.start()):
                return k
        return None

    delante = [marca_junto(m, True) for m in mallas]
    detras = [marca_junto(m, False) for m in mallas]

    # 1. El tramo de cada malla con su marca, y sus lechos (None: el texto no lo deja claro).
    tramos: list[tuple[int, int]] = []
    lechos: list[list[Lecho]] | None = []
    ambos_de_marca = [False] * len(mallas)
    if marcas:
        usadas = _convencion(delante, detras, len(marcas))
        for i, malla in enumerate(mallas):
            a, b = malla.start(), malla.end()
            if usadas is None:
                for k in (delante[i], detras[i]):
                    if k is not None:
                        a, b = min(a, marcas[k].start()), max(b, marcas[k].end())
                lechos = None
            else:
                k = usadas[i]
                assert k is not None and lechos is not None
                a, b = min(a, marcas[k].start()), max(b, marcas[k].end())
                lechos.append(_lechos(marcas[k]))
                ambos_de_marca[i] = bool(marcas[k]["ambos"])
            tramos.append((a, b))
    else:
        tramos = [(m.start(), m.end()) for m in mallas]
        lechos = [["unico"] for _ in mallas]

    # 2. Cada palabra de doble lecho, atada por contexto a la malla que le sigue o, si no,
    #    a la que la precede. Las que no se atan a ninguna quedan para el residuo.
    delante_de: dict[int, list[re.Match[str]]] = {}
    detras_de: dict[int, list[re.Match[str]]] = {}
    for d in dobles:
        k = next((k for k, (a, _) in enumerate(tramos) if a >= d.end()), None)
        if k is not None and atado(vista, d.end(), tramos[k][0]):
            delante_de.setdefault(k, []).append(d)
            continue
        k = next((k for k, (_, b) in reversed(list(enumerate(tramos))) if b <= d.start()), None)
        if k is not None and atado(vista, tramos[k][1], d.start()):
            detras_de.setdefault(k, []).append(d)

    # 3. Qué hacen esas palabras: concuerdan con «LS … LI …», doblan una malla única y sola,
    #    o vuelven ambiguo el lecho de todas.
    extras: list[tuple[int, int]] = []
    if dobles and lechos is not None:
        cubiertos = {lecho for lista in lechos for lecho in lista}
        atadas = [d for lista in (*delante_de.values(), *detras_de.values()) for d in lista]
        if {"sup", "inf"} <= cubiertos:
            extras = [(d.start(), d.end()) for d in atadas]
        elif len(tramos) == 1 and lechos[0] == ["unico"] and len(dobles) == 1 and 0 in delante_de:
            tramos[0] = (dobles[0].start(), tramos[0][1])
            lechos[0] = ["sup", "inf"]
        else:
            lechos = None

    if lechos is None:
        con_palabras = []
        for k, (a, b) in enumerate(tramos):
            for d in delante_de.get(k, []) + detras_de.get(k, []):
                a, b = min(a, d.start()), max(b, d.end())
            con_palabras.append((a, b))
        piezas = [
            _Pieza(a, b, malla=True, aviso=f"lecho ambiguo: «{letrero[a:b].strip()}»: no se toma")
            for a, b in _unir(con_palabras)
        ]
        al_lado = {k for k in delante + detras if k is not None}
        for k, suelta in enumerate(marcas):
            if k not in al_lado:
                a, b = suelta.start(), suelta.end()
                aviso = f"lecho «{letrero[a:b].strip()}» sin su malla: no se toma"
                piezas.append(_Pieza(a, b, malla=True, aviso=aviso))
        return piezas

    piezas = []
    for malla, (a, b), lechos_de_malla, ambos in zip(
        mallas, tramos, lechos, ambos_de_marca, strict=True
    ):
        cita = letrero[a:b].strip()
        if familia not in FAMILIAS_CON_PARRILLA:
            aviso = f"malla «{cita}» en {_con_articulo(familia)}: no se toma"
            piezas.append(_Pieza(a, b, malla=True, aviso=aviso))
            continue
        if not _en_rango(float(malla["sep"]), _RANGO_MALLAS):
            piezas.append(_Pieza(a, b, malla=True, aviso=f"separación fuera de rango: «{cita}»"))
            continue
        sentidos: Literal["ambos", "x", "y"] | None = (
            "ambos"
            if malla["ambos"] or malla["ambos0"] or ambos
            else _SENTIDO_XY.get(malla["xy"] or malla["xy0"] or "")
        )
        parrillas = [
            Parrilla(
                numero=malla["num"],
                separacion_m=_metros(malla["sep"]),
                lecho=lecho,
                sentidos=sentidos,
            )
            for lecho in lechos_de_malla
        ]
        piezas.append(_Pieza(a, b, malla=True, parrillas=parrillas))
    piezas[0].extras = extras
    return piezas


def _estorbo_delante(
    texto: str,
    vista: str,
    desde: int,
    p: _Pieza,
    anterior: _Pieza | None,
    consumido: list[bool],
) -> int | None:
    """Dónde empieza lo que estorba delante de la pieza, o ``None`` si nada la estorba:
    algo pegado que no sea una junta justo después de la pieza anterior («K-2#4»); una
    cuenta suelta («4 #4@20»); delante de una malla, una cabeza de estribo o una palabra de
    lecho que no se leyeron («ESTRIBOS: #3@20», «A/SLI #3@20»); o una palabra que nadie
    tomó (de doble lecho, multiplicador, sentido) unida a la pieza por contexto."""
    antes = vista[desde : p.inicio]
    pegado = _PEGADO_RE.search(antes)
    assert pegado is not None
    if pegado.group():
        junta_valida = (
            pegado.group() in (",", "+")
            and anterior is not None
            and texto[anterior.fin : desde + pegado.start()].strip(" |") == ""
        )
        if not junta_valida:
            return desde + pegado.start()
    patrones = [_CUENTA_ANTES_RE]
    if p.malla:
        patrones += [_CABEZA_ANTES_RE, _LECHO_SUELTO_ANTES_RE]
    for patron in patrones:
        cuenta = patron.search(vista, desde, p.inicio)
        if cuenta is not None:
            return cuenta.start()
    estorbo: int | None = None
    for f in fichas(texto, desde, p.inicio, consumido):
        if f.tipo in ESTORBA:
            estorbo = f.inicio
        elif f.tipo not in ATA and f.tipo != "consumido":
            estorbo = None
    return estorbo


def _revisar(
    texto: str, vista: str, piezas: list[_Pieza], consumido: list[bool]
) -> tuple[list[_Pieza], list[tuple[int, int]]]:
    """Separa las piezas que se toman de los tramos que se avisan enteros.

    Una pieza no se toma, y se avisa con lo que la estorba, si:
    - toca a otra pieza sin espacio ni junta (se avisan las dos juntas: «#4@20 A/S#3@20»), o
      entre las dos hay algo que no es contexto (tampoco se sabe de cuál es: «4#3DALA E#2@20»);
    - algo la estorba delante (``_estorbo_delante``);
    - lo que le sigue hasta la pieza siguiente o el fin de la línea no es contexto."""
    buenas: list[_Pieza] = []
    malos: list[tuple[int, int]] = []
    arrastre: int | None = None  # basura entre la pieza anterior y ésta: no se lee ninguna
    for i, p in enumerate(piezas):
        anterior = piezas[i - 1] if i else None
        siguiente = piezas[i + 1] if i + 1 < len(piezas) else None
        inicio_siguiente = siguiente.inicio if siguiente else None
        desde = max(anterior.fin if anterior else 0, texto.rfind("|", 0, p.inicio) + 1)
        hasta = fin_del_hueco(texto, p.fin, inicio_siguiente)
        inicio, fin, mala = p.inicio, p.fin, False
        if arrastre is not None:
            mala, inicio, arrastre = True, arrastre, None
        if anterior is not None and anterior.fin == p.inicio:
            mala, inicio = True, anterior.inicio
        if siguiente is not None and siguiente.inicio == p.fin:
            mala, fin = True, siguiente.fin
        estorbo = _estorbo_delante(texto, vista, desde, p, anterior, consumido)
        if estorbo is not None:
            mala, inicio = True, min(inicio, estorbo)
        if not hueco_limpio(texto, p.fin, hasta, inicio_siguiente, consumido):
            mala, fin = True, max(fin, hasta)
            if hasta == inicio_siguiente:
                arrastre = inicio
        if mala:
            malos.append((inicio, fin))
        else:
            buenas.append(p)
    return buenas, _unir(malos)


def _aviso_sin_leer(cita: str) -> str:
    for m in _NUMERO_EN_CITA_RE.finditer(cita):
        if m.group(1) not in NUMEROS:
            return f"sin leer: «{cita}»: no hay varilla del #{m.group(1)}"
    return f"sin leer: «{cita}»"


def parsear_armado(textos: list[str], familia: str) -> Armado:
    """Lee los textos de un armado (en orden, uno por línea) para un elemento de ``familia``.

    Tres pasadas reconocen piezas, en este orden: juegos de estribos (con sus zonas, que
    pueden seguir en la línea siguiente, y su «VER CORTE»), mallas con su lecho y sentidos
    (sólo en ``FAMILIAS_CON_PARRILLA``; en otra familia se avisan) y grupos de varillas. Cada
    pieza se revisa contra lo que la rodea en el texto real (``_revisar``): se lee entera o
    se avisa entera, nunca a medias. Al final, todo lo que nadie leyó y no es contexto se
    avisa (``residuo``). Los avisos citan el texto como lo escribió el plano (en mayúsculas)."""
    lineas = [t.strip() for t in textos if t and t.strip()]
    pares = [p for p in (normalizar(t) for t in lineas) if p[0]]
    texto = " | ".join(leer for leer, _ in pares)
    letrero = " | ".join(citar for _, citar in pares)
    consumido = [False] * len(texto)
    piezas: list[_Pieza] = []

    def visible() -> str:
        return "".join(CONSUMIDO if consumido[i] else c for i, c in enumerate(texto))

    def tomar(p: _Pieza) -> None:
        piezas.append(p)
        for a, b in [(p.inicio, p.fin), *p.extras]:
            for i in range(a, b):
                consumido[i] = True

    # 1. Juegos de estribos: «EYG#3@15» es estribo y grapa, nunca una malla.
    for juego in _leer_estribos(visible(), letrero):
        tomar(juego)
    # 2. Mallas, sólo donde van, con su lecho y sus sentidos.
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
    buenas, malos = _revisar(texto, visible(), piezas, consumido)
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

    # 5. Lo que nadie leyó: si no es contexto, se avisa.
    for a, b, tipo in residuo(texto, consumido):
        if tipo == "otro":
            avisos.append((a, _aviso_sin_leer(letrero[a:b].strip(",;: "))))
        else:
            avisos.append((a, f"{tipo} «{letrero[a:b].strip('() ')}» sin su malla: no se toma"))
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


def _cm(separacion_m: float | None, rango: tuple[float, float]) -> str:
    """La separación en cm, dentro del rango que el parser vuelve a leer."""
    if separacion_m is None:
        raise ValueError("zona sin separación: el texto no la puede llevar")
    cm = round(separacion_m * 100, 2)
    if not _en_rango(cm, rango) or abs(separacion_m * 100 - cm) > 1e-6:
        raise ValueError(f"separación {separacion_m} m: el texto no la puede llevar")
    return str(int(cm)) if cm == int(cm) else f"{cm:g}"


def _texto_zonas(zonas: list[Zona]) -> str:
    tramos = tuple(z.tramo for z in zonas)
    if tramos not in _TRAMOS_ESCRIBIBLES:
        raise ValueError(f"zonas {list(tramos)}: el texto no las puede llevar")
    prefijos = {"todo": "", "extremos": " EXT", "centro": " CENTRO"}
    return "".join(f"{prefijos[z.tramo]}@{_cm(z.separacion_m, _RANGO_ESTRIBOS)}" for z in zonas)


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

    Siempre con el lecho delante y los sentidos detrás. Mallas con lecho y mallas sin lecho
    no se pueden escribir juntas (el texto no diría a cuál va cada lecho): ValueError."""
    if len({p.lecho == "unico" for p in a.parrillas}) > 1:
        raise ValueError("mallas con lecho y sin lecho juntas: el texto no las distingue")
    lechos = {"sup": "LS ", "inf": "LI ", "unico": ""}
    sentidos = {"ambos": " A/S", "x": " EN X", "y": " EN Y", None: ""}
    return " ".join(
        f"{lechos[p.lecho]}#{_numero(p.numero)}@{_cm(p.separacion_m, _RANGO_MALLAS)}"
        f"{sentidos[p.sentidos]}"
        for p in a.parrillas
    )


def texto_armado(a: Armado) -> str:
    """Longitudinales, estribos y parrillas, separados por un espacio."""
    return " ".join(
        parte for parte in (texto_longitudinal(a), texto_estribos(a), texto_parrillas(a)) if parte
    )
