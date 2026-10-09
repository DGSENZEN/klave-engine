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
from collections.abc import Callable
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

# Lo que no puede seguirle a un número leído sin que el número quede a medias: otra cifra,
# una fracción («#3/8», «@12/14»), un decimal que no se leyó («#3.5») o milímetros.
_MM = r"\s?MM(?![A-Z])"
# Un número de varilla mexicano y nada más: «#3/8» (pulgadas), «#3.5», «#25» o «Ø12 MM»
# no son un número de la tabla y se avisan en vez de leerse a medias.
_NUM = (
    "(?:"
    + "|".join(re.escape(n) for n in sorted(NUMEROS, key=len, reverse=True))
    + rf")(?![\d/]|\.\d)(?!{_MM})"
)
# Una separación en cm (de 1 a 999.99), con «CM» opcional. No puede seguirle una letra, una
# cifra, «/», un decimal sin leer, «,n» o «-n» (otra separación: «@15,20», «@6,8@10») ni
# milímetros; sí «,» y lo que sigue cuando es otra pieza («,4#3», «, 4 VARS #3», «,2G#3»).
# Si algo así le sigue, el pedazo se avisa entero.
_SEP = r"[1-9]\d{0,2}(?:\.\d{1,2})?"
_OTRA_PIEZA = r"[1-9]\d?\s*(?:(?:VARILLAS|VARS?\.?|V)?\s*#|E|G|LIGA)"
_FIN_SEP = rf"(?:\s?CMS?\.?)?(?![A-Z0-9/]|\.\d)(?![,\-]\s?(?!{_OTRA_PIEZA})\d)(?!{_MM})"
# Opcionalmente a través del salto de línea: «2E#3EXT@10» / «CENTRO@20» son un solo juego.
_LINEA = r"(?:\s*\|)?\s*"
_LS = r"(?:LS|L\.S\.?|LECHO\s+SUP\w*\.?)"
_LI = r"(?:LI|L\.I\.?|LECHO\s+INF\w*\.?)"
_AMBOS = r"(?:A\s*/\s*S|A\.?S\.?|AMBOS\s+SENTIDOS|AMBAS\s+DIRECCIONES)"
_CUENTA = r"[1-9]\d?"  # piezas o varillas: de 1 a 99
_E = r"E(?:ST(?:RIBOS?|\.)?|\.)?"
_G = r"G(?:RAPAS?|\.)?"

# La cantidad de un juego no puede ser el número de la varilla anterior («4#3 E#2@15») ni
# parte de una medida («15X30 E#2@20»): no la precede una letra, un dígito, «#» o «.».
# «nE+mG» y «nG+mE» son el mismo juego de estribos y grapas.
_ESTRIBOS_RE = re.compile(
    r"(?<![A-Z0-9#.])(?<!#\s)"
    rf"(?:(?P<n1>{_CUENTA})\s*)?"
    r"(?:"
    rf"(?P<e>{_E})(?:\s*(?:Y|\+)\s*(?:(?P<n2>{_CUENTA})\s*)?(?P<eg>{_G}))?"
    rf"|(?P<g>{_G})(?:\s*(?:Y|\+)\s*(?:(?P<n3>{_CUENTA})\s*)?(?P<ge>{_E}))?"
    r"|(?P<l>LIGAS?)"
    r")"
    r"(?:\s+DEL?)?"
    rf"\s*#\s*(?P<num>{_NUM})"
    r"(?:"
    rf"{_LINEA}EXT(?:REMOS?)?\.?\s*@\s*(?P<ext>{_SEP}){_FIN_SEP}"
    rf"(?:{_LINEA}(?:Y\s+)?CENTRO\s*@\s*(?P<centro>{_SEP}){_FIN_SEP})?"
    rf"|{_LINEA}@\s*(?P<sep>{_SEP}){_FIN_SEP}"
    r")?"
    rf"(?:{_LINEA}(?P<ref>VER\s+(?:CORTE|DETALLE)))?"
)

