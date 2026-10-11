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
    LADO,
    LADO_FINAL,
    OBJETO_AJENO_RE,
    REFERENCIA,
    atado,
    de_objetos,
    fichas,
    fin_del_hueco,
    hueco_limpio,
    normalizar,
    residuo,
    traducciones,
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
    """«4#5»: cuántas varillas y de qué número; «4#3 VER DETALLE»: con la referencia que le sigue
    (R102: un puntero se guarda donde esté, tras los estribos o tras las varillas)."""

    cantidad: int
    numero: str
    posicion: Literal["esquina", "cara", "lecho_sup", "lecho_inf", "ambos"] | None = None
    referencia: str | None = None  # «VER CORTE»: las varillas se remiten a otro dibujo


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

# Una referencia tras una pieza es suya, con las marcas a las que remite y lo que la cierra
# (R110): «VER CORTE C-2», «(VER CORTE C-2)», «VER CORTES C-1 Y C-2», «VER DET. K-2.».
_VER = REFERENCIA
_PALABRAS_DE_PUNTERO = re.compile(r"VER\s+(?:CORTES?|DETALLES?|DETS?\.?)")

# La cantidad de un juego no puede ser el número de la varilla anterior («4#3 E#2@15»), una
# separación («@20E#3»), parte de una medida («15X30 E#2@20») ni el número de una marca («K-7
# E#3@20»): no la precede una letra, un dígito, «#», «@», «.» o «-».
# «nE+mG» y «nG+mE» son el mismo juego de estribos y grapas.
_ESTRIBOS_RE = re.compile(
    r"(?<![A-Z0-9#.@\-])(?<![#@]\s)"
    rf"(?:(?P<n1>{_CUENTA_P})\s*)?"
    r"(?:"
    rf"(?P<e>{_E})(?:{_JUNTA}(?:(?P<n2>{_CUENTA_P})\s*)?(?P<eg>{_G}))?"
    rf"|(?P<g>{_G})(?:{_JUNTA}(?:(?P<n3>{_CUENTA_P})\s*)?(?P<ge>{_E}))?"
    r"|(?P<l>LIGAS?)"
    r")"
    r"(?:\s+DEL?)?"
    # La cabeza puede acabar su renglón y el «#n» empezar el siguiente («ESTRIBOS» / «#3@15»).
    rf"{_LINEA}#\s*(?P<num>{_NUM})"
    r"(?:"
    rf"{_LINEA}EXT(?:REMOS?)?\.?\s*@\s*(?P<ext>{_SEP}){_CM}"
    rf"(?:{_LINEA}(?:Y\s+)?CENTRO\s*@\s*(?P<centro>{_SEP}){_CM})?"
    rf"|{_LINEA}@\s*(?P<sep>{_SEP}){_CM}"
    r")?"
    rf"(?:{_LINEA}(?P<ref>{_VER}))?"
)

# El cuerpo de una malla. Su lecho («LS», «L.I.», «LECHO SUPERIOR») y sus sentidos («A/S»,
# «EN X») van aparte, pegados delante o detrás; ``_leer_mallas`` decide la convención.
_MALLA_RE = re.compile(rf"#\s*(?P<num>{_NUM})\s*@\s*(?P<sep>{_SEP}){_CM}")
_LECHO_RE = re.compile(
    rf"(?<![A-Z.])(?:EN\s+)?(?P<l1>{_LS}|{_LI})"
    rf"(?:\s*(?:Y|E|,|\+)\s*(?P<l2>{_LS}|{_LI}))?(?![A-Z.])"
)
_SENTIDO_RE = re.compile(
    rf"(?<![A-Z])(?:(?:EN\s+)?(?P<ambos>{AMBOS})|(?:EN|SENTIDO)\s+(?P<xy>[XY]))(?![A-Z0-9])"
)
_ES_LS = re.compile(_LS)
_SENTIDO_XY: dict[str, Literal["x", "y"]] = {"X": "x", "Y": "y"}

