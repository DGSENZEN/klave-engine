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
# Las expresiones sólo reconocen piezas; si lo que sigue a una pieza la deja a medias lo
# decide la revisión de huecos (``_revisar``), no un lookahead.

# Un número de varilla mexicano («#25», «#3/8» o «#12 MM» se leen hasta donde dan y el
# hueco que sigue los avisa enteros).
_NUM = "(?:" + "|".join(re.escape(n) for n in sorted(NUMEROS, key=len, reverse=True)) + ")"
_SEP = r"[1-9]\d{0,2}(?:\.\d{1,2})?"  # cm, de 1 a 999.99
_CM = r"(?:\s?CMS?\.?)?"  # la unidad, pegada a la separación
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

# La cantidad de un juego no puede ser el número de la varilla anterior («4#3 E#2@15») ni
# parte de una medida («15X30 E#2@20»): no la precede una letra, un dígito, «#» o «.».
# «nE+mG» y «nG+mE» son el mismo juego de estribos y grapas.
_ESTRIBOS_RE = re.compile(
    r"(?<![A-Z0-9#.])(?<!#\s)"
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
    rf"(?:\s*(?:EN\s+)?(?P<ambos>{_AMBOS})(?![A-Z0-9])"
    r"|\s+(?:EN|SENTIDO)\s+(?P<xy>[XY])(?![A-Z0-9]))?"
)
_LECHO_RE = re.compile(
    rf"(?<![A-Z.])(?:EN\s+)?(?P<l1>{_LS}|{_LI})"
    rf"(?:\s*(?:Y|E|,|\+)\s*(?P<l2>{_LS}|{_LI}))?(?![A-Z.])"
    rf"(?:\s*(?P<ambos>{_AMBOS})(?![A-Z0-9]))?"
)
_ES_LS = re.compile(_LS)
_SENTIDO_XY: dict[str, Literal["x", "y"]] = {"X": "x", "Y": "y"}

_VARILLAS_RE = re.compile(
    rf"(?<![\d.#])(?P<n>{_CUENTA})\s*(?:VARILLAS|VARS?\.?|V)?\s*#\s*(?P<num>{_NUM})(?!\s*@)"
)

# Lo único que puede ir entre una pieza y la siguiente (o el fin de la línea) sin que la
# pieza quede a medias: medidas, espesores, sentidos, referencias y palabras de familia.
_PALABRAS = (
    r"(?:DALAS?|CADENAS?|CASTILLOS?|COLUMNAS?|CONTRATRABES?|TRABES?|LOSAS?|MUROS?|ZAPATAS?"
    r"|DADOS?|PILOTES?|CERRAMIENTOS?|ARMEX|REFUERZO)"
)
_CONTEXTO_RE = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)?\s*[X×]\s*\d+(?:\.\d+)?(?![\w.])"
    r"|(?<![\w.])H\s*=\s*\d+(?:\.\d+)?(?![\w.])"
    rf"|(?<![A-Z]){_AMBOS}(?![A-Z0-9])"
    r"|(?<![A-Z])EN\s+[XY](?![A-Z0-9])"
    r"|(?<![A-Z])VER\s+(?:CORTE|DETALLE)(?![A-Z])"
    rf"|(?<![A-Z]){_PALABRAS}(?![A-Z])"
)
_JUNTAS = (",", "+", "Y")  # una sola, y sólo justo antes de la pieza siguiente
# Una cuenta suelta delante de una pieza la deja a medias: «4 », «4 VARS », «4 VARILLAS DE »,
# «4 PZAS », «(4) », «4-», «4VARS ». Una medida no («15X30 », «H=20 »).
_CUENTA_ANTES_RE = re.compile(
    r"(?<![\w.=])(?<!=\s)(?:\(\s*\d+\s*\)|\d+)"
    r"\s*(?:-|(?:VARILLAS?|VARS?\.?|V|PZAS?\.?|PIEZAS?)(?:\s+DEL?)?)?\s*$"
)
# Una cabeza de estribo que no se leyó delante de una malla («ESTRIBOS: #3@20»).
_CABEZA_ANTES_RE = re.compile(
    r"(?<![\w.])\d*(?:E|EST|ESTR|ESTRIBOS?|G|GRAPAS?|LIGAS?|EYG)[.:,]?(?:\s+DEL?)?\s*$"
)
_PEGADO_RE = re.compile(r"[^ ]*$")
# Una línea que empieza con «/», «,», «-» o «+» sigue a la anterior.
_SIGUE_LINEA_RE = re.compile(r"\|\s*[/,\-+]")