# El cuerpo de una malla; su lecho («LS», «L.I.», «LECHO SUPERIOR») va aparte, delante o detrás.
_MALLA_RE = re.compile(
    rf"#\s*(?P<num>{_NUM})\s*@\s*(?P<sep>{_SEP}){_FIN_SEP}"
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
# Lo que, delante de una malla, dice que no es una malla: una cuenta («4 #4@20»), una cuenta
# con su palabra («4 VARS #4@20») o una cabeza de estribo que no se leyó («ESTRIBOS: #3@20»).
_PIEZA_CUENTA_RE = re.compile(r"\d+")
_PIEZA_VARILLAS_RE = re.compile(r"VARILLAS|VARS?\.?|V")
_PIEZA_CABEZA_RE = re.compile(r"\d*(?:E|EST|ESTR|ESTRIBOS?|G|GRAPAS?|LIGAS?|EYG)[.:,]?")

# Un grupo no lleva nada pegado detrás: ni «@» (eso es una separación) ni letras («2#5X150»
# dice además una longitud que este armado no guarda; se avisa entero).
_VARILLAS_RE = re.compile(
    rf"(?<![\d.#])(?P<n>{_CUENTA})\s*(?:VARILLAS|VARS?\.?|V)?\s*#\s*(?P<num>{_NUM})"
    r"(?![A-Z])(?!\s*@)"
)

_NUMERO_EN_TOKEN_RE = re.compile(r"#\s*(\d+(?:\.\d+)?)")
_MM_DESPUES_RE = re.compile(_MM)
_FEMENINAS = frozenset(
    {"columna", "trabe", "contratrabe", "dala", "cadena", "losa", "zapata", "pila", "viga"}
)
_CONSUMIDO = "\x00"
_DELIMITADORES = " |" + _CONSUMIDO
_ALCANCE_TOKEN = 24


# ------------------------------------------------------------------ lectura


def _normalizar(texto: str) -> str:
    t = texto.upper().replace("%%%", "%").replace("%%C", "#").replace("Ø", "#")
    t = t.replace("⌀", "#").replace("\\P", " | ")
    return re.sub(r"\s+", " ", t).strip()


def _metros(cm: str) -> float:
    return float(cm) / 100


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

    def juego(tipo: Literal["estribo", "grapa", "liga"], cantidad: str | None) -> JuegoEstribos:
        return JuegoEstribos(
            tipo=tipo,
            cantidad=int(cantidad) if cantidad else 1,
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


def _inicio_pieza(vista: str, fin: int) -> int:
    """Dónde empieza el pedazo que termina en ``fin`` (hasta un espacio, un salto de línea o
    algo ya leído)."""
    a = fin
    while a > 0 and vista[a - 1] not in _DELIMITADORES:
        a -= 1
    return a


def _pieza_previa(vista: str, fin: int) -> tuple[int, str]:
    """El pedazo anterior a ``fin``, saltando espacios: (inicio, texto)."""
    while fin > 0 and vista[fin - 1] == " ":
        fin -= 1
    inicio = _inicio_pieza(vista, fin)
    return inicio, vista[inicio:fin]


def _estorbo_de_malla(vista: str, h: int) -> int | None:
    """Si lo que va delante de una malla (de su ``#``, o de su lecho cuando va delante) dice
    que no es una malla, dónde empieza, para avisar el pedazo entero; ``None`` si nada la
    estorba. Estorba lo pegado («4#4@20», «X#4@20», «4LS #4@20»), una cuenta suelta
    («4 #4@20», «4 LS #4@20»), una cuenta con su palabra («4 VARS #4@20») y una cabeza de
    estribo («ESTRIBOS: #3@20»). Una medida («15X30», «H=20») no estorba: es contexto."""
    if h > 0 and (vista[h - 1].isalnum() or vista[h - 1] == "."):
        return _inicio_pieza(vista, h)
    inicio, pieza = _pieza_previa(vista, h)
    if _PIEZA_CUENTA_RE.fullmatch(pieza) or _PIEZA_CABEZA_RE.fullmatch(pieza):
        return inicio
    if _PIEZA_VARILLAS_RE.fullmatch(pieza) or pieza in ("DE", "DEL"):
        inicio_previo, previa = _pieza_previa(vista, inicio)
        cuenta = pieza not in ("DE", "DEL") and _PIEZA_CUENTA_RE.fullmatch(previa)
        cabeza = pieza in ("DE", "DEL") and _PIEZA_CABEZA_RE.fullmatch(previa)
        if cuenta or cabeza:
            return inicio_previo
    return None


def _token(vista: str, i: int) -> tuple[int, int]:
    """El pedazo sin leer alrededor de la posición ``i``: hasta un espacio, un salto de
    línea o algo ya leído (con un tope a cada lado). Un ``#`` o ``@`` suelto se lleva el
    pedazo que le sigue («@ 20»), y unos milímetros detrás también se avisan («#12 MM»)."""
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


def _aviso_sin_leer(token: str) -> str:
    for m in _NUMERO_EN_TOKEN_RE.finditer(token):
        if m.group(1) not in NUMEROS:
            return f"sin leer: «{token}»: no hay varilla del #{m.group(1)}"
    return f"sin leer: «{token}»"


def _lechos(marca: re.Match[str] | None) -> list[Literal["sup", "inf", "unico"]]:
    """Los lechos que dice una marca («L.S. Y L.I.» son dos); sin marca, único."""
    if marca is None:
        return ["unico"]
    return [
        "sup" if _ES_LS.fullmatch(lecho) else "inf" for lecho in (marca["l1"], marca["l2"]) if lecho
    ]


def parsear_armado(textos: list[str], familia: str) -> Armado:
    """Lee los textos de un armado (en orden, uno por línea) para un elemento de ``familia``.

    Consume, en este orden: juegos de estribos (con sus zonas, que pueden seguir en la línea
    siguiente, y su «VER CORTE»), mallas con su lecho (sólo en ``FAMILIAS_CON_PARRILLA``; en
    otra familia se avisan) y grupos de varillas. Todo ``#`` o ``@`` que quede sin consumir se
    avisa con el pedazo de texto que lo rodea: un número se lee entero o se avisa, nunca a
    medias. Secciones, palabras de familia, «H=», «REFUERZO» y comas son contexto."""
    lineas = [t.strip() for t in textos if t and t.strip()]
    texto = " | ".join(n for n in (_normalizar(t) for t in lineas) if n)
    consumido = [False] * len(texto)
    avisos: list[tuple[int, str]] = []

    def visible() -> str:
        return "".join(_CONSUMIDO if consumido[i] else c for i, c in enumerate(texto))

    def consumir(a: int, b: int) -> None:
        for i in range(a, b):
            consumido[i] = True

    # 1. Juegos de estribos: «EYG#3@15» es estribo y grapa, nunca una malla.
    estribos: list[JuegoEstribos] = []
    for leido in _ESTRIBOS_RE.finditer(visible()):
        estribos += _juegos(leido)
        consumir(leido.start(), leido.end())

    # 2. Mallas, sólo donde van.
    parrillas = _leer_mallas(visible(), texto, familia, consumir, avisos)

    # 3. Grupos de varillas: todos, no sólo el primero («4#5+2#4» son dos).
    longitudinales: list[GrupoVarillas] = []
    for grupo in _VARILLAS_RE.finditer(visible()):
        longitudinales.append(GrupoVarillas(cantidad=int(grupo["n"]), numero=grupo["num"]))
        consumir(grupo.start(), grupo.end())

    # 4. Lo que quedó: cada «#» o «@» sin leer se avisa con su pedazo, una vez por pedazo.
    vista = visible()
    avisado = [False] * len(texto)
    for i, c in enumerate(vista):
        if c in "#@" and not avisado[i]:
            a, b = _token(vista, i)
            for k in range(a, b):
                avisado[k] = True
            avisos.append((a, _aviso_sin_leer(vista[a:b].strip(",;:"))))

    return Armado(
        longitudinales=longitudinales,
        estribos=estribos,
        parrillas=parrillas,
        texto_original=" | ".join(lineas),
        avisos=[aviso for _, aviso in sorted(avisos, key=lambda par: par[0])],
    )


def _leer_mallas(
    vista: str,
    texto: str,
    familia: str,
    consumir: Callable[[int, int], None],
    avisos: list[tuple[int, str]],
) -> list[Parrilla]:
    """Las mallas del texto con su lecho.

    El lecho se escribe delante («LS #4@20 A/S LI #4@20 A/S») o detrás («#4@20 L.S. #3@20
    L.I.»), y un mismo texto usa una sola convención: la decide la primera malla (delante si
    lleva lecho delante, detrás si sólo lo lleva detrás). Un lecho que se queda sin malla se
    avisa. Una malla con una cuenta o una cabeza de estribo delante no es malla: se avisa
    entera."""
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
    lecho_detras = delante[0] is None and detras[0] is not None
    usadas = detras if lecho_detras else delante

    parrillas: list[Parrilla] = []
    for malla, k in zip(mallas, usadas, strict=True):
        marca = marcas[k] if k is not None else None
        inicio = min(malla.start(), marca.start()) if marca else malla.start()
        fin = max(malla.end(), marca.end()) if marca else malla.end()
        # Lo que estorba se busca delante de todo lo que se toma: del lecho si va delante.
        estorbo = _estorbo_de_malla(vista, inicio)
        if estorbo is not None:
            avisos.append((estorbo, f"sin leer: «{texto[estorbo:fin].strip()}»"))
            consumir(estorbo, fin)
            continue
        sentidos: Literal["ambos", "x", "y"] | None = (
            "ambos"
            if malla["ambos"] or (marca and marca["ambos"])
            else _SENTIDO_XY.get(malla["xy"] or "")
        )
        if familia in FAMILIAS_CON_PARRILLA:
            parrillas += [
                Parrilla(
                    numero=malla["num"],
                    separacion_m=_metros(malla["sep"]),
                    lecho=lecho,
                    sentidos=sentidos,
                )
                for lecho in _lechos(marca)
            ]
        else:
            leida = texto[inicio:fin].strip()
            avisos.append((inicio, f"malla «{leida}» en {_con_articulo(familia)}: no se toma"))
        consumir(inicio, fin)

    tomadas = {k for k in usadas if k is not None}
    for k, marca in enumerate(marcas):
        if k not in tomadas:
            sobra = texto[marca.start() : marca.end()].strip()
            avisos.append((marca.start(), f"lecho «{sobra}» sin su malla: no se toma"))
            consumir(marca.start(), marca.end())
    return parrillas


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
    """«LS #4@20 A/S LI #4@20 A/S»; sin lecho cuando es único, sin sufijo si no dice sentidos."""
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