# «4#5», «4 VARS #5», «4V#4», «4 VARILLAS DEL #3», «8 PZAS #6», «4-#3», «4) #3» (R93: el «4-» es
# la cuenta) y, con la palabra delante, «V4#4», «VAR 4#4» (PRUEBA-1: «V4#4 E#3»); con la
# referencia que le sigue, como un juego de estribos («4#3 VER DET.», R102).
_VARILLAS_RE = re.compile(
    rf"(?:(?<![A-Z0-9.#@])(?:VARS?\.?|V)\s*(?P<v>{_CUENTA})"
    rf"|(?<![\d.#@])(?P<n>{_CUENTA})\s*(?:[-)]\s*)?"
    r"(?:(?:VARILLAS|VARS?\.?|PZAS?\.?|PIEZAS|V)(?:\s+DEL?)?)?)"
    rf"\s*#\s*(?P<num>{_NUM})(?!\s*@)"
    rf"(?:(?:\s*\|\s*|\s+)(?P<ref>{_VER}))?"
)
_CIFRA_O_GATO = "0123456789#.@"  # lo que, pegado delante, parte un número (aunque esté leído)
_PEGADO_RE = re.compile(rf"[^ {CONSUMIDO}]*$")
# Una cuenta suelta delante de una pieza la deja a medias: «4 », «4 VARS », «4 VARILLAS DE »,
# «4 PZAS », «(4) », «4-», «4VARS », «4 DE », «4 X », «3 PARRILLAS ». No es cuenta el número
# de una marca («K-1 ») ni el final de una medida («15 X 30 », «H=20 », los decimales de
# «20X40,5 », R109).
_CUENTA_ANTES_RE = re.compile(
    r"(?<![\w.=\-×#@])(?<![=X×]\s)(?<![X×]\d,)(?<![X×]\d\d,)(?<![X×]\d\d\d,)"
    r"(?<![X×]\s\d,)(?<![X×]\s\d\d,)(?<![X×]\s\d\d\d,)(?:\(\s*\d+\s*\)|\d+)"
    r"\s*(?:-|[X×](?![A-Z0-9])|(?:VARILLAS?|VARS?\.?|V|PZAS?\.?|PIEZAS?|PARRILLAS?|LECHOS?"
    r"|CAPAS?|MALLAS?|DEL?)(?:\s+DEL?)?)?\s*$"
)
# Una cabeza de estribo que no se leyó, más atrás en la misma línea que un «#n@s» y sin
# otra pieza en medio («ESTRIBOS: #3@20», «ESTRIBOS DOBLES #3@15», «.E. #3@20», «(E) #3@20»):
# ese «#n@s» no es una malla. La cabeza es la ficha entera (con su cuenta o su junta, a lo
# más entre puntuación) o va pegada a una cifra o un signo («@20E.»); una palabra que sólo
# termina en E o G («XE.», «LIBRE:», «TIPO E)») es una palabra.
_CABEZA = r"(?:EYG|E|EST|ESTR|ESTRIBOS?|G|GRAPAS?|LIGAS?)"
_CUENTA_DE_CABEZA = r"(?:\(\d{1,2}\)|\d{1,2})?"
_CABEZA_FICHA = rf"{_CUENTA_DE_CABEZA}{_CABEZA}(?:[Y+/&,\-]{_CUENTA_DE_CABEZA}{_CABEZA})?"
_CABEZA_EN_LINEA_RE = re.compile(
    rf"(?<![^\s|])(?:\(\s*{_CABEZA_FICHA}\s*\)|[.:]*{_CABEZA_FICHA}[.:,]*"
    rf"|[^\s|]*[^A-Z\s|(]{_CABEZA}[.:)]*)(?=[\s|,+]|$)"
)
# R26: también es cabeza la ficha que EMPIEZA (tras «(», «[» o «"») con una cabeza seguida de
# algo que no es letra: «(ESTRIBOS CERRADOS)», «ESTRIBOS(2)», «E(DOBLE)», «ESTRIBOS;»,
# «[ESTRIBOS]», «"ESTRIBOS"». No lo es una marca («E-1», «G-2A»), ni una E o una G suelta que
# cierra el paréntesis de otra palabra («(TIPO E)», R24).
_CABEZA_AL_INICIO_RE = re.compile(
    rf"(?<![^\s|])(?P<abre>[(\[\"]?)(?P<cabeza>{_CUENTA_DE_CABEZA}{_CABEZA})(?![A-Z])"
    r"(?P<resto>[^\s|]*)"
)
_MARCA_SOLA_RE = re.compile(r"[A-Z]{1,4}-\d{1,3}[A-Z]?(?:\.\d{1,2})?[.,;:)\]\"]*")
# Antes de una malla, en la misma línea y sin otra pieza en medio, un sentido que no se
# reconoció como tal («SENTIDO CORTO #4@20», «CORTEAMBOS SENTIDOS #3@15»), o pegado a otra
# cosa justo delante («XEN X #4@20», «CORTEA/S #4@20»): la malla no sabe su sentido.
_SENTIDO_SUELTO_RE = re.compile(
    r"(?<![^\s|])(?:(?:[^\s|]*AMB[OA]S\s+)?[^\s|]*(?:SENTIDOS?|DIRECCION(?:ES)?)(?![A-Z])"
    r"|[^\s|]*(?:EN|SENTIDO)\s+[XY](?=\s*$)|[^\s|]*A\s*/\s*S\.?(?=\s*$))"
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
    marcas «LS … LI …»); ``cedidas``, las que tiene al lado pero son de otra pieza, que las
    avisa (una palabra de doble lecho entre mallas «LS … LI …» y unas varillas)."""

    inicio: int
    fin: int
    malla: bool = False
    estribos: list[JuegoEstribos] = field(default_factory=list)
    parrillas: list[Parrilla] = field(default_factory=list)
    varillas: list[GrupoVarillas] = field(default_factory=list)
    aviso: str | None = None  # reconocida pero no se toma: malla fuera de lugar, lecho ambiguo
    extras: list[tuple[int, int]] = field(default_factory=list)
    cedidas: list[tuple[int, int]] = field(default_factory=list)


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


def _referencia(escrita: str | None) -> str | None:
    """Una referencia como se escribe en el armado: «VER CORTE» o «VER DETALLE» («VER DET.» se
    escribe «VER DETALLE», R99): una de ``_REFERENCIAS``."""
    if not escrita:
        return None
    return "VER CORTE" if "CORTE" in escrita else "VER DETALLE"


def _juegos(m: re.Match[str]) -> list[JuegoEstribos]:
    """Los juegos de una cabeza leída; un juego mixto queda siempre estribo y luego grapa."""
    numero = m["num"]
    referencia = _referencia(m["ref"])

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


_PALABRA_RE = re.compile(r"[A-Z]+[.:]?")


def _letra_tras_palabra(vista: str, m: re.Match[str]) -> bool:
    """Una E o una G sola, separada de su «#» por un espacio o un salto de línea y con una palabra
    antes en su renglón («TIPO E #4@20», «EJE E» / «#4@20»): es una letra de esa palabra, no una
    cabeza de estribo (como «(TIPO E)», R24). Tras una pieza o una marca («4#3 E #2@20», «K-8 E
    #3@20») o sola en su renglón («E» / «#3@15», R28) sí es cabeza."""
    cabeza = "e" if m["e"] else "g" if m["g"] else None
    if cabeza is None or m["n1"] or m["eg"] or m["ge"] or len(m[cabeza]) != 1:
        return False
    if vista[m.end(cabeza) : m.end(cabeza) + 1] not in (" ", "|"):
        return False
    inicio_linea = vista.rfind("|", 0, m.start()) + 1
    antes = vista[inicio_linea : m.start()].split()
    return bool(antes) and antes[-1] != "Y" and _PALABRA_RE.fullmatch(antes[-1]) is not None


def _leer_estribos(vista: str, letrero: str) -> list[_Pieza]:
    """Los juegos de estribos como piezas; una separación fuera de rango avisa el juego entero.
    Una E o G que es la letra de una palabra (``_letra_tras_palabra``) no es un juego: lo que le
    sigue se lee o se avisa por su cuenta, nunca como estribo."""
    piezas = []
    for m in _ESTRIBOS_RE.finditer(vista):
        if _letra_tras_palabra(vista, m):
            continue
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
    delante: list[int | None], detras: list[int | None]
) -> tuple[Literal["delante", "detras"] | None, list[int | None]] | None:
    """De qué lado toma cada malla su marca de lecho, y cuál toma; ``None`` si el texto no lo
    deja claro.

    Una marca pegada delante de una malla y no detrás de otra dice «delante»; pegada detrás
    de una y no delante de otra, «detrás». Si el texto da las dos señales, o sólo marcas que
    dos mallas podrían reclamar, es ambiguo. Sin ninguna marca pegada, ninguna malla toma
    nada."""
    pegadas_delante = {k for k in delante if k is not None}
    pegadas_detras = {k for k in detras if k is not None}
    if not pegadas_delante and not pegadas_detras:
        return None, [None] * len(delante)
    solo_delante = pegadas_delante - pegadas_detras
    solo_detras = pegadas_detras - pegadas_delante
    if solo_delante and not solo_detras:
        return "delante", delante
    if solo_detras and not solo_delante:
        return "detras", detras
    return None


def _asignar_sentidos(
    delante: list[int | None], detras: list[int | None]
) -> list[int | None] | None:
    """Qué sentido toma cada malla, o ``None`` si el texto no lo deja claro.

    Cada sentido pegado es de una de las mallas que lo tienen al lado (la de detrás, que lo
    lleva delante, o la de delante, que lo lleva detrás) y cada malla lleva a lo más uno. El
    texto se lee sólo si hay una sola manera de repartirlos y es de una sola convención
    (todos delante o todos detrás): «A/S #4@20 A/S #3@20» se lee (el primero no puede llevar
    dos), «#4@20 A/S #3@20» no (el sentido es de cualquiera de las dos), «A/S #4@20 #3@20 EN
    Y» tampoco (mezcla las dos convenciones)."""
    opciones: dict[int, list[tuple[int, str]]] = {}
    for lado, pegados in (("delante", delante), ("detras", detras)):
        for i, k in enumerate(pegados):
            if k is not None:
                opciones.setdefault(k, []).append((i, lado))
    sentidos = sorted(opciones)
    lecturas: list[dict[int, tuple[int, str]]] = []

    def repartir(j: int, tomadas: dict[int, tuple[int, str]]) -> None:
        if len(lecturas) > 1:
            return
        if j == len(sentidos):
            lecturas.append(dict(tomadas))
            return
        for i, lado in opciones[sentidos[j]]:
            if i not in tomadas:
                tomadas[i] = (sentidos[j], lado)
                repartir(j + 1, tomadas)
                del tomadas[i]

    repartir(0, {})
    if len(lecturas) != 1 or len({lado for _, lado in lecturas[0].values()}) > 1:
        return None
    return [lecturas[0][i][0] if i in lecturas[0] else None for i in range(len(delante))]


def _grupos(vista: str, texto: str) -> list[re.Match[str]]:
    """Los grupos de varillas que la vista deja ver; lo que va pegado delante se mira en el
    texto real (un número ya leído también parte al siguiente)."""
    return [
        g
        for g in _VARILLAS_RE.finditer(vista)
        if g.start() == 0 or texto[g.start() - 1] not in _CIFRA_O_GATO
    ]


def _leer_mallas(vista: str, texto: str, letrero: str, familia: str) -> list[_Pieza]:
    """Las mallas del texto con su lecho y sus sentidos, como piezas.

    El lecho se escribe delante («LS #4@20 A/S LI #4@20 A/S») o detrás («#4@20 L.S. #3@20
    L.I.»), con una sola convención por texto. Los sentidos también («A/S #4@20 EN X #3@20»
    o «#4@20 A/S #3@20 EN X», detrás también solos en la línea siguiente), con su propia
    convención y sólo si se reparten de una sola manera (``_asignar_sentidos``): un sentido
    que dos mallas pueden reclamar, una malla con dos o una mezcla de convenciones es
    ambiguo. El sentido va siempre junto al cuerpo: delante, entre el lecho y la malla («LS
    A/S #4@20»); detrás, antes del lecho o, si el lecho va detrás, también después («#4@20
    A/S L.S.», «#4@20 L.S. A/S»).

    Una palabra de doble lecho («DOBLE PARRILLA», «DOBLEMENTE ARMADA», «AMBOS LECHOS», «2
    PARRILLAS», «2 LECHOS», «2 CAPAS») unida por contexto a una malla única y sola, delante
    de ella, la vuelve dos lechos; unida a mallas que ya dicen «LS» y «LI» concuerda y se
    consume. La que toca varillas o estribos es de ellos, que la avisan: junto a mallas «LS …
    LI …» la malla se la cede; junto a otra malla, la malla tampoco se lee. En cualquier otro
    caso ninguna malla se toma: cada una (con las marcas y palabras que tiene al lado) se
    avisa como lecho o sentido ambiguo, y una marca de lecho suelta como lecho sin su malla."""
    cuerpos = list(_MALLA_RE.finditer(vista))
    if not cuerpos:
        return []
    # Un cuerpo pegado a un número (aunque esté leído: «4#4@20», «#4@20#3@20») no es una
    # malla, pero lo que tiene al lado es suyo y no puede pasar a otra: cuenta como malla para
    # repartir lechos y sentidos, y se avisa entero.
    fantasmas = {
        i for i, m in enumerate(cuerpos) if m.start() > 0 and texto[m.start() - 1] in _CIFRA_O_GATO
    }
    marcas = list(_LECHO_RE.finditer(vista))
    sentidos = list(_SENTIDO_RE.finditer(vista))
    marca_que_acaba = {m.end(): k for k, m in enumerate(marcas)}
    marca_que_empieza = {m.start(): k for k, m in enumerate(marcas)}
    sentido_que_acaba = {s.end(): k for k, s in enumerate(sentidos)}
    sentido_que_empieza = {s.start(): k for k, s in enumerate(sentidos)}

    def atras(pos: int) -> int:  # salta los espacios hacia atrás, sin dejar la línea
        while pos > 0 and vista[pos - 1] == " ":
            pos -= 1
        return pos

    def adelante(pos: int) -> int:
        while pos < len(vista) and vista[pos] == " ":
            pos += 1
        return pos

    def sentido_antes(pos: int) -> int | None:  # separado por al menos un espacio
        p = atras(pos)
        return sentido_que_acaba.get(p) if p < pos else None

    def sentido_despues(pos: int) -> int | None:
        p = adelante(pos)
        return sentido_que_empieza.get(p) if p > pos else None

    def sentido_en_la_linea_siguiente(pos: int) -> int | None:
        """El sentido que es todo lo que trae la línea siguiente (a lo más con un punto)."""
        p = adelante(pos)
        if p >= len(vista) or vista[p] != "|":
            return None
        inicio = adelante(p + 1)
        k = sentido_que_empieza.get(inicio)
        if k is None:
            return None
        fin = vista.find("|", inicio)
        resto = vista[sentidos[k].end() : len(vista) if fin < 0 else fin].strip(" ")
        return k if resto in ("", ".") else None

    # 1. El lecho: la marca pegada a cada cuerpo, también a través de su sentido. Con marcas,
    #    cada malla lleva una y cada marca es de una malla; si una malla se queda sin lecho
    #    junto a otras que sí lo llevan, o sobra una marca, es ambiguo.
    marca_delante: list[int | None] = []
    marca_detras: list[int | None] = []
    for c in cuerpos:
        k = sentido_antes(c.start())
        marca_delante.append(
            marca_que_acaba.get(atras(sentidos[k].start() if k is not None else c.start()))
        )
        k = sentido_despues(c.end())
        marca_detras.append(
            marca_que_empieza.get(adelante(sentidos[k].end() if k is not None else c.end()))
        )
    ambiguo: str | None = None
    lado_marcas: Literal["delante", "detras"] | None = None
    usadas: list[int | None] = [None] * len(cuerpos)
    if marcas:
        convencion = _convencion(marca_delante, marca_detras)
        if (
            convencion is None
            or None in convencion[1]
            or set(convencion[1]) != set(range(len(marcas)))
        ):
            ambiguo = "lecho"
        else:
            lado_marcas, usadas = convencion

    # 2. Los sentidos, junto al cuerpo. Detrás, después de la marca de la malla sólo si el
    #    lecho va detrás (con el lecho delante, la marca que sigue es de la malla siguiente).
    sentido_delante = [sentido_antes(c.start()) for c in cuerpos]
    sentido_detras: list[int | None] = []
    for i, c in enumerate(cuerpos):
        fin = c.end()
        k = sentido_despues(fin)
        propia = marca_detras[i] if ambiguo else usadas[i] if lado_marcas == "detras" else None
        if k is None and propia is not None and marcas[propia].start() == adelante(fin):
            fin = marcas[propia].end()
            k = sentido_despues(fin)
        sentido_detras.append(k if k is not None else sentido_en_la_linea_siguiente(fin))
    reparto = _asignar_sentidos(sentido_delante, sentido_detras)
    usados: list[int | None] = [None] * len(cuerpos)
    if reparto is None:
        ambiguo = ambiguo or "sentido"
    else:
        usados = reparto

    # 3. El tramo de cada malla: con su lecho y su sentido o, si el texto es ambiguo, con
    #    todo lo que tiene pegado.
    tramos: list[tuple[int, int]] = []
    for i, c in enumerate(cuerpos):
        a, b = c.start(), c.end()
        if ambiguo:
            pegadas = [marcas[k] for k in (marca_delante[i], marca_detras[i]) if k is not None]
            pegadas += [
                sentidos[k] for k in (sentido_delante[i], sentido_detras[i]) if k is not None
            ]
        else:
            pegadas = [marcas[k] for k in (usadas[i],) if k is not None]
            pegadas += [sentidos[k] for k in (usados[i],) if k is not None]
        for m in pegadas:
            a, b = min(a, m.start()), max(b, m.end())
        tramos.append((a, b))
    lechos: list[list[Lecho]] = [_lechos(marcas[k]) if k is not None else ["unico"] for k in usadas]

    # 4. Cada palabra de doble lecho, atada por contexto a la malla que le sigue o, si no, a
    #    la que la precede. La que toca varillas o estribos es de ellos, salvo que sólo los
    #    alcance desde otra línea y su propia línea tenga la malla («4#8» / «2 PARRILLAS
    #    #4@20»: la palabra es de la malla).
    otras = [(g.start(), g.end()) for g in _grupos(vista, texto)]
    otras += [(m.start(), m.end()) for m in re.finditer(f"{CONSUMIDO}+", vista)]

    def misma_linea(a: int, b: int) -> bool:
        return "|" not in vista[min(a, b) : max(a, b)]

    def malla_atada(d: re.Match[str], delante: bool) -> int | None:
        if delante:
            k = next((k for k, (a, _) in enumerate(tramos) if a >= d.end()), None)
            return k if k is not None and atado(vista, d.end(), tramos[k][0]) else None
        k = next((k for k, (_, b) in reversed(list(enumerate(tramos))) if b <= d.start()), None)
        return k if k is not None and atado(vista, tramos[k][1], d.start()) else None

    def ajena(d: re.Match[str]) -> bool:
        tocadas = [
            a if a >= d.end() else b
            for a, b in otras
            if (a >= d.end() and atado(vista, d.end(), a))
            or (b <= d.start() and atado(vista, b, d.start()))
        ]
        if any(misma_linea(d.start(), borde) for borde in tocadas):
            return True
        mallas = [malla_atada(d, delante=True), malla_atada(d, delante=False)]
        return bool(tocadas) and not any(
            k is not None and misma_linea(d.start(), tramos[k][0]) for k in mallas
        )

    dobles: list[re.Match[str]] = []
    ajenas: list[re.Match[str]] = []
    for d in DOBLE_RE.finditer(vista):
        (ajenas if ajena(d) else dobles).append(d)
    delante_de: dict[int, list[re.Match[str]]] = {}
    detras_de: dict[int, list[re.Match[str]]] = {}
    for d in dobles:
        k = malla_atada(d, delante=True)
        if k is not None:
            delante_de.setdefault(k, []).append(d)
            continue
        k = malla_atada(d, delante=False)
        if k is not None:
            detras_de.setdefault(k, []).append(d)

    # 5. Qué hacen esas palabras: concuerdan con «LS … LI …» (y la de las varillas se cede),
    #    doblan una malla única y sola, o vuelven ambiguo el lecho de todas (también la de
    #    las varillas: la malla no sabe si era suya).
    extras: list[tuple[int, int]] = []
    cubiertos = {lecho for lista in lechos for lecho in lista}
    if (dobles or ajenas) and ambiguo is None:
        atadas = [d for lista in (*delante_de.values(), *detras_de.values()) for d in lista]
        if {"sup", "inf"} <= cubiertos:
            extras = [(d.start(), d.end()) for d in atadas]
        elif (
            len(tramos) == 1
            and lechos[0] == ["unico"]
            and len(dobles) == 1
            and not ajenas
            and 0 in delante_de
        ):
            tramos[0] = (dobles[0].start(), tramos[0][1])
            lechos[0] = ["sup", "inf"]
        else:
            ambiguo = "lecho"

    if ambiguo is not None:
        con_palabras = []
        for k, (a, b) in enumerate(tramos):
            for d in delante_de.get(k, []) + detras_de.get(k, []):
                a, b = min(a, d.start()), max(b, d.end())
            con_palabras.append((a, b))
        piezas = [
            _Pieza(
                a, b, malla=True, aviso=f"{ambiguo} ambiguo: «{letrero[a:b].strip()}»: no se toma"
            )
            for a, b in _unir(con_palabras)
        ]
        al_lado = {k for k in marca_delante + marca_detras if k is not None}
        for k, suelta in enumerate(marcas):
            if k not in al_lado:
                a, b = suelta.start(), suelta.end()
                aviso = f"lecho «{letrero[a:b].strip()}» sin su malla: no se toma"
                piezas.append(_Pieza(a, b, malla=True, aviso=aviso))
        return piezas

    piezas = []
    for i, (cuerpo, (a, b), lechos_de_malla, k) in enumerate(
        zip(cuerpos, tramos, lechos, usados, strict=True)
    ):
        cita = letrero[a:b].strip()
        if i in fantasmas:
            piezas.append(_Pieza(a, b, malla=True, aviso=f"sin leer: «{cita}»"))
            continue
        if familia not in FAMILIAS_CON_PARRILLA:
            aviso = f"malla «{cita}» en {_con_articulo(familia)}: no se toma"
            piezas.append(_Pieza(a, b, malla=True, aviso=aviso))
            continue
        if not _en_rango(float(cuerpo["sep"]), _RANGO_MALLAS):
            piezas.append(_Pieza(a, b, malla=True, aviso=f"separación fuera de rango: «{cita}»"))
            continue
        sentido: Literal["ambos", "x", "y"] | None = None
        if k is not None:
            sentido = "ambos" if sentidos[k]["ambos"] else _SENTIDO_XY[sentidos[k]["xy"]]
        parrillas = [
            Parrilla(
                numero=cuerpo["num"],
                separacion_m=_metros(cuerpo["sep"]),
                lecho=lecho,
                sentidos=sentido,
            )
            for lecho in lechos_de_malla
        ]
        piezas.append(_Pieza(a, b, malla=True, parrillas=parrillas))
    leidas = [i for i in range(len(piezas)) if i not in fantasmas]
    if leidas:
        piezas[leidas[0]].extras = extras
    # Una palabra de doble lecho entre mallas «LS … LI …» y unas varillas o estribos es de
    # ellos: la malla se la cede (no la ensucia) y ellos la avisan.
    if {"sup", "inf"} <= cubiertos:
        for d in ajenas:
            for k in (malla_atada(d, delante=True), malla_atada(d, delante=False)):
                if k is not None:
                    piezas[k].cedidas.append((d.start(), d.end()))
    return piezas


def _cabeza_en(vista: str, desde: int, hasta: int) -> int | None:
    """Dónde empieza la primera cabeza de estribo que nadie leyó entre ``desde`` y ``hasta``
    (ver ``_CABEZA_EN_LINEA_RE`` y ``_CABEZA_AL_INICIO_RE``), o ``None``."""
    inicios = []
    vieja = _CABEZA_EN_LINEA_RE.search(vista, desde, hasta)
    if vieja is not None:
        inicios.append(vieja.start())
    for m in _CABEZA_AL_INICIO_RE.finditer(vista, desde, hasta):
        ficha = m["cabeza"] + m["resto"]
        if _MARCA_SOLA_RE.fullmatch(ficha):
            continue  # una marca: «E-1», «(G-2)»
        if not m["abre"] and m["cabeza"] in ("E", "G") and m["resto"][:1] in (")", "]"):
            continue  # la letra que cierra el paréntesis de otra palabra: «(TIPO E)»
        inicios.append(m.start())
        break
    return min(inicios) if inicios else None


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
    cuenta suelta («4 #4@20»); delante de una malla, una palabra de lecho que no se leyó
    («A/SLI #3@20»), una cabeza de estribo o un sentido sin leer más atrás en la línea
    («ESTRIBOS DOBLES #3@15», «(ESTRIBOS) #3@15», «SENTIDO CORTO #4@20»), un sentido que la
    malla no tomó como suyo («EN X: #4@20», R27) o, si es la primera pieza de su renglón, una
    cabeza de estribo sin leer en el renglón de antes después de su última pieza («ESTRIBOS:» /
    «#3@15», R28); o una palabra que nadie tomó (de doble lecho, multiplicador, sentido) unida
    a la pieza por contexto. Si estorban varias, la que empieza antes."""
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
        patrones += [_LECHO_SUELTO_ANTES_RE, _SENTIDO_SUELTO_RE]
    estorbos = []
    for patron in patrones:
        estorbo = patron.search(vista, desde, p.inicio)
        if estorbo is not None:
            estorbos.append(estorbo.start())
    if p.malla:
        sentido = _SENTIDO_RE.search(vista, desde, p.inicio)
        if sentido is not None:  # R27, desde el principio de su ficha: «(EN X) #4@20»
            inicio = sentido.start()
            while inicio > desde and vista[inicio - 1] not in f" |{CONSUMIDO}":
                inicio -= 1
            estorbos.append(inicio)
        cabeza = _cabeza_en(vista, desde, p.inicio)
        if cabeza is not None:
            estorbos.append(cabeza)
        inicio_linea = texto.rfind("|", 0, p.inicio) + 1
        if inicio_linea > 0 and desde == inicio_linea:
            # R28: la primera pieza de su renglón, con una cabeza sin leer al final del de antes
            # (después de su última pieza): no se sabe si es una malla o los estribos de ella.
            previa = max(anterior.fin if anterior else 0, texto.rfind("|", 0, inicio_linea - 1) + 1)
            cabeza = _cabeza_en(vista, previa, inicio_linea - 1)
            if cabeza is not None:
                estorbos.append(cabeza)
    palabra: int | None = None
    for f in fichas(texto, desde, p.inicio, consumido):
        if f.tipo in ESTORBA:
            palabra = f.inicio
        elif f.tipo not in ATA and f.tipo != "consumido":
            palabra = None
    if palabra is not None:
        estorbos.append(palabra)
    return min(estorbos) if estorbos else None


def _sin_lo_cedido(
    vista: str, consumido: list[bool], cedidas: list[tuple[int, int]]
) -> tuple[str, list[bool]]:
    """La vista y lo consumido como los ve una pieza: lo que cedió a otra no la ensucia."""
    if not cedidas:
        return vista, consumido
    letras, tomado = list(vista), consumido.copy()
    for a, b in cedidas:
        for i in range(a, b):
            letras[i], tomado[i] = CONSUMIDO, True
    return "".join(letras), tomado


def _revisar(
    texto: str, vista: str, piezas: list[_Pieza], consumido: list[bool]
) -> tuple[list[_Pieza], list[tuple[int, int]]]:
    """Separa las piezas que se toman de los tramos que se avisan enteros.

    Una pieza no se toma, y se avisa con lo que la estorba, si:
    - toca a otra pieza sin espacio ni junta (se avisan las dos juntas: «#4@20 A/S#3@20»), o
      entre las dos hay algo que no es contexto (tampoco se sabe de cuál es: «4#3DALA E#2@20»),
      salvo que la pieza siguiente se lo haya cedido a ésta;
    - algo la estorba delante (``_estorbo_delante``);
    - lo que le sigue hasta la pieza siguiente o el fin de la línea no es contexto.
    Lo que una pieza cedió (``cedidas``) no la estorba a ella."""
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
        vista_p, consumido_p = _sin_lo_cedido(vista, consumido, p.cedidas)
        estorbo = _estorbo_delante(texto, vista_p, desde, p, anterior, consumido_p)
        if estorbo is not None:
            mala, inicio = True, min(inicio, estorbo)
        if not hueco_limpio(texto, p.fin, hasta, inicio_siguiente, consumido_p):
            mala, fin = True, max(fin, hasta)
            cedido_a_esta = (
                siguiente is not None
                and siguiente.cedidas
                and hueco_limpio(
                    texto,
                    p.fin,
                    hasta,
                    inicio_siguiente,
                    _sin_lo_cedido(vista, consumido, siguiente.cedidas)[1],
                )
            )
            if hasta == inicio_siguiente and not cedido_a_esta:
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


@dataclass
class _Piezas:
    """Lo que las tres pasadas reconocieron en un texto y lo que ``_revisar`` dejó tomar."""

    lineas: list[str]
    texto: str  # para leer: «Ø» escrito «#», las líneas unidas por « | »
    letrero: str  # para citar, de la misma longitud
    consumido: list[bool]
    buenas: list[_Pieza]
    malos: list[tuple[int, int]]
    grupos: list[re.Match[str]]  # los grupos de varillas reconocidos, se tomen o no
    reconocidas: list[_Pieza]  # toda pieza reconocida (juego, malla, grupo), se tome o no
    traducidas: list[tuple[int, int]]  # lo que ``normalizar`` escribió como «#n» (R87)
    ajenos: list[tuple[int, int]]  # lo que es de un objeto (R100): anclas, placas…


def _piezas(textos: list[str], familia: str) -> _Piezas:
    """Las pasadas 1 a 4 de ``parsear_armado``: reconocer las piezas y revisarlas."""
    lineas = [t.strip() for t in textos if t and t.strip()]
    pares = [(p, linea) for linea in lineas if (p := normalizar(linea))[0]]
    texto = " | ".join(leer for (leer, _), _l in pares)
    letrero = " | ".join(citar for (_, citar), _l in pares)
    traducidas: list[tuple[int, int]] = []
    desde = 0
    for (leer, _), linea in pares:
        traducidas += [(desde + a, desde + b) for a, b in traducciones(linea)]
        desde += len(leer) + 3
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
    grupos = _grupos(visible(), texto)
    for grupo in grupos:
        varilla = GrupoVarillas(
            cantidad=int(grupo["n"] or grupo["v"]),
            numero=grupo["num"],
            referencia=_referencia(grupo["ref"]),
        )
        tomar(_Pieza(grupo.start(), grupo.end(), varillas=[varilla]))

    # 4. Lo que es de un objeto (R100) queda fuera, con su palabra: no estorba a sus vecinas
    #    («30X30 8#6 E#3@20 PLACA BASE 35X35»: los estribos son de la columna).
    piezas.sort(key=lambda p: p.inicio)
    reconocidas = list(piezas)
    ajenos = _de_objetos(texto, reconocidas)
    for a, b in ajenos:
        for i in range(a, b):
            consumido[i] = True
    propias = [p for p in piezas if not any(a <= p.inicio and p.fin <= b for a, b in ajenos)]
    # 5. Cada pieza se toma entera o se avisa entera con lo que la estorba.
    buenas, malos = _revisar(texto, visible(), propias, consumido)
    return _Piezas(
        lineas, texto, letrero, consumido, buenas, malos, grupos, reconocidas, traducidas, ajenos
    )


# Una sección o las tres medidas de una pieza («15X20», «20 X 40 CMS», «15X20X40») y una longitud
# («L=8.00 M», «LONG. 8», «LONGITUD DE 12.00 M»): el parser las tiene por contexto (R91).
_SECCION_EN_TEXTO = re.compile(
    rf"(?<![\dxX×.]){LADO}\s*[xX×]\s*(?:\d{{1,3}}(?:\.\d+)?\s*[xX×]\s*)?{LADO_FINAL}"
    r"(?:\s*CMS?\.?)?"
)
_LONGITUD_EN_TEXTO = re.compile(
    r"\bL\s*=\s*\d+(?:[.,]\d+)?(?:\s*(?:M|MTS?|CMS?)\b)?"
    r"|\bLONG\.?\s*=?\s*\d+(?:[.,]\d+)?(?:\s*(?:M|MTS?)\b)?"
    r"|\bLONGITUD\b[^|\n]*?\d+(?:[.,]\d+)?\s*(?:M|MTS?|METROS)\b"
)
_INICIO_DE_FICHA = ' |:;,()="' + CONSUMIDO
_CUENTA_SUELTA = re.compile(r"\d{1,2}\s+")
_PREFIJO_SUELTO = re.compile(r"(?:^|[\s:;,()=\".\-/+&])[A-Z]{1,4}(?:\s*-\s*|\s+)$")


def tramos_de_armado(texto: str) -> tuple[str, list[tuple[int, int]]]:
    """``texto`` como lo cita el parser (``normalizar``) y los tramos que el parser reconoce como
    armado, se lean o se avisen (R91): cada juego de estribos, malla o grupo de varillas que
    reconoce (con las frases de R87: «4 VARS 3/8"», «N° 3», «8 PZAS #6»), cada sección y cada
    longitud. Sólo los que empiezan una ficha: el «7 #3» de «K-7 #3» o el «20X40» de «T2-20X40»
    van pegados a una marca y no son suyos. Sin cifras no hay armado y el parser no corre."""
    citar = normalizar(texto.strip())[1]
    if not re.search(r"\d", citar):
        return citar, []
    leida = _piezas([texto], "castillo")
    if len(leida.texto) != len(citar):  # «leer» y «citar» tienen siempre la misma longitud
        raise ValueError(f"el texto para leer y el de citar no miden lo mismo: «{texto}»")
    tramos = []
    for p in leida.reconocidas:
        inicio = p.inicio
        cuenta = _CUENTA_SUELTA.match(leida.texto, p.inicio)
        cabeza = cuenta is not None and leida.texto[cuenta.end() : cuenta.end() + 1].isalpha()
        if cuenta and cabeza and _PREFIJO_SUELTO.search(leida.texto, 0, p.inicio):
            # «K 7 E#3@1S», «TRABE T 1 E#3@1S»: la cifra tras unas letras sueltas puede ser el
            # número de una marca escrita con espacio; el juego empieza en su cabeza.
            inicio = cuenta.end()
        fin = p.fin
        destino = _PALABRAS_DE_PUNTERO.search(leida.texto, inicio, p.fin)
        if destino is not None:
            # La pieza se queda con su referencia, no con las marcas a las que remite (R110): ésas
            # quedan a la vista de la gramática de marcas y del respaldo.
            fin = destino.end()
        tramos.append((inicio, fin))
    tramos += [m.span() for m in _SECCION_EN_TEXTO.finditer(leida.texto)]
    tramos += [m.span() for m in _LONGITUD_EN_TEXTO.finditer(leida.texto)]
    enteros = []
    for a, b in tramos:
        for ta, tb in leida.traducidas:  # «3/8"» o «N° 3» van enteros
            if ta < b and a < tb:
                a, b = min(a, ta), max(b, tb)
        enteros.append((a, b))
    # Lo que empieza con «#» o «@» («#3@20», «@15») nunca se confunde con una marca: queda a la
    # vista (la E de «K-7-E #3@20» sigue siendo la cabeza de unos estribos).
    return citar, sorted(
        (a, b)
        for a, b in enteros
        if (a == 0 or citar[a - 1] in _INICIO_DE_FICHA) and citar[a : a + 1] not in ("#", "Ø", "@")
    )


def clase_de_tramo(tramo: str) -> Literal["seccion", "longitud", "pieza"]:
    """Qué es un tramo de ``tramos_de_armado`` (como lo cita el parser): una sección o las tres
    medidas de una pieza, una longitud, o una pieza que el parser reconoce (un grupo de varillas, un
    juego de estribos, una malla), que siempre se lee o se avisa. Una sección y una longitud son
    contexto para el parser: las lee (o no) quien lee el texto (R104)."""
    if _SECCION_EN_TEXTO.fullmatch(tramo.strip()):
        return "seccion"
    if _LONGITUD_EN_TEXTO.fullmatch(tramo.strip()):
        return "longitud"
    return "pieza"


def sin_armado(texto: str) -> str:
    """``texto`` como lo cita el parser con cada tramo de armado (``tramos_de_armado``) cambiado
    por ``CONSUMIDO`` (R68, R91): una cuenta de varillas, un juego de estribos, una sección o una
    longitud nunca son una marca («V4 #4», «P 4#3», «K 7 #3», «4 VARS 3/8"», «8 PZAS #6»)."""
    citar, tramos = tramos_de_armado(texto)
    letras = list(citar)
    for a, b in tramos:
        letras[a:b] = CONSUMIDO * (b - a)
    return "".join(letras)


def sin_cuentas_de_varillas(texto: str) -> str:
    """Lo mismo que ``sin_armado`` (el nombre de R68)."""
    return sin_armado(texto)


def _de_objetos(texto: str, piezas: list[_Pieza]) -> list[tuple[int, int]]:
    """Los tramos de ``texto`` que son de un objeto (R100, ``de_objetos``): sus fragmentos son las
    piezas que el parser reconoce y las secciones."""
    if OBJETO_AJENO_RE.search(texto) is None:
        return []
    fragmentos = [
        (p.inicio, p.fin, "malla" if p.malla else "varillas" if p.varillas else "estribos")
        for p in piezas
    ]
    fragmentos += [(*m.span(), "seccion") for m in _SECCION_EN_TEXTO.finditer(texto)]
    return de_objetos(texto, fragmentos)


def fragmentos_ajenos(texto: str) -> list[tuple[int, int]]:
    """Los tramos de ``texto`` que son de un objeto y no del elemento (R100): «PLACA BASE 35X35»,
    «ANCLAS 4 PZAS #6», «4 ANCLAS #6». Para que una sección de ellos no se tome como la del
    elemento (el parser los avisa)."""
    if not re.search(r"\d", texto) or OBJETO_AJENO_RE.search(texto) is None:
        return []
    corrido = len(texto) - len(texto.lstrip())
    return [(a + corrido, b + corrido) for a, b in _piezas([texto], "castillo").ajenos]


def tiene_armado(texto: str) -> bool:
    """Si el parser reconoce armado en ``texto``, se lea o se avise (R91): un juego de estribos,
    una malla o un grupo de varillas, también escrito con palabras o en pulgadas («4 VARS. N°
    3», «4 VARS 3/8"»). Un texto así es candidato a nota, tenga «#» o no."""
    if not re.search(r"\d", texto):
        return False
    return bool(_piezas([texto], "castillo").reconocidas)


_CON_GATO_RE = re.compile(r"#\s*(\d+(?:\.5)?)(?![\d.])|@\s*\d")


def _con_gato(texto: str) -> bool:
    """Si ``texto`` (como lo lee el parser) trae una varilla que existe («#3», también escrita
    «Ø3» o «No. 3») o una separación («@20»). «TABLA No. 1» no: no hay varilla del #1."""
    return any(m[1] is None or m[1] in NUMEROS for m in _CON_GATO_RE.finditer(texto))


# R107: un armado prefabricado (electrosoldado): no es una familia ni varillas que se lean.
_ARMEX_RE = re.compile(r"(?<![A-Z])ARMEX(?![A-Z])")
ARMEX_RE = _ARMEX_RE


def lo_ve_el_parser(texto: str) -> bool:
    """Si el parser lee o avisa algo de armado en ``texto`` (R108): un tramo de
    ``tramos_de_armado`` (una sección, una longitud), una pieza que reconoce, se lea o se avise
    (una malla suelta «#3@20» también), o un aviso que cita una varilla que existe o una
    separación («V#3 @15 CMS AMBOS SENTIDOS», «3.- @20», «… VARILLA ADICIONAL #3»). Otra cifra sin
    armado («NPT +3.50», «ESC 1:50», «TABLA No. 1») no: el parser la avisa, pero no es armado."""
    if not re.search(r"\d", texto):
        return False
    if tramos_de_armado(texto)[1] or _piezas([texto], "castillo").reconocidas:
        return True
    if not _con_gato(normalizar(texto)[0]):
        return False
    return any(
        _con_gato(normalizar(cita)[0])
        for aviso in parsear_armado([texto], "castillo").avisos
        for cita in re.findall(r"«([^»]*)»", aviso)
    )


def parsear_armado(textos: list[str], familia: str) -> Armado:
    """Lee los textos de un armado (en orden, uno por línea) para un elemento de ``familia``.

    Tres pasadas reconocen piezas, en este orden: juegos de estribos (con sus zonas, que
    pueden seguir en la línea siguiente, y su «VER CORTE»), mallas con su lecho y sentidos
    (sólo en ``FAMILIAS_CON_PARRILLA``; en otra familia se avisan) y grupos de varillas. Cada
    pieza se revisa contra lo que la rodea en el texto real (``_revisar``): se lee entera o
    se avisa entera, nunca a medias. Al final, todo lo que nadie leyó y no es contexto se
    avisa (``residuo``). Los avisos citan el texto como lo escribió el plano (en mayúsculas)."""
    leida = _piezas(textos, familia)
    lineas, texto, letrero = leida.lineas, leida.texto, leida.letrero
    consumido, buenas, malos = leida.consumido, leida.buenas, leida.malos
    avisos: list[tuple[int, str]] = []

    def entero(a: int, b: int) -> tuple[int, int]:
        """Un tramo que toca algo que ``normalizar`` escribió como «#n» lo cita entero (R92)."""
        for ta, tb in leida.traducidas:
            if ta < b and a < tb:
                a, b = min(a, ta), max(b, tb)
        return a, b

    armado = Armado(texto_original=" | ".join(lineas))
    # R100: lo que es de un objeto (anclas, pernos, placas…), con su palabra: se avisa entero y
    # nada de él se lee; lo demás del texto, sí.
    ajenos = [entero(a, b) for a, b in leida.ajenos]
    for a, b in ajenos:
        avisos.append((a, f"«{letrero[a:b].strip()}»: no es armado del elemento"))
        for i in range(a, b):
            consumido[i] = True

    def sin_lo_ajeno(a: int, b: int) -> list[tuple[int, int]]:
        """El tramo ``a:b`` sin lo que es de un objeto (ya avisado): los pedazos con cifras (lo
        que queda entre dos objetos, «CON», es sólo contexto)."""
        tramos = [(a, b)]
        for oa, ob in ajenos:
            tramos = [
                t for x, y in tramos for t in ((x, min(y, oa)), (max(x, ob), y)) if t[0] < t[1]
            ]
        return [(x, y) for x, y in tramos if re.search(r"[\d#@Ø]", letrero[x:y])]

    for p in buenas:
        if p.aviso is not None:
            avisos.append((p.inicio, p.aviso))
        armado.estribos += p.estribos
        armado.parrillas += p.parrillas
        armado.longitudinales += p.varillas
    for mala in malos:
        for a, b in sin_lo_ajeno(*entero(*mala)):
            avisos.append((a, _aviso_sin_leer(letrero[a:b].strip())))
            for i in range(a, b):
                consumido[i] = True

    # R107: ARMEX es armado prefabricado: ni varillas ni estribos que el parser lea; se avisa.
    for m in _ARMEX_RE.finditer(texto):
        if not any(consumido[m.start() : m.end()]):
            avisos.append(
                (m.start(), f"armado prefabricado «{letrero[m.start() : m.end()]}»: no se lee")
            )
            for i in range(m.start(), m.end()):
                consumido[i] = True

    # 5. Lo que nadie leyó: si no es contexto, se avisa.
    for a, b, tipo in residuo(texto, consumido):
        a, b = entero(a, b)
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
    """«4#5+2#4»; un grupo con referencia la lleva detrás («4#3 VER DETALLE», R102), y el grupo
    siguiente va tras un espacio."""
    texto = ""
    for i, g in enumerate(a.longitudinales):
        if i:
            texto += " " if a.longitudinales[i - 1].referencia is not None else "+"
        texto += f"{_cuenta(g.cantidad)}#{_numero(g.numero)}"
        if g.referencia is not None:
            if g.referencia not in _REFERENCIAS:
                raise ValueError(f"referencia «{g.referencia}»: el texto no la puede llevar")
            texto += f" {g.referencia}"
    return texto


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

    Siempre con el lecho delante y los sentidos detrás. Sin lecho, una malla con sentido se
    separa de la siguiente con una coma («#4@20 A/S, #3@15»): pegado a las dos, el sentido
    podría ser de cualquiera. Mallas con lecho y mallas sin lecho no se pueden escribir
    juntas (el texto no diría a cuál va cada lecho): ValueError."""
    if len({p.lecho == "unico" for p in a.parrillas}) > 1:
        raise ValueError("mallas con lecho y sin lecho juntas: el texto no las distingue")
    lechos = {"sup": "LS ", "inf": "LI ", "unico": ""}
    sentidos = {"ambos": " A/S", "x": " EN X", "y": " EN Y", None: ""}
    texto = ""
    for i, p in enumerate(a.parrillas):
        if i:
            anterior = a.parrillas[i - 1]
            texto += ", " if anterior.lecho == "unico" and anterior.sentidos else " "
        texto += f"{lechos[p.lecho]}#{_numero(p.numero)}@{_cm(p.separacion_m, _RANGO_MALLAS)}"
        texto += sentidos[p.sentidos]
    return texto


def texto_armado(a: Armado) -> str:
    """Longitudinales, estribos y parrillas, separados por un espacio."""
    return " ".join(
        parte for parte in (texto_longitudinal(a), texto_estribos(a), texto_parrillas(a)) if parte
    )