_NUMERO_EN_TOKEN_RE = re.compile(r"[#Ø]\s*(\d+(?:\.\d+)?)")
_MM_DESPUES_RE = re.compile(r"\s?MM(?![A-Z])")
_FEMENINAS = frozenset(
    {"columna", "trabe", "contratrabe", "dala", "cadena", "losa", "zapata", "pila", "viga"}
)
_CONSUMIDO = "\x00"
_DELIMITADORES = " |" + _CONSUMIDO
_ALCANCE_TOKEN = 24


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


def _leer_mallas(vista: str, letrero: str, familia: str) -> list[_Pieza]:
    """Las mallas del texto con su lecho, como piezas.

    El lecho se escribe delante («LS #4@20 A/S LI #4@20 A/S») o detrás («#4@20 L.S. #3@20
    L.I.»), con una sola convención por texto. Si no queda claro qué lecho va con qué malla
    ninguna malla se toma: cada una (con las marcas que tiene al lado) se avisa como lecho
    ambiguo, y una marca suelta como lecho sin su malla."""
    mallas = list(_MALLA_RE.finditer(vista))
    if not mallas:
        return []
    marcas = list(_LECHO_RE.finditer(vista))

    def junto(a: int, b: int) -> bool:  # sólo espacios entre a y b, en la misma línea
        return a <= b and vista[a:b].strip(" ") == ""

    def marca_delante(malla: re.Match[str]) -> int | None:
        return next((k for k, m in enumerate(marcas) if junto(m.end(), malla.start())), None)

    def marca_detras(malla: re.Match[str]) -> int | None:
        return next((k for k, m in enumerate(marcas) if junto(malla.end(), m.start())), None)

    delante = [marca_delante(m) for m in mallas]
    detras = [marca_detras(m) for m in mallas]
    usadas = [None] * len(mallas) if not marcas else _convencion(delante, detras, len(marcas))

    if usadas is None:
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
    for malla, k in zip(mallas, usadas, strict=True):
        marca = marcas[k] if k is not None else None
        a = min(malla.start(), marca.start()) if marca else malla.start()
        b = max(malla.end(), marca.end()) if marca else malla.end()
        if familia not in FAMILIAS_CON_PARRILLA:
            aviso = f"malla «{letrero[a:b].strip()}» en {_con_articulo(familia)}: no se toma"
            piezas.append(_Pieza(a, b, malla=True, aviso=aviso))
            continue
        sentidos: Literal["ambos", "x", "y"] | None = (
            "ambos"
            if malla["ambos"] or (marca and marca["ambos"])
            else _SENTIDO_XY.get(malla["xy"] or "")
        )
        parrillas = [
            Parrilla(
                numero=malla["num"],
                separacion_m=_metros(malla["sep"]),
                lecho=lecho,
                sentidos=sentidos,
            )
            for lecho in _lechos(marca)
        ]
        piezas.append(_Pieza(a, b, malla=True, parrillas=parrillas))
    return piezas


def _hueco_limpio(hueco: str, sigue_pieza: bool) -> bool:
    """Lo que hay entre una pieza y la siguiente (o el fin de la línea) es sólo contexto."""
    resto = _CONTEXTO_RE.sub(" ", hueco.replace("|", " ")).strip()
    return resto == "" or (sigue_pieza and resto in _JUNTAS)


