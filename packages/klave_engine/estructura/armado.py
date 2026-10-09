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

# Un número de varilla mexicano y nada más: «#3/8» (pulgadas), «#3.5» o «#25» no son un
# número de la tabla y se avisan en vez de leerse a medias.
_NUM = (
    "(?:"
    + "|".join(re.escape(n) for n in sorted(NUMEROS, key=len, reverse=True))
    + r")(?![\d/]|\.\d)"
)
# Una separación en cm (nunca cero), con «CM» opcional; no puede seguirle una letra ni un
# dígito («@1S» se avisa entero, no se lee como @1).
_SEP = r"[1-9]\d{0,2}(?:\.\d{1,2})?"
_FIN_SEP = r"(?:\s?CMS?\.?)?(?![A-Z0-9])"
# Opcionalmente a través del salto de línea: «2E#3EXT@10» / «CENTRO@20» son un solo juego.
_LINEA = r"(?:\s*\|)?\s*"
_LS = r"(?:LS|L\.S\.?|LECHO\s+SUP\w*\.?)"
_LI = r"(?:LI|L\.I\.?|LECHO\s+INF\w*\.?)"
_AMBOS = r"(?:A\s*/\s*S|A\.?S\.?|AMBOS\s+SENTIDOS|AMBAS\s+DIRECCIONES)"

# La cantidad de un juego no puede ser el número de la varilla anterior («4#3 E#2@15») ni
# parte de una medida («15X30 E#2@20»): no la precede una letra, un dígito, «#» o «.».
_ESTRIBOS_RE = re.compile(
    r"(?<![A-Z0-9#.])(?<!#\s)"
    r"(?:(?P<n1>[1-9])\s*)?"
    r"(?:"
    r"(?P<e>E(?:ST(?:RIBOS?|\.)?)?)"
    r"(?:\s*(?:Y|\+)\s*(?:(?P<n2>[1-9])\s*)?(?P<eg>G(?:RAPAS?)?))?"
    r"|(?P<g>G(?:RAPAS?)?)"
    r"|(?P<l>LIGAS?)"
    r")"
    rf"\s*#\s*(?P<num>{_NUM})"
    r"(?:"
    rf"{_LINEA}EXT(?:REMOS?)?\.?\s*@\s*(?P<ext>{_SEP}){_FIN_SEP}"
    rf"(?:{_LINEA}(?:Y\s+)?CENTRO\s*@\s*(?P<centro>{_SEP}){_FIN_SEP})?"
    rf"|{_LINEA}@\s*(?P<sep>{_SEP}){_FIN_SEP}"
    r")?"
    rf"(?:{_LINEA}(?P<ref>VER\s+(?:CORTE|DETALLE)))?"
)

_MALLA_RE = re.compile(
    rf"(?:(?<![A-Z])(?:(?P<sup>{_LS})|(?P<inf>{_LI}))(?![A-Z.])\s*)?"
    rf"(?<!\d)#\s*(?P<num>{_NUM})\s*@\s*(?P<sep>{_SEP}){_FIN_SEP}"
    rf"(?:\s*(?:EN\s+)?(?P<ambos>{_AMBOS})(?![A-Z0-9])"
    r"|\s+(?:EN|SENTIDO)\s+(?P<xy>[XY])(?![A-Z0-9]))?"
)
# «#4@20 A/S L.S. Y L.I.»: los lechos escritos después de la malla. Nunca se roba el lecho
# de la malla siguiente («… LI #4@20»).
_LECHOS_DESPUES_RE = re.compile(
    rf"\s+(?:EN\s+)?(?P<l1>{_LS}|{_LI})"
    rf"(?:\s*(?:Y|E|,|\+)\s*(?P<l2>{_LS}|{_LI}))?(?![A-Z.])(?!\s*#)"
    rf"(?:\s*(?P<ambos>{_AMBOS})(?![A-Z0-9]))?"
)
_ES_LS = re.compile(_LS)
_SENTIDO_XY: dict[str, Literal["x", "y"]] = {"X": "x", "Y": "y"}

# Un grupo no lleva nada pegado detrás: ni «@» (eso es una separación) ni letras («2#5X150»
# dice además una longitud que este armado no guarda; se avisa entero).
_VARILLAS_RE = re.compile(
    rf"(?<![\d.#])(?P<n>[1-9]\d?)\s*(?:VARILLAS|VARS?\.?|V)?\s*#\s*(?P<num>{_NUM})"
    r"(?![A-Z])(?!\s*@)"
)

_NUMERO_EN_TOKEN_RE = re.compile(r"#\s*(\d+(?:\.\d+)?)")
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
    numero = m["num"]
    referencia = " ".join(m["ref"].split()) if m["ref"] else None
    n1 = int(m["n1"]) if m["n1"] else 1

    def juego(tipo: Literal["estribo", "grapa", "liga"], cantidad: int) -> JuegoEstribos:
        return JuegoEstribos(
            tipo=tipo, cantidad=cantidad, numero=numero, zonas=_zonas(m), referencia=referencia
        )

    if m["e"]:
        juegos = [juego("estribo", n1)]
        if m["eg"]:
            juegos.append(juego("grapa", int(m["n2"]) if m["n2"] else 1))
        return juegos
    if m["g"]:
        return [juego("grapa", n1)]
    return [juego("liga", n1)]