def _revisar(texto: str, piezas: list[_Pieza]) -> tuple[list[_Pieza], list[tuple[int, int]]]:
    """Separa las piezas que se toman de los tramos que se avisan enteros.

    Una pieza no se toma (y se avisa con lo que la estorba) si va pegada a algo que no sea
    una sola junta («,», «+») tras la pieza anterior («K-2#4», «H=202E+1G#3»), si la
    precede una cuenta suelta (o, a una malla, una cabeza de estribo que no se leyó), o si
    lo que le sigue hasta la pieza siguiente o el fin de la línea no es contexto. Una línea
    que empieza con «/», «,», «-» o «+» cuenta como continuación de la anterior."""
    buenas: list[_Pieza] = []
    malos: list[tuple[int, int]] = []
    for i, p in enumerate(piezas):
        fin_anterior = piezas[i - 1].fin if i else 0
        inicio_siguiente = piezas[i + 1].inicio if i + 1 < len(piezas) else len(texto)
        inicio_linea = texto.rfind("|", 0, p.inicio) + 1
        desde = max(fin_anterior, inicio_linea)
        fin_linea = texto.find("|", p.fin)
        fin_linea = len(texto) if fin_linea < 0 else fin_linea
        while fin_linea < inicio_siguiente and _SIGUE_LINEA_RE.match(texto, fin_linea):
            otro = texto.find("|", fin_linea + 1)
            fin_linea = len(texto) if otro < 0 else otro
        hasta = min(inicio_siguiente, fin_linea)
        antes = texto[desde : p.inicio]

        inicio, fin, mala = p.inicio, p.fin, False
        pegado = _PEGADO_RE.search(antes)  # lo que va junto a la pieza, sin espacio
        if pegado is not None and pegado.group() not in ("", ",", "+"):
            mala, inicio = True, desde + pegado.start()
        elif (cuenta := _CUENTA_ANTES_RE.search(antes)) is not None or (
            p.malla and (cuenta := _CABEZA_ANTES_RE.search(antes)) is not None
        ):
            mala, inicio = True, desde + cuenta.start()
        if not _hueco_limpio(texto[p.fin : hasta], sigue_pieza=hasta == inicio_siguiente):
            mala, fin = True, hasta
        if mala:
            malos.append((inicio, fin))
        else:
            buenas.append(p)
    return buenas, _unir(malos)


def _token(vista: str, i: int) -> tuple[int, int]:
    """El pedazo sin leer alrededor de la posición ``i``: hasta un espacio, un salto de
    línea o algo ya leído (con un tope a cada lado). Un ``#`` o ``@`` suelto se lleva el
    número que le sigue («@ 20»), y unos milímetros detrás también se avisan («#12 MM»)."""
    a = i
    while a > 0 and vista[a - 1] not in _DELIMITADORES and i - a < _ALCANCE_TOKEN:
        a -= 1
    b = i + 1
    while True:
        while b < len(vista) and vista[b] not in _DELIMITADORES and b - i < _ALCANCE_TOKEN:
            b += 1
        numero_detras = b + 1 < len(vista) and vista[b] == " " and vista[b + 1].isdigit()
        if numero_detras and vista[b - 1] in "#@":
            b += 1
            continue
        if (mm := _MM_DESPUES_RE.match(vista, b)) is not None:
            b = mm.end()
        return a, b


def _aviso_sin_leer(cita: str) -> str:
    for m in _NUMERO_EN_TOKEN_RE.finditer(cita):
        if m.group(1) not in NUMEROS:
            return f"sin leer: «{cita}»: no hay varilla del #{m.group(1)}"
    return f"sin leer: «{cita}»"


def parsear_armado(textos: list[str], familia: str) -> Armado:
    """Lee los textos de un armado (en orden, uno por línea) para un elemento de ``familia``.

    Tres pasadas reconocen piezas, en este orden: juegos de estribos (con sus zonas, que
    pueden seguir en la línea siguiente, y su «VER CORTE»), mallas con su lecho (sólo en
    ``FAMILIAS_CON_PARRILLA``; en otra familia se avisan) y grupos de varillas. Después cada
    pieza se revisa contra lo que la rodea (``_revisar``): se lee entera o se avisa entera,
    nunca a medias. Al final todo ``#`` o ``@`` que nadie leyó se avisa con su pedazo. Los
    avisos citan el texto como lo escribió el plano (en mayúsculas)."""
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
    for malla in _leer_mallas(visible(), letrero, familia):
        tomar(malla)
    # 3. Grupos de varillas: todos, no sólo el primero («4#5+2#4» son dos).
    for grupo in _VARILLAS_RE.finditer(visible()):
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

    # 5. Lo que quedó: cada «#» o «@» sin leer se avisa con su pedazo, una vez por pedazo.
    vista = visible()
    avisado = [False] * len(texto)
    for i, c in enumerate(vista):
        if c in "#@" and not avisado[i]:
            a, b = _token(vista, i)
            for k in range(a, b):
                avisado[k] = True
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