def _con_articulo(familia: str) -> str:
    return f"{'una' if familia in _FEMENINAS else 'un'} {familia.replace('_', ' ')}"


def _token(visible: str, i: int) -> tuple[int, int]:
    """El pedazo sin leer alrededor de la posición ``i``: hasta un espacio, un salto de
    línea o algo ya leído (con un tope a cada lado)."""
    a = i
    while a > 0 and visible[a - 1] not in _DELIMITADORES and i - a < _ALCANCE_TOKEN:
        a -= 1
    b = i + 1
    while b < len(visible) and visible[b] not in _DELIMITADORES and b - i < _ALCANCE_TOKEN:
        b += 1
    return a, b


def _aviso_sin_leer(token: str) -> str:
    for m in _NUMERO_EN_TOKEN_RE.finditer(token):
        if m.group(1) not in NUMEROS:
            return f"sin leer: «{token}»: no hay varilla del #{m.group(1)}"
    return f"sin leer: «{token}»"


def parsear_armado(textos: list[str], familia: str) -> Armado:
    """Lee los textos de un armado (en orden, uno por línea) para un elemento de ``familia``.

    Consume, en este orden: juegos de estribos (con sus zonas, que pueden seguir en la línea
    siguiente, y su «VER CORTE»), mallas (sólo en ``FAMILIAS_CON_PARRILLA``; en otra familia
    se avisan) y grupos de varillas. Todo ``#`` o ``@`` que quede sin consumir se avisa con
    el pedazo de texto que lo rodea. Secciones, palabras de familia, «H=», «REFUERZO» y
    comas son contexto y no se avisan."""
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
    parrillas: list[Parrilla] = []
    vista = visible()
    pos = 0
    while (malla := _MALLA_RE.search(vista, pos)) is not None:
        fin = malla.end()
        sentidos: Literal["ambos", "x", "y"] | None = (
            "ambos" if malla["ambos"] else _SENTIDO_XY.get(malla["xy"] or "")
        )
        lechos: list[Literal["sup", "inf", "unico"]]
        if malla["sup"] or malla["inf"]:
            lechos = ["sup" if malla["sup"] else "inf"]
        elif (despues := _LECHOS_DESPUES_RE.match(vista, fin)) is not None:
            lechos = [
                "sup" if _ES_LS.fullmatch(lecho) else "inf"
                for lecho in (despues["l1"], despues["l2"])
                if lecho
            ]
            if despues["ambos"]:
                sentidos = "ambos"
            fin = despues.end()
        else:
            lechos = ["unico"]
        if familia in FAMILIAS_CON_PARRILLA:
            parrillas += [
                Parrilla(
                    numero=malla["num"],
                    separacion_m=_metros(malla["sep"]),
                    lecho=lecho,
                    sentidos=sentidos,
                )
                for lecho in lechos
            ]
        else:
            leida = texto[malla.start() : fin].strip()
            aviso = f"malla «{leida}» en {_con_articulo(familia)}: no se toma"
            avisos.append((malla.start(), aviso))
        consumir(malla.start(), fin)
        pos = fin

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


# ------------------------------------------------------------------ textos canónicos


def _cm(separacion_m: float) -> str:
    cm = round(separacion_m * 100, 2)
    return str(int(cm)) if cm == int(cm) else f"{cm:g}"


def _texto_zonas(zonas: list[Zona]) -> str:
    partes = []
    for z in zonas:
        if z.separacion_m is None:
            continue
        s = _cm(z.separacion_m)
        prefijo = {"todo": "", "extremos": " EXT", "centro": " CENTRO"}[z.tramo]
        partes.append(f"{prefijo}@{s}")
    return "".join(partes)


def _cabeza(j: JuegoEstribos) -> str:
    if j.tipo == "liga":
        return "LIGA" if j.cantidad == 1 else f"{j.cantidad}LIGAS"
    letra = "E" if j.tipo == "estribo" else "G"
    return letra if j.cantidad == 1 else f"{j.cantidad}{letra}"


def texto_longitudinal(a: Armado) -> str:
    """«4#5+2#4»."""
    return "+".join(f"{g.cantidad}#{g.numero}" for g in a.longitudinales)


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
            uno_y_uno = j.cantidad == 1 and siguiente.cantidad == 1
            cabeza = "EYG" if uno_y_uno else f"{j.cantidad}E+{siguiente.cantidad}G"
            i += 2
        else:
            cabeza = _cabeza(j)
            i += 1
        texto = f"{cabeza}#{j.numero}{_texto_zonas(j.zonas)}"
        if j.referencia:
            texto += f" {j.referencia}"
        partes.append(texto)
    return " ".join(partes)


def texto_parrillas(a: Armado) -> str:
    """«LS #4@20 A/S LI #4@20 A/S»; sin lecho cuando es único, sin sufijo si no dice sentidos."""
    lechos = {"sup": "LS ", "inf": "LI ", "unico": ""}
    sentidos = {"ambos": " A/S", "x": " EN X", "y": " EN Y", None: ""}
    return " ".join(
        f"{lechos[p.lecho]}#{p.numero}@{_cm(p.separacion_m)}{sentidos[p.sentidos]}"
        for p in a.parrillas
    )


def texto_armado(a: Armado) -> str:
    """Longitudinales, estribos y parrillas, separados por un espacio."""
    return " ".join(
        parte for parte in (texto_longitudinal(a), texto_estribos(a), texto_parrillas(a)) if parte
    )
