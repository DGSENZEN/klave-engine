"""Element specifications stated on the sheet: the cuadro de castillos and
its informal cousins.

A structural sheet says what a mark *is* in one of three places, in
descending authority: a text table (MARCA | SECCIÓN | ARMADO | ESTRIBOS),
a detail where the mark sits under its stack of armado lines ("8#6" /
"2E#3EXT@10" / "CENTRO@20"), or a general note ("DALA 15X30 4#3 E#2@20"). This module
reads all of them into one inventory keyed by mark and stamps the matching
detections with their section so the takeoff uses the sheet's own numbers
instead of a typical value.

Every reading keeps its source: the sheet it was read on (``hoja``), how
(``metodo``), the entities it came from, which fields had text and what
could not be read (``avisos``). Which text belongs to which mark is decided
by ``estructura.asociacion`` (stacks and cuadro rows), and every armado text
is read by the lossless parser of ``estructura.armado``: «EYG#3@15» is a
stirrup and a grapa, «4#5+2#4» is two groups, and what cannot be read is
said, never dropped. Readings from different sheets are kept apart (Task 8
compares them), and an AI reading never fills a field whose text exists
on the drawing but could not be read.
"""

import bisect
import math
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Collection
from dataclasses import dataclass
from dataclasses import field as campo_de_dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Literal, TypeVar

from pydantic import BaseModel, Field

from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection, DetectionType, layer_matches
from klave_engine.detection.text_patterns import (
    FOOTING_MARK_PREFIXES,
    PILE_MARK_PREFIXES,
    TextPatternConfig,
)
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.estructura._armado_texto import (
    LADO,
    LADO_FINAL,
    SECCION_CON_COMA_DUDOSA,
    normalizar,
)
from klave_engine.estructura.armado import (
    ARMEX_RE,
    FAMILIAS_CON_PARRILLA,
    Armado,
    clase_de_tramo,
    fragmentos_ajenos,
    lo_ve_el_parser,
    parsear_armado,
    sin_cuentas_de_varillas,
    texto_estribos,
    texto_longitudinal,
    texto_parrillas,
    tiene_armado,
    tramos_de_armado,
)
from klave_engine.estructura.asociacion import (
    ARMADO_RE,
    Rechazo,
    SeccionDeTitulo,
    asociar,
    asociar_secciones,
    hoja_y_llave,
    lo_lee_una_nota,
    marca_en_texto,
)
from klave_engine.estructura.marcas import (
    GUIONES,
    con_guion,
    es_rango,
    extremos_de_rango,
    forma_de_marca,
    leer_marcas,
    marca_en_rango,
    marca_normalizada,
    marca_sola,
    marcas_de_ficha,
    marcas_nombradas,
    punteros,
    sin_referencias,
    titulos,
)
from klave_engine.estructura.reglas import leer_reglas
from klave_engine.estructura.textos import (
    alto_de_texto,
    ancla_texto,
    extension_de_texto,
)
from klave_engine.geometry.bbox import (
    BBox,
    bbox_center,
    bbox_contains_point,
    bbox_height,
)

# A section: two sides as written, whole or with their decimals («20.5X40», «20X40,5»): read
# with its decimals, never truncated (R109). A piece's three measures are not a section.
_SECTION_RE = re.compile(rf"(?<![\dxX×.#Ø@])({LADO})\s*[xX×]\s*({LADO_FINAL})(?![\dxX×]|\.\d)")
_BLOCK_RE = re.compile(rf"(?<![\dxX×.]){LADO}\s*[xX×]\s*\d{{1,3}}(?:\.\d+)?\s*[xX×]\s*{LADO_FINAL}")

_FAMILY_KEYWORDS: list[tuple[str, re.Pattern[str]]] = [
    ("dala", re.compile(r"\bDALA|\bCADENAS?\b", re.I)),
    ("contratrabe", re.compile(r"\bCONTRATRABE", re.I)),
    ("trabe", re.compile(r"\bTRABE|\bVIGAS?\b", re.I)),
    ("castillo", re.compile(r"\bCASTILLO", re.I)),
    ("columna", re.compile(r"\bCOLUMNA", re.I)),
    ("zapata", re.compile(r"\bZAPATA", re.I)),
    ("muro", re.compile(r"\bMURO", re.I)),
]
_MIN_SIDE_CM, _MAX_SIDE_CM = 8, 400  # up to a 4 m zapata; a castillo starts at 8 cm
_SOURCE_RANK = {"cuadro": 3, "detalle": 2, "nota": 1, "ia": 0}

Source = Literal["cuadro", "detalle", "nota", "ia"]
# How a reading was made: a cuadro row, a mark's stack of armado lines, the
# cotas or the drawn section of a detail, a section callout, a note, the AI.
Metodo = Literal["fila", "pila", "cotas", "geometria", "llamada", "nota", "ia"]
Campo = Literal["seccion", "longitudinales", "estribos", "parrillas", "longitud"]
CAMPOS: tuple[Campo, ...] = ("seccion", "longitudinales", "estribos", "parrillas", "longitud")
_CAMPOS_DE_ARMADO: tuple[Campo, ...] = ("longitudinales", "estribos", "parrillas")
# A section keeps the order it was written or drawn in (a beam's b×h, R75): only a
# castillo, a columna or a pilote is compared with its sides sorted (R88). An
# unknown or generic family keeps the written order.
FAMILIAS_QUE_SE_ORDENAN = frozenset({"castillo", "columna", "pilote"})
# A text's sheet: its name (``hoja``) and its unique key (``hoja_llave``).
Sheet = Callable[[NormalizedEntity], tuple[str, str]]


def _no_frames(e: NormalizedEntity) -> tuple[str, str]:
    return e.source_file, f"{e.source_file}#"


class Bloqueo(BaseModel):
    """A drawing text that keeps the AI from filling one field of a mark (R64,
    R68). The AI reading carries it (R69), so that no later stage elects the
    blocked value: the definitions turn it into an unreadable drawing value,
    with the AI only as an alternative."""

    campo: Campo
    texto: str
    entidades: list[str] = Field(default_factory=list)
    hoja: str = ""
    hoja_llave: str = ""
    # Where the text sits: a cuadro or a detail when a reading of the drawing
    # consumed it (or it is a stack line), a note otherwise.
    fuente: Literal["cuadro", "detalle", "nota"]
    # How it blocks: a reading of the mark (read or not), a line that names the
    # mark (R64), a rejected text that names it, a line where the mark occurs
    # under the loose comparison of the backstop (R68), or an unowned line in
    # the mark's column past its stack's cut (R111: «posible», a block only).
    por: Literal["lectura", "texto", "rechazo", "respaldo", "posible"]
    # The text names this mark and no other (its reading, «K-7 E#3@1S», a title
    # «CORTE K-7 …», a list that names it); otherwise it is ambiguous: it may be
    # another mark's (R74).
    inequivoco: bool = True


class ElementSpec(BaseModel):
    mark: str  # "K-1", or the family name for family-level notes
    family: str
    # Its sides as the drawing gives them: whole or with their decimals (20.5, 72.5), R106, R109.
    section_cm: tuple[int | float, int | float] | None = None
    rebar: str | None = None  # longitudinal, canonical: "4#5+2#4" (every group)
    stirrups: str | None = None  # canonical: "EYG#3@15", "2E#3 EXT@10 CENTRO@20"
    mesh: str | None = None  # parrillas, canonical: "LS #4@20 A/S LI #4@20 A/S"
    # Declared length in m (pilotes): from the notes, the cuadro or the AI.
    length_m: float | None = None
    source: Source
    source_text: str
    confidence: float
    # The reading itself, with its source (no confidence of its own):
    armado: Armado | None = None  # the parsed armado (rebar/stirrups/mesh are its renders)
    hoja: str = ""  # the sheet (frame code) it was read on; its file without frames
    # The sheet's unique key (file and frame): two frames sharing a code are two sheets.
    hoja_llave: str = ""
    metodo: Metodo = "nota"
    # The fields whose text the drawing has for this reading, read or not: an
    # AI reading never fills one of them (a text that failed to parse is an
    # aviso, not an empty field).
    campos_con_texto: list[Campo] = Field(default_factory=list)
    entidades: list[str] = Field(default_factory=list)  # the texts it was read from
    avisos: list[str] = Field(default_factory=list)  # what could not be read, disagreements
    # An AI reading: the fields it has a value for that the drawing has text for
    # (R69), and the texts that block each one. That value is never elected.
    campos_bloqueados: list[Campo] = Field(default_factory=list)
    bloqueos: list[Bloqueo] = Field(default_factory=list)
    # The section has an assumed side (one cota and a square outline taken square, or the
    # width the sheet's callouts use): a «supuesto» value, never a «detalle» one (R81).
    seccion_supuesta: bool = False
    # R125: its family is only its mark's prefix (no text of the drawing states it): a reading
    # that states one (the AI's included) wins over it.
    familia_supuesta: bool = False
    # R150: the section the label's title points at is drawn and is not a rectangle (K-15A's L).
    seccion_no_rectangular: bool = False
    # R168: the wall thickness (cm) the reading's detail declares under its title («CI» over
    # «(PARA MUROS DE 15CM)»): the reading is that variant of its mark's.
    para_muro_cm: float | None = None


class TextoConMarca(BaseModel):
    """A line of a drawing text that names marks and holds an armado- or
    section-shaped fragment (R64): what the drawing says of those marks, read
    or not. An AI reading never fills the matching fields of a mark it names,
    unless a reading of that same mark consumed the text."""

    entidad_id: str
    texto: str  # the line (an MTEXT gives one per line)
    hoja: str
    hoja_llave: str
    # The marks as the text writes them: normalized marks, a glued form
    # («K-7E»: resolved later against the known marks) and ranges as written.
    marcas: list[str]
    campos: list[Campo]  # «seccion» for a section, the three armado fields for armado


class LineaConFragmento(BaseModel):
    """A line of a drawing text that holds an armado-, section- or
    length-shaped fragment and a letter (R68, R80): the backstop of the AI
    block looks in it for every known mark under a loose comparison, whatever
    the mark grammar read in it. A line without a letter names no mark."""

    entidad_id: str
    texto: str
    campos: list[Campo]  # the fields its fragments show (``campos_de_fragmento``)


class HojaConFragmentos(BaseModel):
    """The fragment lines of one sheet: its name and unique key, once."""

    hoja: str
    hoja_llave: str
    lineas: list[LineaConFragmento] = Field(default_factory=list)


class ScheduleInventory(BaseModel):
    specs: list[ElementSpec] = Field(default_factory=list)
    by_mark: dict[str, ElementSpec] = Field(default_factory=dict)
    by_family: dict[str, ElementSpec] = Field(default_factory=dict)
    # Declared concrete strengths by element family (kg/cm²), from notes
    # such as "RESISTENCIA EN CASTILLOS ___ F'C=200 Kg/Cm²".
    concrete_fc: dict[str, int] = Field(default_factory=dict)
    # Pile length declared in the notes ("PILOTES DE 12.00 M DE LONGITUD"), m.
    pile_length_m: float | None = None
    tables_found: int = 0
    notes: list[str] = Field(default_factory=list)
    # Text entities that are the marks of a cuadro drawn on a planta sheet:
    # they name a type, they are not an element to count.
    cuadro_mark_entities: list[str] = Field(default_factory=list)
    # R145: of those, the titles of a detail: a label that owns a drawn section with cotas (a
    # detail drawn inside a planta sheet) or carries a «señalada» leader. A definition, never a
    # placement.
    titulos_de_detalle: list[str] = Field(default_factory=list)
    # Armado texts the association could not give to a mark (ambiguous, unowned,
    # another family's…): reported, never read in silence.
    rechazos: list[Rechazo] = Field(default_factory=list)
    # Every drawing line that names marks and holds armado or a section (R64):
    # the AI never covers what they say, whoever reads them.
    textos_con_marca: list[TextoConMarca] = Field(default_factory=list)
    # Every drawing line with an armado, section or length fragment and a
    # letter, mark or not (R68), by sheet.
    textos_con_fragmento: list[HojaConFragmentos] = Field(default_factory=list)
    # Every mark a drawing text names without ambiguity (the grammar's «unica»),
    # in its one spelling, with how many texts name it: readings, rejected
    # texts, cuadro rows and every label, the placements' too (R84).
    marcas_del_plano: dict[str, int] = Field(default_factory=dict)
    # The texts the rules reader (``estructura.reglas.leer_reglas``) read a rule from, with the
    # lines it read (none: the whole text): consumed, never rejected (R119).
    leidos_por_reglas: dict[str, list[str]] = Field(default_factory=dict)

    def lineas_con_fragmento(self) -> list[tuple[HojaConFragmentos, LineaConFragmento]]:
        return [(hoja, linea) for hoja in self.textos_con_fragmento for linea in hoja.lineas]


_FC_FAMILIES: list[tuple[str, re.Pattern[str]]] = [
    ("cimentacion", re.compile(r"CIMENTACI|ZAPATA|DADO", re.I)),
    ("castillo", re.compile(r"CASTILLO", re.I)),
    ("dala", re.compile(r"CERRAMIENTO|DALA|CADENA", re.I)),
    ("trabe", re.compile(r"TRABE|VIGA", re.I)),
    ("losa", re.compile(r"LOSA", re.I)),
    ("firme", re.compile(r"FIRME", re.I)),
    ("columna", re.compile(r"COLUMNA", re.I)),
    ("muro", re.compile(r"MURO", re.I)),
]
_FC_RE = re.compile(r"F\s*'?\s*C\s*=?\s*(\d{3})", re.I)


def parse_concrete_fc(texts: list[str]) -> dict[str, int]:
    """Family → f'c from the sheet's notes; the first explicit statement wins
    per family, and one line may declare several families."""
    declared: dict[str, int] = {}
    for text in texts:
        for line in text.replace("\\P", "\n").splitlines():
            match = _FC_RE.search(line)
            if not match:
                continue
            value = int(match.group(1))
            if not 100 <= value <= 600:
                continue
            head = line[: match.start()]
            # "LOSAS DE AZOTEA Y TRABES ... F'C=250" speaks for both families.
            for family, pattern in _FC_FAMILIES:
                if pattern.search(head) and family not in declared:
                    declared[family] = value
    return declared


# A note that states the pile length: "PILOTES DE 12.00 M DE LONGITUD",
# "LONGITUD DE PILOTE: 12 M", "PILOTE Ø60 L=12.00 M", "PILAS DE 15 M".
_PILE_LENGTH_RES = (
    re.compile(
        r"PIL(?:OTE|A)S?\b[^\n]{0,60}?(?<!\d)(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:M|MTS?|METROS)\b",
        re.I,
    ),
    re.compile(
        r"LONG(?:ITUD|\.)?\s*(?:DE\s+)?PIL(?:OTE|A)S?[^\d\n]{0,12}(\d{1,2}(?:[.,]\d{1,2})?)(?!\d)",
        re.I,
    ),
)


def parse_pile_length(texts: list[str]) -> float | None:
    """Pile length in m from the sheet's notes; the first plausible one wins
    (3–60 m). Never a guess: None when nothing is declared."""
    for text in texts:
        for line in text.replace("\\P", "\n").splitlines():
            for pattern in _PILE_LENGTH_RES:
                match = pattern.search(line)
                if not match:
                    continue
                value = float(match.group(1).replace(",", "."))
                if 3.0 <= value <= 60.0:
                    return value
    return None


# ------------------------------------------------------------------ parsing


def _lados(m: re.Match[str]) -> tuple[int | float, int | float]:
    """The two sides of a ``_SECTION_RE`` match as written («40,5» is 40.5)."""
    return _cm(float(m.group(1).replace(",", "."))), _cm(float(m.group(2).replace(",", ".")))


def _read_section(
    text: str, family: str | None = None
) -> tuple[tuple[int | float, int | float] | None, list[str], bool]:
    """The section written in ``text`` (the first NNxNN with both sides in
    8–400 cm), the avisos for what was not taken (a side out of range, a second
    different section) and whether the text has a section at all. The section
    keeps its written order (a beam's b×h, R75, R88); only a castillo's, a
    columna's or a pilote's sides are sorted. The section of an object («PLACA
    BASE 35X35», R100) is that object's, not the element's: it is never taken,
    the field stays claimed, and the parser reports it with its object."""
    blocked = [m.span() for m in _BLOCK_RE.finditer(text)]
    ajenos = fragmentos_ajenos(text)
    section: tuple[int | float, int | float] | None = None
    avisos: list[str] = []
    found = False
    for m in _SECTION_RE.finditer(text):
        if any(s <= m.start() < e for s, e in blocked):
            continue
        found = True
        if any(a <= m.start() and m.end() <= b for a, b in ajenos):
            continue
        dudosa = SECCION_CON_COMA_DUDOSA.match(text, m.end())
        if dudosa is not None:
            # R117: a comma after the section that neither starts a fragment nor ends a decimal
            # («15X20,4A»): which section it is, the text does not say. Quoted and claimed.
            cola = re.match(r",\S*", text[m.end() :])
            assert cola is not None
            citada = f"{m.group(0)}{cola.group(0)}"
            avisos.append(f"sección con una coma que no se sabe leer: «{citada}»")
            continue
        a, b = _lados(m)
        leida = (min(a, b), max(a, b)) if family in FAMILIAS_QUE_SE_ORDENAN else (a, b)
        if not (_MIN_SIDE_CM <= a <= _MAX_SIDE_CM and _MIN_SIDE_CM <= b <= _MAX_SIDE_CM):
            avisos.append(f"sección fuera de rango: «{m.group(0)}»: no se toma")
        elif section is None:
            section = leida
        elif leida != section:
            avisos.append(
                f"otra sección en el mismo texto: «{m.group(0)}»; se toma {section[0]}x{section[1]}"
            )
    return section, avisos, found


# What a fragment of a drawing text says (R76): a stirrup or grapa head before
# «#», or a zoned spacing, is stirrups; a count before «#» is bars; a bare
# «#n@s» is a mesh, whoever's it is (R95), and in a family without meshes it
# may also be stirrups written without their head; a bare «@s» is a mesh's
# spacing in a family that has one, stirrups otherwise; a length («L=8.00»,
# «LONG. 8», «LONGITUD … 8 M») is the length.
_CABEZA_DE_ESTRIBOS = re.compile(
    r"(?<![A-Z0-9#@.])(?:\(?\d{1,2}\)?\s*)?(?:EYG|E|G|EST|ESTR|ESTRIBOS?|GRAPAS?|LIGAS?)"
    r"(?:\s*[Y+/&,-]\s*(?:\d{1,2}\s*)?(?:E|G))?\.?\s*[#Ø]|(?:CENTRO|EXT)\.?\s*@",
)
# A bar group as the parser writes it (R87, R91, R93): a count, «-» or «)» after it, the word of
# the bar («VARILLAS», «VARS.», «PZAS», «PIEZAS», «V») with or without «DEL», and «#n»; or the
# word in front («V4#4», «VAR 4#4»).
_CUENTA = (
    r"(?<![#@.\d])\d{1,2}\s*(?:[-)]\s*)?"
    r"(?:(?:VARILLAS|VARS?\.?|PZAS?\.?|PIEZAS|V)(?:\s+DEL?)?)?\s*[#Ø]\s*"
)
_CUENTA_DELANTE = r"(?<![A-Z0-9])(?:VARS?\.?|V)\s*\d{1,2}\s*[#Ø]\s*"
_CUENTA_DE_VARILLAS = re.compile(rf"{_CUENTA}\d(?!\d|\s*@)|{_CUENTA_DELANTE}\d")
# A stirrup set whole: its head, its bar and its spacings («E#3@1S», «2E#3EXT@10 CENTRO@20»).
_JUEGO_DE_ESTRIBOS = re.compile(
    rf"(?:{_CABEZA_DE_ESTRIBOS.pattern})\s*\d*(?:\.\d+)?"
    r"(?:[\s|]*(?:(?:EXT\w*|CENTRO)\.?\s*)?@\s*\w+)*"
)
_SEPARACION = re.compile(r"[#Ø]\s*\d+(?:\.\d+)?\s*@|@\s*\d")
_MALLA_EN_TEXTO = re.compile(r"[#Ø]\s*\d+(?:\.\d+)?\s*@\s*\d+(?:\.\d+)?")
_LONGITUD = re.compile(
    r"\bL\s*=\s*\d|\bLONG\.?\s*=?\s*\d|\bLONGITUD\b[^|\n]*?\d+(?:[.,]\d+)?\s*(?:M|MTS?|METROS)\b"
)
_VARILLA = re.compile(r"[#Ø]\s*\d")


# The number of a numbered note («3.-», «1.-», «2)», and with a letter «a).-», «A)», «b.-»,
# R110): never a count right before a bar («4-#3», «4) #3» are 4 bars, R93).
_NUMERO = r"(?:\d{1,2}(?:\.-?|-|\))|[A-Z](?:\)(?:\.-?)?|\.-))"
_NUMERO_DE_NOTA = re.compile(rf"^\s*{_NUMERO}(?!\s*[#Ø\d])", re.I)


# What a recognised fragment consumes (R86): a section or a piece's three
# measures, a stirrup set, a bar group, a mesh, a spacing, a length, a mark, the
# number of a numbered note. A digit left over is something nobody recognised.
_CONSUMIDOS = (
    _BLOCK_RE,
    re.compile(rf"(?<![\dxX×.]){LADO}\s*[xX×]\s*{LADO_FINAL}(?:\s*CMS?\.?)?"),
    _JUEGO_DE_ESTRIBOS,
    re.compile(rf"{_CUENTA}\d{{1,2}}(?:\.5)?|{_CUENTA_DELANTE}\d{{1,2}}(?:\.5)?"),
    re.compile(r"[#Ø]\s*\d{1,2}(?:\.5)?\s*@\s*\d+(?:\.\d+)?(?:\s*CMS?\.?)?"),
    # A spacing, alone or after how many stirrups go at it («@20», «8@15,1@6»).
    re.compile(r"(?:(?<![#Ø.\d])\d{1,2}\s*)?@\s*\d+(?:\.\d+)?(?:\s*CMS?\.?)?"),
    re.compile(
        r"\bL\s*=\s*\d+(?:[.,]\d+)?(?:\s*(?:M|MTS?|CMS?)\b)?"
        r"|\bLONG\.?\s*=?\s*\d+(?:[.,]\d+)?(?:\s*(?:M|MTS?)\b)?"
        r"|\bLONGITUD\b[^|\n]*?\d+(?:[.,]\d+)?\s*(?:M|MTS?|METROS)\b"
    ),
    _NUMERO_DE_NOTA,
)


def _sin_lo_reconocido(t: str, marcas: Collection[str]) -> str:
    """``t`` without its recognised fragments and without the marks the mark
    grammar names in the whole text (``marcas``, in their one spelling,
    ``forma_de_marca``). A token is never read alone (R96): «V 3» is a mark
    only if the whole text names V-3; in «… LS V 3» it is three bars, a digit
    nobody read. The named marks go first, so no fragment takes their digits
    («T-2 E#3@1S»: the 2 is T-2's, not a count of stirrups); what is left of a
    glued one after the fragments («K-7E» of «K-7E#3@20») goes after."""
    config = TextPatternConfig()

    def en_blanco(m: re.Match[str], ficha: str) -> str:
        return " " * len(m.group(0)) if _nombrada(ficha, marcas, config) else m.group(0)

    t = _ESPACIADA.sub(lambda m: en_blanco(m, f"{m[1]}-{m[2]}"), t)
    t = _FICHA.sub(lambda m: en_blanco(m, m.group(0)), t)
    for patron in _CONSUMIDOS:
        t = patron.sub(" ", t)
    t = _con_marcas_juntas(t)
    fichas = [f for f in re.split(r'[\s:;,()="]+', t) if f]
    return " ".join(f for f in fichas if not _nombrada(f, marcas, config))


def _nombrada(ficha: str, marcas: Collection[str], config: TextPatternConfig) -> bool:
    """Si la ficha es una de las marcas que nombra el texto entero, o varias de ellas unidas
    («T-1+T-2», «K-1-K-3»): nunca se lee sola (R96)."""
    ficha = ficha.rstrip(GUIONES + ".")
    if forma_de_marca(ficha, config) in marcas:
        return True
    partes = marcas_de_ficha(ficha, config)
    return bool(partes) and all(p in marcas for p in partes)


# A mark written with a space («K 7», «TRABE T 1», «TL 1») and a token, as the residue sees them.
_ESPACIADA = re.compile(r"(?<![A-Z0-9])([A-Z]{1,4})\s*-?\s+(\d{1,3}[A-Z]?)(?=$|[\s:;,()=\"])")
_FICHA = re.compile(r'[^\s:;,()="]+')


def _con_marcas_juntas(t: str) -> str:
    """Las marcas escritas con espacio («K 7», «TRABE T 1», «TL 1») escritas juntas: una ficha que
    se compara con las que nombra el texto entero."""
    return _ESPACIADA.sub(r"\1-\2", t)


def campos_de_fragmento(
    texto: str, family: str | None = None, marcas: Collection[str] | None = None
) -> list[Campo]:
    """The fields a drawing text claims, by what its fragments show (R76): a
    section, a stirrup head, a bar count, a mesh, a spacing, a length. Only when
    every digit of the text is in a fragment it recognises (a section, a bar
    group, a stirrup set, a mesh, a spacing, a length, a mark the whole text
    names, a note number) does it claim just those fields (R86); otherwise it
    claims every field ``family`` can have (a castillo never has parrillas;
    without a family, every field). A mesh claims parrillas even in a family
    that has none (R95): the field is blocked and the text reported, never
    moved to another field. ``marcas`` are the marks the whole text names
    (``marcas_nombradas``); for a piece of a text (an aviso's quote), the
    caller passes the whole text's (R96)."""
    if marcas is None:
        marcas = marcas_nombradas(texto, TextPatternConfig())
    t = normalizar(texto)[0]
    con_parrilla = family is None or family in FAMILIAS_CON_PARRILLA
    campos: list[Campo] = []
    if _read_section(t)[2]:
        campos.append("seccion")
    if _CUENTA_DE_VARILLAS.search(t):
        campos.append("longitudinales")
    if _CABEZA_DE_ESTRIBOS.search(t):
        campos.append("estribos")
    sin_cabeza = _JUEGO_DE_ESTRIBOS.sub(" ", t)
    if _MALLA_EN_TEXTO.search(sin_cabeza):
        # «#n@s» sin cabeza: una malla (R95). En una familia que no lleva mallas pueden ser
        # también sus estribos escritos sin cabeza («K-1 15X15 4#3 #2@20»): reclama los dos.
        campos.append("parrillas")
        if family not in FAMILIAS_CON_PARRILLA:
            campos.append("estribos")
    if _SEPARACION.search(_MALLA_EN_TEXTO.sub(" ", sin_cabeza)):
        campos.append("parrillas" if family in FAMILIAS_CON_PARRILLA else "estribos")
        if family is None:
            campos.append("parrillas")
    if _LONGITUD.search(t):
        campos.append("longitud")
    if ARMEX_RE.search(t):
        # R107: un armado prefabricado dice las varillas y los estribos, aunque nadie los lea.
        campos += ["longitudinales", "estribos"]
    if re.search(r"\d", _sin_lo_reconocido(t, marcas)):
        # Algo con cifras que nadie reconoce: puede ser de cualquier campo de la familia.
        campos += ["seccion", "longitudinales", "estribos"]
        if con_parrilla:
            campos.append("parrillas")
        if family in (None, "pilote"):
            campos.append("longitud")
    return [c for c in CAMPOS if c in campos]


# The family of a mark by its prefix. The foundation prefixes are the detectors' own
# (``text_patterns``, R95): every mark a detector places has its family (ZA-3 is a zapata).
_FAMILIA_DE_PREFIJO: dict[str, str] = {
    "K": "castillo",
    "C": "columna",
    "COL": "columna",
    "T": "trabe",
    "TB": "trabe",
    "CT": "contratrabe",
    "CTA": "contratrabe",
    "D": "dala",
    "DL": "dala",
    "DAL": "dala",
    "CE": "dala",
    "CI": "dala",  # R152: the type tags of a dala (CI, DC, DA-2)
    "DC": "dala",
    "DA": "dala",
    "CR": "cerramiento",
    "MC": "muro_concreto",
    **dict.fromkeys(FOOTING_MARK_PREFIXES, "zapata"),
    **dict.fromkeys(PILE_MARK_PREFIXES, "pilote"),
}


def family_of_mark(mark: str) -> str:
    prefix = re.match(r"[A-Z]+", mark.upper())
    head = prefix.group(0) if prefix else ""
    return _FAMILIA_DE_PREFIJO.get(head, "elemento")


def _family_in_text(text: str) -> str | None:
    for family, pattern in _FAMILY_KEYWORDS:
        if pattern.search(text):
            return family
    return None


# The number of a note before its first word («1.-», «3)», «2.»).
_NUMERO_AL_INICIO = re.compile(rf"^\s*{_NUMERO}\s*", re.I)


def _family_subject(text: str) -> tuple[str | None, list[str]]:
    """The family a family note is about (R83) and every family the text names.
    The family word must be the subject: the text's first word, after an
    optional note number («CADENA DE ENRASE 15x25 …», «1.- CASTILLOS 15X15 …»,
    «DALA: 15X20 …», «a).- DALAS …»; a «WORD:» elsewhere is not, R110); and no
    word of another family may appear elsewhere. A family word in another place («2 VARILLAS #5
    ANCLADA AL MURO O CADENA …», «ANCLAR A LA TRABE CON 2#4», «ARMEX 15X30
    CADENA DE BORDE») gives no subject: the text is no family's note."""
    upper = text.upper()
    words: list[tuple[int, int, str]] = []
    for family, pattern in _FAMILY_KEYWORDS:
        for m in pattern.finditer(upper):
            end = m.end()
            while end < len(upper) and upper[end].isalpha():
                end += 1  # «CASTILLOS», «DALAS»: la palabra entera
            words.append((m.start(), end, family))
    words.sort()
    families = list(dict.fromkeys(family for _a, _b, family in words))
    number = _NUMERO_AL_INICIO.match(upper)
    head = number.end() if number else len(upper) - len(upper.lstrip())
    # Sólo la palabra a la cabeza es el sujeto (R110): «DALA: 15X20 …» sí; «ANCLAR A LA TRABE: 2#4»,
    # «VER PLANO DE DALAS: 4#3 E#2@20», no.
    subject = next((family for start, _end, family in words if start == head), None)
    if subject is None or any(family != subject for family in families):
        return None, families
    return subject, families


# R107: the name of a family alone on a line («CADENA DE DESPLANTE», «DALA», «CASTILLOS»).
_FRASE_DE_FAMILIA = re.compile(
    r"(?:DALAS?|CADENAS?|CASTILLOS?|COLUMNAS?|CONTRATRABES?|TRABES?|VIGAS?|ZAPATAS?|MUROS?)"
    r"(?:\s+(?:DE\s+LA|DE|DEL)\s+[A-ZÁÉÍÓÚÑ]+){0,2}\.?"
)


def _frase_de_familia(texto: str) -> tuple[str, list[str]] | None:
    """R107: a text whose first or last line is just a family's name («CADENA DE DESPLANTE»)
    and whose other lines carry armado — bars, stirrups, a mesh, a section; never a piece's
    three measures («10X20X40») — is that family's label over its armado: (the family, the
    other lines). ARMEX is armado (prefab), never a family's name."""
    lineas = [" ".join(linea.upper().split()) for linea in texto.split("\n")]
    lineas = [linea for linea in lineas if linea]
    if len(lineas) < 2:
        return None
    for frase, otras in ((lineas[0], lineas[1:]), (lineas[-1], lineas[:-1])):
        if not _FRASE_DE_FAMILIA.fullmatch(frase):
            continue
        family = _family_in_text(frase)
        if family is None or any(_family_in_text(o) not in (None, family) for o in otras):
            continue
        if any(tiene_armado(o) or _read_section(o)[2] for o in otras):
            return family, otras
    return None


def _render(render: Callable[[Armado], str], armado: Armado, avisos: list[str]) -> str | None:
    try:
        return render(armado) or None
    except ValueError as error:  # a parsed armado always renders; say so if it ever does not
        avisos.append(f"no se pudo escribir el armado leído: {error}")
        return None


def _reading(
    textos: list[str],
    family: str,
    section_of_the_element: bool = True,
    sin_marca: str | None = None,
    residuos: Collection[str] = (),
) -> dict:
    """One reading of an armado text (one string per line) for an element of
    ``family``: its section, its parsed armado and the canonical renders, the
    fields whose text is there and every aviso. What could not be read claims
    the fields its fragments show (R76, R86), so nobody fills them from
    elsewhere. A note's own mark (``sin_marca``, however it is written: «T1-1»,
    «K 7», «K-1-A») and its number («3.-») are not armado: the parser does not
    see them, so they are never reported as unread. Lossless (R104): every
    armado span of the text (``tramos_de_armado``) is read or quoted in an
    aviso — the parser's pieces always are; a section or a length the reading
    did not take («HUECOS DE HASTA 15X20»), and what the mark grammar left as
    unread bars (``residuos``, R103: «… E#2@20 V-4»), are quoted here."""
    section, avisos, has_section = _read_section(" | ".join(textos), family)  # never across lines
    if not section_of_the_element:
        section, avisos, has_section = None, [], False
    a_leer = textos
    if sin_marca is not None:
        a_leer = [_sin_la_marca(t, sin_marca) for t in textos]
    armado = parsear_armado(a_leer, family)
    if a_leer is not textos:
        armado.texto_original = " | ".join(t.strip() for t in textos if t and t.strip())
    avisos = avisos + list(armado.avisos)
    rebar = _render(texto_longitudinal, armado, avisos)
    stirrups = _render(texto_estribos, armado, avisos)
    mesh = _render(texto_parrillas, armado, avisos)
    # What could not be read claims the fields its fragments show (R76); a residue with digits
    # nobody recognises claims every field the family can have, the section too (R86, R92).
    # A quote is a piece of the text: its tokens are marks only if the whole text names them
    # (R96), never read alone.
    config = TextPatternConfig()
    nombradas = set().union(*(marcas_nombradas(t, config) for t in textos))
    if sin_marca is not None:
        nombradas.add(forma_de_marca(sin_marca, config))
    perdidos = _sin_leer_ni_citar(textos, family, section, avisos, residuos, section_of_the_element)
    avisos += [aviso for aviso, _cita in perdidos]
    sin_leer: set[Campo] = set()
    for aviso in [*armado.avisos, *(f"«{cita}»" for _aviso, cita in perdidos)]:
        citas = re.findall(r"«([^»]*)»", aviso)
        for cita in citas or [aviso]:
            sin_leer.update(campos_de_fragmento(cita, family, nombradas))
    campos: list[Campo] = []
    if has_section or "seccion" in sin_leer:
        campos.append("seccion")
    if armado.longitudinales or "longitudinales" in sin_leer:
        campos.append("longitudinales")
    if armado.estribos or "estribos" in sin_leer:
        campos.append("estribos")
    if armado.parrillas or "parrillas" in sin_leer:
        campos.append("parrillas")
    if _LONGITUD.search(" | ".join(textos)):
        campos.append("longitud")  # nadie lee una longitud escrita: se dice
    # R110: un puntero remite el armado a otro dibujo: las varillas y los estribos son del plano
    # (por referencia), nunca de la IA; el puntero se guarda (en su pieza, o en un aviso).
    remitidos = [p for t in textos for p in punteros(t, config)]
    if remitidos:
        campos = [c for c in CAMPOS if c in {*campos, "longitudinales", "estribos"}]
        con_referencia = any(g.referencia for g in armado.longitudinales) or any(
            j.referencia for j in armado.estribos
        )
        if not con_referencia:
            avisos += [f"armado remitido a otro dibujo: «{p}»" for p in remitidos]
    return {
        "section_cm": section,
        "rebar": rebar,
        "stirrups": stirrups,
        "mesh": mesh,
        "armado": armado,
        "campos_con_texto": campos,
        "avisos": avisos,
    }


def _plano(texto: str) -> str:
    """Un texto en mayúsculas y con los espacios juntos, como cita el parser."""
    return " ".join(texto.upper().split())


def _escrito(residuo: str, textos: list[str]) -> str | None:
    """Cómo escribe el texto un residuo de la gramática («V-4» puede ser «V 4», «V–4»): la última
    vez que aparece (acaba el texto, R103)."""
    partes = re.fullmatch(r"([A-Z]+)-?(\d+)([A-Z]?)", residuo)
    if partes is None:
        return None
    patron = rf"(?<![A-Z0-9]){partes[1]}\s*[{re.escape(GUIONES)}]?\s*0*{int(partes[2])}{partes[3]}"
    vistos = list(re.finditer(patron + r"(?![A-Z0-9])", _plano(" ".join(textos))))
    return vistos[-1].group(0) if vistos else None


def _sin_leer_ni_citar(
    textos: list[str],
    family: str,
    section: tuple[int | float, int | float] | None,
    avisos: list[str],
    residuos: Collection[str],
    section_of_the_element: bool,
) -> list[tuple[str, str]]:
    """What a reading leaves neither read nor quoted (R104), as (aviso, quote): a
    section span that is not the section read («HUECOS DE HASTA 15X20», a
    section the reader does not take) and a length nobody quoted; the parser's
    pieces are always read or quoted by the parser itself. And what the mark
    grammar left as unread bars after another mark's armado («… E#2@20 V-4»,
    R103): the parser takes «V-4» as a mark, so it never quotes it."""
    citas = [_plano(c) for aviso in avisos for c in re.findall(r"«([^»]*)»", aviso)]
    perdidos: list[tuple[str, str]] = []

    def citado(tramo: str) -> bool:
        # Sólo una cita que lo trae entero, en sus fronteras (R108): nunca un pedazo suyo.
        patron = re.compile(rf"(?<![A-Z0-9]){re.escape(tramo)}(?![A-Z0-9])")
        return any(patron.search(c) for c in citas if c)

    for residuo in residuos:
        escrito = _escrito(residuo, textos)
        if escrito is not None and not citado(escrito):
            perdidos.append((f"sin leer: «{escrito}»: ¿la marca {residuo} o varillas?", escrito))
            citas.append(escrito)
    for linea in textos:
        citar, tramos = tramos_de_armado(linea)
        for a, b in tramos:
            tramo = _plano(citar[a:b])
            clase = clase_de_tramo(tramo)
            if clase == "pieza" or citado(tramo):
                continue
            medidas = _SECTION_RE.search(tramo)
            if clase == "seccion" and section is not None and medidas is not None:
                leida = _lados(medidas)
                if family in FAMILIAS_QUE_SE_ORDENAN:
                    leida = (min(leida), max(leida))
                if leida == section and not _BLOCK_RE.search(tramo):
                    continue  # la sección leída (o una copia suya)
            if clase == "seccion" and not section_of_the_element:
                aviso = f"«{tramo}»: no es la sección del elemento (hueco, paso…): no se toma"
            else:
                aviso = f"sin leer: «{tramo}»"
            perdidos.append((aviso, tramo))
            citas.append(tramo)
    return perdidos


def _sin_la_marca(texto: str, marca: str) -> str:
    """``texto`` (as the parser quotes it) without the note's number and its own mark: only
    the grammar's occurrence of the mark — the first one outside the armado the parser
    recognises —, never another («V-4 20X40 V4#4»: V4#4 is 4 bars #4), R93."""
    citar, tramos = tramos_de_armado(texto)
    nota = _NUMERO_DE_NOTA.match(citar)
    patron = _patron_suelto(marca)
    if patron is not None:
        for m in patron.finditer(citar):
            if not any(a <= m.start() < b for a, b in tramos):
                citar = citar[: m.start()] + " " * (m.end() - m.start()) + citar[m.end() :]
                break
    if nota is not None:
        citar = " " * nota.end() + citar[nota.end() :]
    return citar


def _has_something(reading: dict, content: str) -> bool:
    """A family note is a reading when it gave a section or armado, or when an
    armado-shaped text in it could not be read (a note about holes whose only
    numbers are its own numbering is not an armado reading)."""
    if reading["section_cm"] is not None or not reading["armado"].vacio():
        return True
    return bool(reading["avisos"]) and (
        ARMADO_RE.search(content) is not None or tiene_armado(content)
    )


# ------------------------------------------- cuadro rows, stacks and notes


def _read_associations(
    entities: list[NormalizedEntity],
    frames: list[SheetFrame],
    config: TextPatternConfig,
    posibles: dict[str, set[str]] | None = None,
) -> tuple[list[ElementSpec], list[str], list[Rechazo], int]:
    """The cuadro rows and the stacks ``estructura.asociacion`` gives each
    mark, read through the parser: (specs, the labels that define a mark,
    the rejections, how many cuadros had rows read). A label that owns a
    stack or a row is a definition, never a placement. ``posibles`` gets, by
    text, the labels in whose column it lies past their stack's cut (R111)."""
    asociaciones, rechazos = asociar(entities, frames, config, posibles)
    sheet = hoja_y_llave(frames)
    by_id = {e.entity_id: e for e in entities}
    specs: list[ElementSpec] = []
    labels: list[str] = []
    for a in asociaciones:
        family = family_of_mark(a.marca)
        row = a.via == "fila"
        specs.append(
            ElementSpec(
                mark=a.marca,
                family=family,
                familia_supuesta=True,
                source="cuadro" if row else "detalle",
                metodo=a.via,
                hoja=a.hoja,
                hoja_llave=sheet(by_id[a.etiqueta_id])[1],
                entidades=list(a.entidades),
                source_text=f"{a.marca} · {' / '.join(a.textos)}",
                confidence=0.95 if row else 0.75,
                **_reading(a.textos, family),
            )
        )
        labels.append(a.etiqueta_id)
    tables = len({a.cuadro for a in asociaciones if a.via == "fila"})
    return specs, labels, rechazos, tables


# A hole's size is not the element's section. An object's («PLACA BASE 35X35») is R100's: the
# parser reports it with its object, and the element's section beside it is still read.
_NOT_A_SECTION = re.compile(r"HUECO|PASO|ABERTURA|HASTA|M[AÁ]X|PERFORACI", re.I)


def _section_is_the_elements(content: str) -> bool:
    """A family-level note names the element and then its section ("CADENA DE
    ENRASE 15x25"); a section preceded by hole/opening words is not one."""
    match = _SECTION_RE.search(content)
    if match is None:
        return False
    before = content[max(0, match.start() - 40) : match.start()]
    return not _NOT_A_SECTION.search(before)


def _parse_annotations(
    texts: list[NormalizedEntity],
    config: TextPatternConfig,
    sheet: Sheet,
) -> tuple[list[ElementSpec], list[Rechazo]]:
    """Notes: a text that names its mark ("K-1 15x20 4#3 E#2@20") or its
    family ("DALA 15x30 4#3,E#2@20", "CADENA DE BORDE" over "ARMEX 15X30"), read when it has a
    section, bars, a mesh or stirrups the parser reads (``lo_lee_una_nota``:
    the association reports the others as «sin lector»). Its mark comes from
    the one mark grammar (``leer_marcas``, R67), keyed as a label would be: a
    mark inside a reference ("… VER CORTE C-2") is not the note's, nor anyone's
    (R99); in a text with armado, a heading names its marks and the text is not
    read («CORTE K-1 15X20 4#3»: a «sin_lector» rejection of K-1, R97); a note naming
    several marks («K-1 Y K-2 15X20 4#3», «K-1 A K-4 …», «K-1-K-3 …») is a
    «varias_marcas» rejection with the marks as written (R63); a note whose
    mark is glued to something («T2-20X40», «K-7E#3@20 15X20», «K-1-3 4#3») is
    not read either: it is a «sin_lector» rejection naming every candidate.
    Bare armado lines are the association's, not a note's."""
    specs: list[ElementSpec] = []
    rechazos: list[Rechazo] = []
    for text in texts:
        content = " ".join((text.text or "").split())
        if not content:
            continue
        lee = lo_lee_una_nota(content)
        # R91: un texto con armado que el parser reconoce es candidato a nota, tenga «#» o no.
        if not lee and not tiene_armado(content):
            continue
        hoja, llave = sheet(text)
        lectura = leer_marcas(content, config)
        if lectura.tipo in ("varias", "ambigua"):
            if not lee:
                continue  # la asociación lo reporta: no se lee

            rechazos.append(
                Rechazo(
                    entidad_id=text.entity_id,
                    texto=(text.text or "").strip(),
                    hoja=hoja,
                    motivo="varias_marcas" if lectura.tipo == "varias" else "sin_lector",
                    marcas=lectura.piezas,
                )
            )
            continue
        mark = lectura.marca
        family = _family_in_text(content)
        if mark is not None:
            if not lee:
                continue  # nombra su marca y nadie lo lee: «sin_lector» de la asociación
            if lectura.titulo:
                # R97: el título de un corte («CORTE K-1 15X20 4#3») o una referencia con armado
                # nombra su marca, pero no se lee: es un rechazo con la marca que nombra.
                rechazos.append(
                    Rechazo(
                        entidad_id=text.entity_id,
                        texto=(text.text or "").strip(),
                        hoja=hoja,
                        motivo="sin_lector",
                        marcas=lectura.piezas,
                    )
                )
                continue
            supuesta = family is None
            family = family or family_of_mark(mark)
            specs.append(
                ElementSpec(
                    mark=mark,
                    family=family,
                    familia_supuesta=supuesta,
                    source="nota",
                    metodo="nota",
                    hoja=hoja,
                    hoja_llave=llave,
                    entidades=[text.entity_id],
                    source_text=content[:120],
                    confidence=0.8,
                    **_reading([content], family, sin_marca=mark, residuos=lectura.residuos),
                )
            )
        elif family is not None:
            # R83: a family note needs its family word as the subject; a family word in
            # another place («… ANCLADA AL MURO O CADENA …») is not a family reading. It is
            # reported, never dropped. R107: a line that is just the family's name («CADENA DE
            # DESPLANTE»), first or last, over armado lines is the family's label.
            family, families = _family_subject(content)
            frase = _frase_de_familia(text.text or "") if family is None else None
            if frase is not None:
                family, lineas = frase
                reading = _reading(lineas, family, _section_is_the_elements(" ".join(lineas)))
                specs.append(
                    ElementSpec(
                        mark=family.upper(),
                        family=family,
                        source="nota",
                        metodo="nota",
                        hoja=hoja,
                        hoja_llave=llave,
                        entidades=[text.entity_id],
                        source_text=content[:120],
                        confidence=0.6,
                        **reading,
                    )
                )
                continue
            if family is None:
                rechazos.append(
                    Rechazo(
                        entidad_id=text.entity_id,
                        texto=(text.text or "").strip(),
                        hoja=hoja,
                        motivo="sin_lector",
                        familias=families,
                    )
                )
                continue
            # "HUECOS DE HASTA 15X20 … CONTRATRABE": a hole, not the element's section.
            reading = _reading([content], family, _section_is_the_elements(content))
            if not _has_something(reading, content):
                continue
            specs.append(
                ElementSpec(
                    mark=family.upper(),
                    family=family,
                    source="nota",
                    metodo="nota",
                    hoja=hoja,
                    hoja_llave=llave,
                    entidades=[text.entity_id],
                    source_text=content[:120],
                    confidence=0.6,
                    **reading,
                )
            )
    return specs, rechazos


# ------------------------------------------------------------------ assembly

# Beam/column section drawings in details: a rectangle of real size (m)
# with the estribo drawn inside it (a concentric rectangle 1–8 cm in).
_SECTION_W_M = (0.10, 0.60)
_SECTION_H_M = (0.12, 1.20)
_STIRRUP_OFFSET_M = (0.01, 0.08)


def _sections_from_detail_geometry(
    entities: list[NormalizedEntity],
    config: TextPatternConfig,
    unit_to_m: float,
    detail_boxes: list[BBox],
    sheet: Sheet,
) -> list[ElementSpec]:
    """The detail convention without a cuadro: the mark sits right above a
    section drawn at real size (30×80 cm rectangle with its cotas). Only
    inside detail frames — a mark in a plan view has castillos beside it."""
    closed = [
        e
        for e in entities
        if e.entity_type == EntityType.polyline and e.is_closed and len(e.points or []) in (4, 5)
    ]
    rects: list[tuple[NormalizedEntity, float, float]] = []
    for e in closed:
        w = (e.bbox[2] - e.bbox[0]) * unit_to_m
        h = (e.bbox[3] - e.bbox[1]) * unit_to_m
        if not (_SECTION_W_M[0] <= w <= _SECTION_W_M[1]):
            continue
        if not (_SECTION_H_M[0] <= h <= _SECTION_H_M[1]):
            continue
        if h < 0.9 * w:
            continue  # sections are drawn deeper than wide (or square)
        x0, y0, x1, y1 = e.bbox
        lo, hi = _STIRRUP_OFFSET_M[0] / unit_to_m, _STIRRUP_OFFSET_M[1] / unit_to_m
        has_stirrup = any(
            lo <= o.bbox[0] - x0 <= hi
            and lo <= o.bbox[1] - y0 <= hi
            and lo <= x1 - o.bbox[2] <= hi
            and lo <= y1 - o.bbox[3] <= hi
            for o in closed
            if o is not e
        )
        if has_stirrup:
            rects.append((e, w, h))
    if not rects:
        return []
    specs: list[ElementSpec] = []
    for text in entities:
        if not text.is_textual or not text.text:
            continue
        content = text.text.strip()
        mark = marca_en_texto(content, config)
        if mark is None or len(content) > 8:
            continue
        center = bbox_center(text.bbox)
        if not any(bbox_contains_point(box, center) for box in detail_boxes):
            continue
        height = _alto_de_renglon(text, 1.0)
        best: tuple[float, float, float] | None = None
        for rect, w, h in rects:
            x0, y0, x1, y1 = rect.bbox
            # The mark is above the section, within its width (±one width),
            # and at most a few text heights away from its top edge.
            if not (x0 - (x1 - x0) <= center[0] <= x1 + (x1 - x0)):
                continue
            gap = center[1] - y1
            if gap < -height or gap > 6 * height:
                continue
            if best is None or gap < best[0]:
                best = (gap, w, h)
        if best is None:
            continue
        a, b = round(best[1] * 100), round(best[2] * 100)
        specs.append(
            ElementSpec(
                mark=mark,
                family=family_of_mark(mark),
                familia_supuesta=True,
                section_cm=(a, b),
                source="detalle",
                metodo="geometria",
                hoja=sheet(text)[0],
                hoja_llave=sheet(text)[1],
                entidades=[text.entity_id],
                campos_con_texto=["seccion"],
                source_text=f"{content} · sección dibujada {a}x{b} cm",
                confidence=0.7,
            )
        )
    return specs


_SECTION_LABEL_RE = re.compile(r"^SECCI[OÓ]N\s*(\d+)", re.I)
_BARE_SECTION_RE = re.compile(r"^(\d{2,3})\s*[xX×]\s*(\d{2,3})$")


def _sections_from_section_callouts(
    texts: list[NormalizedEntity],
    config: TextPatternConfig,
    detail_boxes: list[BBox],
    sheet: Sheet,
) -> list[ElementSpec]:
    """Elevation details: the mark titles the drawing at its top-left and the
    section cuts are called out along it as "SECCIÓN 1" over "30X80". A bare
    NNxNN with a SECCIÓN label beside it belongs to the nearest title that
    sits above-left of it in the same detail frame; with several cuts the
    largest section is kept and the range is said in the note."""

    def box_of(entity: NormalizedEntity) -> int | None:
        center = bbox_center(entity.bbox)
        for index, box in enumerate(detail_boxes):
            if bbox_contains_point(box, center):
                return index
        return None

    labels = [
        (bbox_center(t.bbox), int(m.group(1)))
        for t in texts
        if (m := _SECTION_LABEL_RE.match(" ".join((t.text or "").split())))
    ]
    marks = []
    for t in texts:
        content = (t.text or "").strip()
        mark = marca_en_texto(content, config)
        if mark is None or len(content) > 8:
            continue
        box = box_of(t)
        if box is not None:
            marks.append((mark, bbox_center(t.bbox), box, t))
    # Per mark and sheet: the cuts of one sheet are one reading, never mixed with another's.
    found: dict[tuple[str, str], list[tuple[int, tuple[int, int], str]]] = {}
    title_of: dict[tuple[str, str], NormalizedEntity] = {}
    cut_texts: dict[tuple[str, str], list[str]] = {}
    for t in texts:
        content = " ".join((t.text or "").split())
        match = _BARE_SECTION_RE.match(content)
        if match is None:
            continue
        box = box_of(t)
        if box is None:
            continue
        cx, cy = bbox_center(t.bbox)
        height = _alto_de_renglon(t, 0.1)
        label = min(
            ((abs(lx - cx) + abs(ly - cy), n) for (lx, ly), n in labels),
            default=(None, None),
        )
        if label[0] is None or label[0] > 8 * height:
            continue  # a bare NNxNN without a SECCIÓN label is something else
        best: tuple[float, str, NormalizedEntity] | None = None
        for mark, (mx, my), mbox, title in marks:
            if mbox != box:
                continue
            dx, dy = cx - mx, my - cy
            if not (-1.0 <= dx <= 30.0 and 0.0 <= dy <= 6.0):
                continue
            score = dx + 2 * dy
            if best is None or score < best[0]:
                best = (score, mark, title)
        if best is None:
            continue
        key = (best[1], sheet(best[2])[1])
        found.setdefault(key, []).append(
            (int(label[1]), (int(match.group(1)), int(match.group(2))), content)
        )
        title_of.setdefault(key, best[2])
        cut_texts.setdefault(key, []).append(t.entity_id)
    specs: list[ElementSpec] = []
    for (mark, llave), cuts in found.items():
        cuts.sort()
        largest = max(cuts, key=lambda c: c[1][0] * c[1][1])[1]
        listed = ", ".join(f"sección {n} {a}x{b}" for n, (a, b), _t in cuts)
        # Each cut not taken is quoted as written (R108): nothing is lost unsaid.
        citados = ", ".join(f"sección {n} «{t}»" for n, _ab, t in cuts)
        aviso = (
            [f"varios cortes con secciones distintas ({citados}): se toma la mayor"]
            if len({c[1] for c in cuts}) > 1
            else []
        )
        title = title_of[(mark, llave)]
        specs.append(
            ElementSpec(
                mark=mark,
                family=family_of_mark(mark),
                familia_supuesta=True,
                section_cm=largest,
                source="detalle",
                metodo="llamada",
                hoja=sheet(title)[0],
                hoja_llave=llave,
                entidades=[title.entity_id, *cut_texts[(mark, llave)]],
                campos_con_texto=["seccion"],
                avisos=aviso,
                source_text=f"{mark} · {listed} (se toma la mayor)"[:120],
                confidence=0.65,
            )
        )
    return specs


_COTA_DEPTH_CM = (12, 150)
_ARMADO_TEXT_RE = re.compile(r"\d\s*#\s*\d|#\s*\d\s*@\s*\d", re.I)


# The units a cota's displayed number can be in (metres per displayed unit): metres, centimetres,
# millimetres. A style factor that gives another (dimlfac 40 on a drawing in metres: «1 unidad =
# 2.5 cm», a detail scaled by its style) does not say the number's unit.
_UNIDADES_DE_COTA = (1.0, 0.01, 0.001)


def _unidad_mostrada(props: dict, unit_to_m: float) -> float | None:
    """Metres per unit of a dimension's displayed number: the drawing unit over the style's
    linear factor (dimlfac 100 on a drawing in metres: centimetres), when that is metres,
    centimetres or millimetres (or the factor is 1); otherwise not known (None). R151: where the
    factor does not fix it, the unit its group's note declares (``_con_unidad_declarada``); none
    when the notes of its group disagree."""
    if props.get("unidades_en_conflicto"):
        return None
    declarada = props.get("unidad_declarada")
    if isinstance(declarada, (int, float)):
        return float(declarada)
    dimlfac = props.get("dimlfac")
    if not isinstance(dimlfac, (int, float)) or dimlfac <= 0 or abs(dimlfac - 1.0) < 1e-9:
        return unit_to_m
    factor = unit_to_m / float(dimlfac)
    return next((u for u in _UNIDADES_DE_COTA if abs(factor - u) <= 0.01 * u), None)


def _cota_cm(entity: NormalizedEntity, unit_to_m: float) -> float | None:
    """A dimension's value in centimetres: the displayed number in its unit (the drawing unit
    over the style's dimlfac), else the measured length. A displayed number whose unit the
    style does not say (``_unidad_mostrada``) is no value: never converted by guess."""
    props = entity.properties or {}
    display = props.get("display_value")
    if isinstance(display, (int, float)) and display > 0:
        unidad = _unidad_mostrada(props, unit_to_m)
        # The displayed number as written, only scaled to centimetres: never rounded (R119).
        return float(_exacto(display) * _exacto(unidad) * 100) if unidad is not None else None
    measurement = props.get("measurement")
    if isinstance(measurement, (int, float)) and measurement > 0:
        return float(_exacto(measurement) * _exacto(unit_to_m) * 100)
    return None


def _sin_unidad(entity: NormalizedEntity, unit_to_m: float) -> str | None:
    """The aviso for a cota whose displayed number has no known unit (``_cota_cm`` is None)."""
    props = entity.properties or {}
    display = props.get("display_value")
    if not isinstance(display, (int, float)) or _unidad_mostrada(props, unit_to_m) is not None:
        return None
    texto = props.get("display_text") or f"{display:g}"
    if props.get("unidades_en_conflicto"):
        return (
            f"cota «{texto}»: las notas de unidad de su grupo no coinciden "
            f"({props['unidades_en_conflicto']}): no se toma"
        )
    paso = unit_to_m / float(props["dimlfac"]) * 100.0
    return (
        f"cota «{texto}» con un factor de escala que no dice su unidad (1 unidad = {paso:g} cm): "
        "no se toma"
    )


# R151: a note that declares the unit of its group's cotas: «ACOTACIONES EN CMS, SIN ESCALA»,
# «(ACOTACIONES EN CMS, S/E)», «ACOTACIONES EN MMS», «ACOTACIONES EN CENTIMETROS, NIVELES EN
# METROS», «ACOTACIONES Y NIVELES EN METROS, EXCEPTO INDICADOS».
_NOTA_DE_UNIDAD = re.compile(
    r"ACOTACION(?:ES)?(?:\s+Y\s+NIVELES)?\s+EN\s+"
    r"(CENT[IÍ]METROS|CMS?|MIL[IÍ]METROS|MMS?|METROS|MTS?)\b",
    re.IGNORECASE,
)
# A cota's group is its title's (the nearest mark label, within the reach of a section from it:
# ``_ALCANCE + _TAMANO`` of its heights). A group's note is written under it, with its heading
# (Marina: «CERRAMIENTOS» / «ACOTACIONES EN CMS, SIN ESCALA» under CR-1…CR-3; «COLUMNAS
# METÁLICAS» / «… EN MMS» beside it, under CM-1): the title's note is in the nearest row of unit
# notes below it, within this many of the note's own heights down and across (Marina: 28 under
# the CR, 54 under ES-300's CI; PRUEBA-1's general notes lie above its details, and its «EN
# METROS, EXCEPTO INDICADOS» 140 below T-11), and of that row the one horizontally nearest the
# title.
_NOTA_DEL_GRUPO = 60.0
# Notes in one row: their centres this many note heights apart vertically, at most.
_MISMA_FILA = 2.0
# Two notes of different units about as near the title along the row (the second within 10 % or
# both over it): its group is not told apart, and its cotas are refused (R151).
_NOTAS_EMPATADAS = 1.10
# R174: a group's note is a caption, «ACOTACIONES EN CMS, SIN ESCALA» or «(ACOTACIONES EN CMS,
# S/E)», written under its group's heading. A numbered note («1.- ACOTACIONES Y NIVELES EN METROS,
# EXCEPTO INDICADOS», the first of PRUEBA-1's NOTAS GENERALES beside PLANTA BAJA) or one inside a
# longer text (a pile's specifications) is the sheet's or a plan view's general note: it never
# scopes a detail's cotas.
_NOTA_DE_GRUPO = re.compile(r"\s*\(?\s*ACOTACION", re.IGNORECASE)
# R174: a group note's heading is the text written right over it, across it, its bottom within
# this many of the note's heights above the note's top (Marina: «COLUMNAS METÁLICAS» over «… EN
# MMS», «CERRAMIENTOS» over «… EN CMS», «DADO D-1» over its note: 2.2 to 3.3).
_SOBRE_LA_NOTA = 3.5


def _unidad_de_nota(texto: str) -> float | None:
    """Metres per unit of the cotas a unit note declares (None if it declares none)."""
    m = _NOTA_DE_UNIDAD.search(texto)
    if m is None:
        return None
    unidad = m.group(1).upper()
    if unidad.startswith("C"):
        return 0.01
    if unidad.startswith("MI") or unidad.startswith("MM"):
        return 0.001
    return 1.0


def _fija_su_unidad(props: dict, unit_to_m: float) -> bool:
    """Whether a dimension's style factor fixes its displayed number's unit: a factor other than
    1 that gives metres, centimetres or millimetres (dimlfac 100 on a drawing in metres). A
    factor of 1 says nothing (Marina's CR depth «20»), nor one that is a scale (dimlfac 40)."""
    dimlfac = props.get("dimlfac")
    if not isinstance(dimlfac, (int, float)) or dimlfac <= 0 or abs(dimlfac - 1.0) < 1e-9:
        return False
    factor = unit_to_m / float(dimlfac)
    return any(abs(factor - u) <= 0.01 * u for u in _UNIDADES_DE_COTA)


def _con_unidad_declarada(
    dims: list[NormalizedEntity],
    entities: list[NormalizedEntity],
    unit_to_m: float,
    config: TextPatternConfig,
) -> list[NormalizedEntity]:
    """R151, R174: a unit note («ACOTACIONES EN CMS, SIN ESCALA») declares the unit of its OWN
    detail group's cotas, and only where the style factor does not fix it (``_fija_su_unidad``).
    A cota's group is the nearest group heading of any kind, within a section's reach: a mark
    label, or the heading a group note is written under (``_encabezados``: «COLUMNAS METÁLICAS»
    over «… EN MMS»). A heading's note is the one under it; a mark title's is the one written
    under its group (``_nota_del_grupo``), never across another group's heading. On Marina ES-200
    the cotas of CM-1 (not a mark) lie nearer «COLUMNAS METÁLICAS» than the CR-1 title: millimetres,
    not centimetres; the CR-1 cota lies as near the «EN MMS» note as to its own «EN CMS», and the
    title of the CI for 15 cm walls is nearer that «EN MMS» than to its own «EN CMS» under
    «CADENAS INTERMEDIAS»; by rows below each title both find their own. Only a group's caption
    is a group note (``_NOTA_DE_GRUPO``): a numbered general note — PRUEBA-1's «1.- ACOTACIONES Y
    NIVELES EN METROS», beside PLANTA BAJA — never scopes a detail's cotas. One note: its unit
    (``unidad_declarada``, on a copy of the dimension). Two of different units about as near
    (``_NOTAS_EMPATADAS``): the cota is refused (``unidades_en_conflicto``) and its section
    claimed. No note: as the factor says."""
    notas: list[tuple[BBox, tuple[float, float], float, float]] = []
    for e in entities:
        if not e.is_textual or not e.text or not _NOTA_DE_GRUPO.match(e.text):
            continue
        unidad = _unidad_de_nota(e.text)
        if unidad is not None:
            notas.append((e.bbox, bbox_center(e.bbox), alto_de_texto(e), unidad))
    sueltas = [
        d
        for d in dims
        if not _fija_su_unidad(d.properties or {}, unit_to_m)
        and len((d.properties or {}).get("measured_segment") or []) == 2
    ]
    if not notas or not sueltas:
        return dims
    titulos = [
        e
        for e in entities
        if e.is_textual
        and e.text
        and len(e.text.strip()) <= 8
        and marca_en_texto(e.text.strip(), config) is not None
    ]
    encabezados = _encabezados(entities, notas)
    # Each heading: its centre, height, and its note (a heading's) or None (a mark title's).
    grupos: list[tuple[tuple[float, float], float, str, dict | None]] = [
        (bbox_center(t.bbox), alto_de_texto(t), t.entity_id, None) for t in titulos
    ]
    grupos += [
        (bbox_center(caja), alto, f"encabezado:{k}", {"unidad_declarada": u})
        for k, (caja, alto, u, _nota) in enumerate(encabezados)
    ]
    if not grupos:
        return dims
    cajas = [(caja, nota) for caja, _alto, _u, nota in encabezados]
    de_grupo: dict[str, dict] = {}
    extra: dict[str, dict] = {}
    for d in sueltas:
        p, q = d.properties["measured_segment"]
        medio = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        distancia, (centro, alto, clave, suya) = min(
            ((math.dist(medio, g[0]), g) for g in grupos), key=lambda x: (x[0], x[1][2])
        )
        if distancia > (_ALCANCE + _TAMANO) * alto:
            continue
        if clave not in de_grupo:
            de_grupo[clave] = suya if suya is not None else _nota_del_grupo(centro, notas, cajas)
        if de_grupo[clave]:
            extra[d.entity_id] = de_grupo[clave]
    if not extra:
        return dims
    return [
        d.model_copy(update={"properties": {**(d.properties or {}), **extra[d.entity_id]}})
        if d.entity_id in extra
        else d
        for d in dims
    ]


def _encabezados(
    entities: list[NormalizedEntity], notas: list[tuple[BBox, tuple[float, float], float, float]]
) -> list[tuple[BBox, float, float, BBox]]:
    """R174: the headings group notes are written under — for each, the nearest text over it
    (``_SOBRE_LA_NOTA``), across it, that is no unit note — with its height, its note's unit and
    its note's box."""
    textos = [e for e in entities if e.is_textual and e.text and _unidad_de_nota(e.text) is None]
    salida: list[tuple[BBox, float, float, BBox]] = []
    for caja, _centro, alto, unidad in notas:
        encima = [
            t
            for t in textos
            if t.bbox[1] >= caja[3] - 0.2 * alto
            and t.bbox[1] - caja[3] <= _SOBRE_LA_NOTA * alto
            and t.bbox[0] < caja[2]
            and t.bbox[2] > caja[0]
        ]
        if encima:
            t = min(encima, key=lambda e: (e.bbox[1], e.entity_id))
            salida.append((t.bbox, alto_de_texto(t), unidad, caja))
    return salida


def _nota_del_grupo(
    centro: tuple[float, float],
    notas: list[tuple[BBox, tuple[float, float], float, float]],
    encabezados: list[tuple[BBox, BBox]] | None = None,
) -> dict:
    """R151: what the unit note of a title's group declares: of the unit notes below the title
    and beside it (each within ``_NOTA_DEL_GRUPO`` of the note's heights, down and across), the
    nearest row, and of it the note horizontally nearest the title (0 when the title is over it):
    ``{"unidad_declarada": u}``, or ``{"unidades_en_conflicto": "cm, mm"}`` when two of different
    units are about as near, or nothing. R174: never across another group's heading — a heading
    (``encabezados``: its box and its note's) between the title and that row, over the title's
    column, that is not the heading of a note in that row, is another group's: then nothing."""

    def de_lado(n: tuple[BBox, tuple[float, float], float, float]) -> float:
        return max(n[0][0] - centro[0], 0.0, centro[0] - n[0][2])

    debajo = [
        n
        for n in notas
        if n[1][1] < centro[1]
        and centro[1] - n[1][1] <= _NOTA_DEL_GRUPO * n[2]
        and de_lado(n) <= _NOTA_DEL_GRUPO * n[2]
    ]
    if not debajo:
        return {}
    arriba = max(n[1][1] for n in debajo)
    fila = [n for n in debajo if arriba - n[1][1] <= _MISMA_FILA * n[2]]
    cerca = sorted((de_lado(n), n[3], n) for n in fila)
    d0, u0, n0 = cerca[0]
    # The headings of the row's notes lie right over them; another one between the title and the
    # row, over the title's column, is another group's.
    de_la_fila = {n[0] for n in fila}
    for caja, nota in encabezados or []:
        if nota in de_la_fila:
            continue
        if arriba < bbox_center(caja)[1] < centro[1] and caja[0] <= centro[0] <= caja[2]:
            return {}
    empatadas = {u for dx, u, _n in cerca if dx <= _NOTAS_EMPATADAS * d0}
    if len(empatadas) > 1:
        return {
            "unidades_en_conflicto": ", ".join(
                {1.0: "m", 0.01: "cm", 0.001: "mm"}[u] for u in sorted(empatadas, reverse=True)
            )
        }
    return {"unidad_declarada": u0}


_COTA_CM = (_MIN_SIDE_CM, _MAX_SIDE_CM)  # a section side read from a cota: 8–400 cm
# The section of a cuadro or detail label is ITS OWN drawn section (R81): the closed outline
# nearest the label on the side the sheet's convention puts it, covering the label's centre.
# Distances go in label heights, so they hold in any drawing unit.
_ALCANCE = 12.0  # from the label to the near edge of its section
_TAMANO = 35.0  # a section's larger side is at most this: a bigger outline is a frame or a table
_UNE = 0.01  # two chain ends this close are one point
_SOBRE_ARISTA = 0.05  # a dimension's definition point this close to an edge lies on it
_DUPLICADA = 0.25  # the same label drawn twice: one label
# R120: of two labels over one section (or two sections under one title), the larger overlap wins
# only by this margin (as R54); otherwise neither.
_MARGEN = 1.25
# R123: a title owns only a section at least this share of its text lies over.
_ENCIMA_MINIMO = 1 / 3
# R165: the same for a claimed box of cotas (R158), which only attributes armado.
_ENCIMA_RECLAMADA = 1 / 4
# R164: a title whose text ends this close (in its heights, R115's tolerance) to the edge two
# dimensioned pieces share stands at their boundary: which one is its own section is not known.
_EN_LA_JUNTA = 0.5
# R123: an outline without cotas is a section only when it looks like one: four corners, both
# sides at least this many title heights, and no longer than this many times its width.
_LADO_MINIMO = 1.5
_ESBELTEZ_MAXIMA = 8.0
_CUADRADA = 0.02  # an outline whose sides differ less than this (relative) is drawn square
# A drawn section agrees with its cotas when each side is within 2 cm or 10 % of its cota (R112):
# a cuadro not drawn to scale is not a second reading.
_COINCIDE_CM, _COINCIDE_PARTE = 2.0, 0.10
# R106: without a closed outline, the rectangle of one horizontal and one vertical cota that
# share a corner is the section when the drawing draws at least 3 of its 4 edges, each at least
# half its length.
_ARISTAS_DIBUJADAS = 3
_CUBIERTA = 0.5
# R118: and at least 2 of those drawn edges stop at its corners; no line crosses it edge to edge.
_ESQUINAS = 2


def _cm(valor: float) -> int | float:
    """A side in centimetres as the drawing gives it: whole, or with its decimals (72.5, 41.55),
    never rounded (R106, R119)."""
    v = float(valor)
    return int(v) if v.is_integer() else v


def _exacto(valor: float) -> Decimal:
    """A number as it was written (``repr``: 41.55 is 41.55), to add and scale cotas without the
    binary noise of a float (R119)."""
    return Decimal(repr(float(valor)))


@dataclass
class _Contorno:
    """A closed outline: polylines and lines joined end to end."""

    puntos: list[tuple[float, float]]
    entidades: list[str]

    @property
    def caja(self) -> BBox:
        xs = [x for x, _ in self.puntos]
        ys = [y for _, y in self.puntos]
        return (min(xs), min(ys), max(xs), max(ys))


def _contornos(segmentos: list[NormalizedEntity], une: float) -> list[_Contorno]:
    """The closed outlines the segments draw (``une``: how close two chain ends must be to be
    one point). A closed polyline is one; open polylines and lines are joined end to end, and a
    chain that comes back to its start is closed. Where three or more ends meet nothing is
    joined (a T is not an outline)."""

    def clave(p: tuple[float, float]) -> tuple[int, int]:
        return (round(p[0] / une), round(p[1] / une))

    cerrados: list[_Contorno] = []
    vivas: dict[int, tuple[list[tuple[float, float]], list[str]]] = {}
    for e in segmentos:
        puntos = [(float(x), float(y)) for x, y in (e.points or [])]
        if len(puntos) < 2:
            continue
        if e.is_closed and clave(puntos[0]) != clave(puntos[-1]):
            puntos.append(puntos[0])
        if clave(puntos[0]) == clave(puntos[-1]):
            if len(puntos) >= 4:
                cerrados.append(_Contorno(puntos=puntos, entidades=[e.entity_id]))
            continue
        vivas[len(vivas)] = (puntos, [e.entity_id])
    extremos: dict[tuple[int, int], set[int]] = defaultdict(set)
    for i, (puntos, _ids) in vivas.items():
        extremos[clave(puntos[0])].add(i)
        extremos[clave(puntos[-1])].add(i)
    siguiente = len(vivas)
    pendientes = [k for k, ids in extremos.items() if len(ids) == 2]
    while pendientes:
        k = pendientes.pop()
        ids = extremos.get(k, set())
        if len(ids) != 2:
            continue
        a, b = sorted(ids)
        (pa, ea), (pb, eb) = vivas.pop(a), vivas.pop(b)
        for i, puntos in ((a, pa), (b, pb)):
            extremos[clave(puntos[0])].discard(i)
            extremos[clave(puntos[-1])].discard(i)
        if clave(pa[-1]) != k:
            pa = pa[::-1]
        if clave(pb[0]) != k:
            pb = pb[::-1]
        unida = pa + pb[1:]
        if clave(unida[0]) == clave(unida[-1]):
            if len(unida) >= 4:
                cerrados.append(_Contorno(puntos=unida, entidades=ea + eb))
            continue
        vivas[siguiente] = (unida, ea + eb)
        for punta in (clave(unida[0]), clave(unida[-1])):
            extremos[punta].add(siguiente)
            if len(extremos[punta]) == 2:
                pendientes.append(punta)
        siguiente += 1
    return cerrados


def _esquinas(puntos: list[tuple[float, float]], une: float) -> list[tuple[float, float]]:
    """The corners of a closed outline: its vertices without repeated points or points where
    the direction does not change."""
    distintos: list[tuple[float, float]] = []
    for p in puntos[:-1]:
        if not distintos or math.dist(p, distintos[-1]) > une:
            distintos.append(p)
    if len(distintos) > 1 and math.dist(distintos[0], distintos[-1]) <= une:
        distintos.pop()
    esquinas = []
    for i, p in enumerate(distintos):
        a, b = distintos[i - 1], distintos[(i + 1) % len(distintos)]
        cruz = (p[0] - a[0]) * (b[1] - p[1]) - (p[1] - a[1]) * (b[0] - p[0])
        if abs(cruz) > une * une:
            esquinas.append(p)
    return esquinas


def _es_rectangulo(esquinas: list[tuple[float, float]], une: float) -> bool:
    return len(esquinas) == 4 and all(
        abs(a[0] - b[0]) <= une or abs(a[1] - b[1]) <= une
        for a, b in zip(esquinas, esquinas[1:] + esquinas[:1], strict=True)
    )


def _area(puntos: list[tuple[float, float]]) -> float:
    return (
        abs(
            sum(
                puntos[i][0] * puntos[i + 1][1] - puntos[i + 1][0] * puntos[i][1]
                for i in range(len(puntos) - 1)
            )
        )
        / 2
    )


def _en_arista(p: tuple[float, float], puntos: list[tuple[float, float]], tol: float) -> bool:
    for (ax, ay), (bx, by) in zip(puntos, puntos[1:], strict=False):
        dx, dy = bx - ax, by - ay
        largo = dx * dx + dy * dy
        if largo == 0:
            continue
        t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / largo))
        if math.hypot(ax + t * dx - p[0], ay + t * dy - p[1]) <= tol:
            return True
    return False


@dataclass
class _Etiqueta:
    """A label the cotas reader considers: its text, mark, the box its text really takes (R120:
    alignment-aware, ``caja_de_texto``) and its centre, its height and sheet."""

    texto: NormalizedEntity
    marca: str
    x: float
    y: float
    alto: float
    llave: str
    en_detalle: bool
    x0: float = 0.0
    x1: float = 0.0
    y0: float = 0.0
    y1: float = 0.0
    # R130: the family its own title's family word states («DADO\nD-3»), if any.
    familia: str | None = None


@dataclass
class _Propio:
    """A label's own outline, or why it has none (and which other labels reach the same)."""

    contorno: _Contorno | None
    por_que: str = ""
    otras: list[str] = campo_de_dataclass(default_factory=list)
    # No outline at all where its section goes (not two, not shared): a pair of cotas may draw it.
    sin_contorno: bool = False
    # Its title spans two sections side by side and neither is clearly its own (R120): claimed.
    dudosa: bool = False
    # R129: the gap to the nearest closed outline on its side, which is not a section: the title
    # reaches nothing past it (a pair of cotas nearer than it may still be its section).
    tope: float | None = None
    # R150: that nearest outline is not a rectangle (K-15A's L): its section is not rectangular.
    no_rectangular: bool = False
    # R158: the drawn sections it claims without owning them (one it shares with another title,
    # R111; the two its title lies over, R120): their armado may be its.
    reclamados: list[BBox] = campo_de_dataclass(default_factory=list)


def _alto_de_renglon(text: NormalizedEntity, defecto: float) -> float:
    """The height of one line of a text: its letters' (R146: its box is its real extent — several
    lines of a MTEXT, a turned text's length — never its height), or its box's for a text built
    without one; ``defecto`` when neither has any."""
    alto = text.properties.get("height")
    if isinstance(alto, int | float) and alto > 0:
        return float(alto)
    caja = bbox_height(text.bbox)
    return caja if caja > 0 else defecto


def _extension_del_texto(text: NormalizedEntity) -> BBox:
    """Where a label's text really lies (R120): its extent as the normalizer gives it (R146,
    ``text_extent``) — placed where its alignment puts it and turned with it; a text built
    without an insert point lies in its box."""
    return extension_de_texto(text)


def _parece_seccion(c: _Contorno, alto_letra: float, une: float) -> bool:
    """R123: an outline that looks like a section: four corners, both sides at least
    ``_LADO_MINIMO`` title heights, and its longer side at most ``_ESBELTEZ_MAXIMA`` times the
    shorter (a sliver, a wall strip, an octagon or a symbol does not)."""
    x0, y0, x1, y1 = c.caja
    corto, largo = sorted((x1 - x0, y1 - y0))
    return (
        _es_rectangulo(_esquinas(c.puntos, une), une)
        and corto >= _LADO_MINIMO * alto_letra * (1 - 1e-6)  # R129: float noise
        and largo <= _ESBELTEZ_MAXIMA * corto
    )


# R124: the text a title a leader points from claims instead of a section nobody reads.
_SENALADA = "señalada por flecha; se lee en E3"
# R150: the nearest outline a title owns is not a rectangle (K-15A's L).
_NO_RECTANGULAR = "sección: la dibujada no es un rectángulo"
# The beam families: a leader claim's parrillas are dropped when the definition's final family,
# stated, is one of them (R150, R155).
FAMILIAS_DE_VIGA = frozenset({"trabe", "contratrabe", "dala", "cerramiento"})
# A leader starts or lands this close to a title's text and reaches this far from it (in title
# heights): the association's thresholds for a «llamada» (R52).
_PUNTA_DE_FLECHA = 0.6
_LARGO_DE_FLECHA = 2.0


def _distancia_tramo_caja(p: tuple[float, float], q: tuple[float, float], caja: BBox) -> float:
    """How far the segment ``p``–``q`` passes from the box (0 when it touches or crosses it)."""
    x0, y0, x1, y1 = caja

    def a_la_caja(r: tuple[float, float]) -> float:
        return math.hypot(max(x0 - r[0], 0.0, r[0] - x1), max(y0 - r[1], 0.0, r[1] - y1))

    def al_tramo(r: tuple[float, float]) -> float:
        dx, dy = q[0] - p[0], q[1] - p[1]
        largo = dx * dx + dy * dy
        t = (
            0.0
            if largo == 0
            else max(0.0, min(1.0, ((r[0] - p[0]) * dx + (r[1] - p[1]) * dy) / largo))
        )
        return math.dist(r, (p[0] + t * dx, p[1] + t * dy))

    if (
        min(p[0], q[0]) <= x1
        and max(p[0], q[0]) >= x0
        and min(p[1], q[1]) <= y1
        and max(p[1], q[1]) >= y0
    ):
        # Its box meets the box: it crosses it unless it passes beside a corner.
        pasos = 16
        if any(
            a_la_caja((p[0] + (q[0] - p[0]) * k / pasos, p[1] + (q[1] - p[1]) * k / pasos)) == 0
            for k in range(pasos + 1)
        ):
            return 0.0
    esquinas = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    return min(a_la_caja(p), a_la_caja(q), *(al_tramo(r) for r in esquinas))


class _Abiertas:
    """The leaders among the open polylines near the titles (R124, R128), by the grid cells
    their landing runs through: a LEADER or a MULTILEADER (open polylines from the normalizer,
    from the arrow tip to the landing: only the last segment is the landing, and a two-point
    leader lands only at its last point — the tip is what it points at, never its title, R136),
    or one drawn as an open polyline of three vertices — a horizontal landing and a slanted
    segment to what it points at."""

    def __init__(self, lineas: list[NormalizedEntity], celda: float, tol: float) -> None:
        self.celda = max(celda, 1e-6)
        self.apoyos: list[tuple[NormalizedEntity, list[tuple[float, float]], tuple[int, int]]] = []
        self.rejilla: dict[tuple[int, int], list[int]] = defaultdict(list)
        for linea in lineas:
            puntos = [(float(q[0]), float(q[1])) for q in linea.points or []]
            if len(puntos) < 2:
                continue
            if linea.properties.get("derived_from") in ("LEADER", "MULTILEADER"):
                ultimo = len(puntos) - 1
                tramos = [(ultimo - 1, ultimo) if ultimo >= 2 else (ultimo, ultimo)]
            elif len(puntos) == 3:
                tramos = [
                    (1, c)
                    for a, c in ((0, 2), (2, 0))
                    if abs(puntos[c][1] - puntos[1][1]) <= tol < abs(puntos[c][0] - puntos[1][0])
                    and abs(puntos[a][0] - puntos[1][0]) > tol
                    and abs(puntos[a][1] - puntos[1][1]) > tol
                ]
            else:
                continue
            for tramo in dict.fromkeys(tramos):
                (ax, ay), (bx, by) = puntos[tramo[0]], puntos[tramo[1]]
                n = len(self.apoyos)
                self.apoyos.append((linea, puntos, tramo))
                for i in range(int(min(ax, bx) // self.celda), int(max(ax, bx) // self.celda) + 1):
                    for j in range(
                        int(min(ay, by) // self.celda), int(max(ay, by) // self.celda) + 1
                    ):
                        self.rejilla[(i, j)].append(n)

    def flecha_de(self, caja: BBox, alto: float) -> NormalizedEntity | None:
        """The leader whose landing runs under, meets or crosses the title's real text (R128: the
        whole landing segment, within ``_PUNTA_DE_FLECHA`` heights, not only its end) and that
        reaches ``_LARGO_DE_FLECHA`` heights or more away from it. Where it points is not read
        (E3)."""
        punta = _PUNTA_DE_FLECHA * alto
        x0, y0, x1, y1 = caja
        vistos: set[int] = set()
        for i in range(int((x0 - punta) // self.celda), int((x1 + punta) // self.celda) + 1):
            for j in range(int((y0 - punta) // self.celda), int((y1 + punta) // self.celda) + 1):
                for n in self.rejilla.get((i, j), ()):
                    if n in vistos:
                        continue
                    vistos.add(n)
                    linea, puntos, (a, b) = self.apoyos[n]
                    if _distancia_tramo_caja(puntos[a], puntos[b], caja) <= punta and any(
                        _distancia_tramo_caja(q, q, caja) >= _LARGO_DE_FLECHA * alto for q in puntos
                    ):
                        return linea
        return None


# R128: a title, for a leader's claim, is a text made only of family words, marks and connectors
# («DADO\nD-1A», «DADO D-1B / O D-1C», «PILOTE\nP-3»), of any length; its family word states the
# family of its marks (R130).
_PALABRAS_DE_FAMILIA: list[tuple[str, re.Pattern[str]]] = [
    ("dado", re.compile(r"DADOS?")),
    ("pilote", re.compile(r"PILOTES?")),
    ("castillo", re.compile(r"CASTILLOS?")),
    ("columna", re.compile(r"COLUMNAS?")),
    ("contratrabe", re.compile(r"CONTRATRABES?")),
    ("trabe", re.compile(r"TRABES?")),
    ("dala", re.compile(r"DALAS?|CADENAS?")),
    ("zapata", re.compile(r"ZAPATAS?")),
    ("muro", re.compile(r"MUROS?")),
    ("losa", re.compile(r"LOSAS?")),
    ("cerramiento", re.compile(r"CERRAMIENTOS?")),
]
_CONECTORES = frozenset({"O", "Y", "E", "U", "&", "-"})


def _familia_de_titulo(familia: str | None, marca: str) -> str | None:
    """The family a title's word states for ``marca`` (R130); «MURO» over a muro de concreto
    (MC-1) says what its prefix says, more precisely."""
    if familia == "muro" and family_of_mark(marca) == "muro_concreto":
        return "muro_concreto"
    return familia


def _titulo(texto: str, config: TextPatternConfig) -> tuple[list[str], str | None] | None:
    """The marks of a title made only of family words, marks and connectors (R128), and the
    family its family word states (R130); None if any word is something else."""
    marcas: list[str] = []
    familia: str | None = None
    for ficha in re.split(r"[\s/,;:()]+", texto.upper()):
        if not ficha or ficha in _CONECTORES:
            continue
        de_familia = next(
            (f for f, patron in _PALABRAS_DE_FAMILIA if patron.fullmatch(ficha)), None
        )
        if de_familia is not None:
            familia = familia or de_familia
            continue
        marca = marca_sola(ficha, config)
        if marca is None:
            return None
        marcas.append(marca)
    return (list(dict.fromkeys(marcas)), familia) if marcas else None


def _solape(e: _Etiqueta, c: _Contorno) -> float:
    """How much of the label's text lies over the outline (R120): the part of its extent within
    the outline's x-range, as a share of the extent — a wide title is not more over a section
    than a short one lying wholly over it."""
    return (min(e.x1, c.caja[2]) - max(e.x0, c.caja[0])) / max(e.x1 - e.x0, 1e-9)


_Q = TypeVar("_Q")


def _por_solape(quienes: list[tuple[float, _Q]]) -> _Q | None:
    """Of overlaps and whose they are, the one with the larger overlap, if larger by
    ``_MARGEN`` (R120, as R54); otherwise none."""
    orden = sorted(quienes, key=lambda q: -q[0])
    if len(orden) == 1 or orden[0][0] >= _MARGEN * orden[1][0]:
        return orden[0][1]
    return None


def _propio(
    etiquetas: list[_Etiqueta],
    contornos: list[_Contorno],
    es_seccion: Callable[[_Contorno, _Etiqueta], bool] | None = None,
    topes: dict[str, float] | None = None,
    encima_minimo: float = _ENCIMA_MINIMO,
) -> dict[str, _Propio]:
    """Each label's own outline (R81), by its entity id, with why there is none. An outline (or
    pair rectangle) is a label's when the label's text really lies over it (R120: its
    alignment-aware extent overlaps the outline's x-range by at least ``_ENCIMA_MINIMO`` of the
    text, R123; never an anchor or an estimated centre), it is a section (``es_seccion``, R123,
    R129: a sliver, a wall strip, an octagon, a symbol, a trapezoid or a rotated outline is
    not), it is the nearest closed outline on the side its sheet's convention puts the section,
    within reach — a title never reaches past the nearest one, section or not (R129; ``topes``
    bounds a label's reach for the pairs of cotas) — and no other label lies over it as much: of
    two labels nearest one outline, the larger overlap wins only by ``_MARGEN`` (as R54);
    otherwise it is both labels' and neither's (claimed, ``otras``). A title over two sections
    side by side at that distance takes the one it overlaps clearly more, else neither (claimed,
    ``dudosa``); one another label clearly owns is not among them. The convention is the side
    (above or below the label) on which more labels of the sheet own an outline."""
    por_hoja: dict[str, list[_Etiqueta]] = defaultdict(list)
    for e in etiquetas:
        por_hoja[e.llave].append(e)
    salida: dict[str, _Propio] = {}
    for grupo in por_hoja.values():
        # The same label drawn twice at the same place is one claimant.
        representantes: list[_Etiqueta] = []
        de: dict[str, _Etiqueta] = {}
        for e in grupo:
            igual = next(
                (
                    r
                    for r in representantes
                    if r.marca == e.marca
                    and math.dist((r.x, r.y), (e.x, e.y)) <= _DUPLICADA * e.alto
                ),
                None,
            )
            if igual is None:
                representantes.append(e)
                igual = e
            de[e.texto.entity_id] = igual

        def hueco(e: _Etiqueta, c: _Contorno, lado: int) -> float | None:
            """The gap from the label to the outline on ``lado``, if its text lies over it."""
            x0, y0, x1, y1 = c.caja
            if _solape(e, c) < encima_minimo or max(x1 - x0, y1 - y0) > _TAMANO * e.alto:
                return None
            h = y0 - e.y if lado > 0 else e.y - y1
            tope = (topes or {}).get(e.texto.entity_id, math.inf)
            return h if 0 < h <= _ALCANCE * e.alto and h < tope else None

        def mas_cercanos(
            e: _Etiqueta, lado: int
        ) -> tuple[list[_Contorno], float | None, _Contorno | None]:
            """The sections nearest the label on ``lado`` that its text lies over: one, or
            several side by side at that distance (of outlines one inside another, the
            largest); or none, with its gap, when the nearest closed outline is not a section
            (R129: the title does not reach past it) — and that outline when it alone is the
            nearest and is not a rectangle (K-15A's L, R150)."""
            candidatos = [(h, c) for c in contornos if (h := hueco(e, c, lado)) is not None]
            if not candidatos:
                return [], None, None
            minimo = min(h for h, _c in candidatos)
            cerca = sorted(
                (
                    c
                    for h, c in candidatos
                    if h - minimo <= _SOBRE_ARISTA * e.alto
                    and (es_seccion is None or es_seccion(c, e))
                ),
                key=lambda c: -_area(c.puntos),
            )
            if not cerca:
                une = _UNE * e.alto
                junto = [c for h, c in candidatos if h - minimo <= _SOBRE_ARISTA * e.alto]
                torcido = (
                    junto[0]
                    if len(junto) == 1 and not _es_rectangulo(_esquinas(junto[0].puntos, une), une)
                    else None
                )
                return [], minimo, torcido
            aparte: list[_Contorno] = []
            for c in cerca:
                if all(min(c.caja[2], o.caja[2]) - max(c.caja[0], o.caja[0]) <= 0 for o in aparte):
                    aparte.append(c)
            return aparte, None, None

        def resolver(lado: int, representantes: list[_Etiqueta]) -> dict[int, _Propio | None]:
            """Each label's outline on ``lado`` (None: it finds none there)."""
            vistos = {id(r): mas_cercanos(r, lado) for r in representantes}
            cercanos = {clave: v[0] for clave, v in vistos.items()}
            quienes: dict[int, list[_Etiqueta]] = defaultdict(list)
            for r in representantes:
                for c in cercanos[id(r)]:
                    quienes[id(c)].append(r)
            gana: dict[int, _Etiqueta | None] = {}
            for r in representantes:
                for c in cercanos[id(r)]:
                    if id(c) not in gana:
                        gana[id(c)] = _por_solape([(_solape(o, c), o) for o in quienes[id(c)]])
            # R156: a non-rectangular outline says its title's section is not a rectangle only when
            # it is that title's own, by the rule of a section's (no other label lies over it as
            # much); one another title shares or wins says nothing of this one.
            torcidos: dict[int, list[_Etiqueta]] = defaultdict(list)
            for r in representantes:
                if (t := vistos[id(r)][2]) is not None:
                    torcidos[id(t)].append(r)
            suyo_torcido = {
                id(r): _por_solape([(_solape(o, t), o) for o in torcidos[id(t)]]) is r
                for r in representantes
                if (t := vistos[id(r)][2]) is not None
            }
            resultado: dict[int, _Propio | None] = {}
            donde = "encima" if lado > 0 else "debajo"
            for r in representantes:
                tope = vistos[id(r)][1]
                if tope is not None:
                    resultado[id(r)] = _Propio(
                        None,
                        f"lo más cercano dibujado {donde} no es una sección: no se toma lo que "
                        "está más allá",
                        tope=tope,
                        no_rectangular=suyo_torcido.get(id(r), False),
                    )
                    continue
                if not cercanos[id(r)]:
                    resultado[id(r)] = None
                    continue
                opciones = [c for c in cercanos[id(r)] if gana[id(c)] in (r, None)]
                if not opciones:
                    otra = gana[id(cercanos[id(r)][0])]
                    assert otra is not None
                    resultado[id(r)] = _Propio(
                        None, f"su sección dibujada es de {otra.marca}, que se le encima más"
                    )
                    continue
                suya = _por_solape([(_solape(r, c), c) for c in opciones])
                if suya is None:
                    resultado[id(r)] = _Propio(
                        None,
                        "su título está sobre dos secciones dibujadas",
                        dudosa=True,
                        reclamados=[c.caja for c in opciones],
                    )
                elif gana[id(suya)] is r:
                    resultado[id(r)] = _Propio(suya)
                else:
                    otras = sorted(o.marca for o in quienes[id(suya)] if o is not r)
                    resultado[id(r)] = _Propio(
                        None,
                        f"su sección dibujada la alcanza también {', '.join(otras)}",
                        otras,
                        reclamados=[suya.caja],
                    )
            return resultado

        por_lado = {lado: resolver(lado, representantes) for lado in (1, -1)}

        def convencion_de(
            miembros: list[_Etiqueta], lados: dict[int, dict[int, _Propio | None]]
        ) -> int:
            suyas = {
                lado: sum(
                    1 for r in miembros if (p := lados[lado][id(r)]) is not None and p.contorno
                )
                for lado in (1, -1)
            }
            return 1 if suyas[1] > suyas[-1] else -1 if suyas[-1] > suyas[1] else 0

        de_la_hoja = convencion_de(representantes, por_lado)
        # R165: a sheet can hold a cuadro (sections above its labels) and a detail group
        # (sections under its titles, ES-200's «CERRAMIENTOS»): each group of labels near one
        # another keeps its own convention; a group whose labels own nothing takes the sheet's.
        por_grupo: dict[int, int] = {}
        for grupo_cercano in _grupos_cercanos(representantes):
            local = convencion_de(grupo_cercano, por_lado)
            for r in grupo_cercano:
                por_grupo[id(r)] = local or de_la_hoja
        for r in representantes:
            convencion = por_grupo[id(r)]
            if convencion:
                propio = por_lado[convencion][id(r)] or _Propio(
                    None,
                    f"no hay sección dibujada {'encima' if convencion > 0 else 'debajo'}",
                    sin_contorno=True,
                )
            else:
                # Sin convención en la hoja: sólo si la etiqueta tiene sección de un solo lado.
                ambos = [p for p in (por_lado[1][id(r)], por_lado[-1][id(r)]) if p is not None]
                lados = [p for p in ambos if p.tope is None]
                if len(lados) == 1:
                    propio = lados[0]
                elif lados:
                    propio = _Propio(None, "tiene una sección dibujada encima y otra debajo")
                elif ambos:
                    propio = min(ambos, key=lambda p: p.tope or 0.0)
                else:
                    propio = _Propio(None, "no se encontró su sección dibujada", sin_contorno=True)
            for e in grupo:
                if de[e.texto.entity_id] is r:
                    salida[e.texto.entity_id] = propio
    return salida


def _grupos_cercanos(etiquetas: list[_Etiqueta]) -> list[list[_Etiqueta]]:
    """The labels of a sheet in groups of labels near one another (each within two reaches,
    ``2 × _ALCANCE`` heights, of another of its group): a cuadro's row, a detail group."""
    padre = list(range(len(etiquetas)))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i, a in enumerate(etiquetas):
        for j in range(i + 1, len(etiquetas)):
            b = etiquetas[j]
            if math.dist((a.x, a.y), (b.x, b.y)) <= 2 * _ALCANCE * max(a.alto, b.alto):
                padre[raiz(j)] = raiz(i)
    grupos: dict[int, list[_Etiqueta]] = defaultdict(list)
    for i, e in enumerate(etiquetas):
        grupos[raiz(i)].append(e)
    return list(grupos.values())


def _eje(
    d: NormalizedEntity, p: tuple[float, float], q: tuple[float, float], tol: float
) -> str | None:
    """What a dimension measures: «x», «y», or neither (None: a diagonal, an angle, a radius). A
    linear dimension measures on its angle whatever its points; an aligned one between them."""
    props = d.properties or {}
    tipo, angulo = props.get("dimtype"), props.get("angle")
    if tipo == 0 and isinstance(angulo, (int, float)):
        a = float(angulo) % 180.0
        return "x" if min(a, 180.0 - a) < 1.0 else "y" if abs(a - 90.0) < 1.0 else None
    if tipo not in (None, 0, 1):
        return None
    return "x" if abs(p[1] - q[1]) <= tol else "y" if abs(p[0] - q[0]) <= tol else None


def _cotas_de_arista(
    contorno: _Contorno, dims: list[NormalizedEntity], tol: float, unit_to_m: float
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[str]]:
    """The dimensions whose two definition points lie on the outline's edges (``tol``): the
    horizontal ones (their span in x and value) and the vertical ones (span in y, value), and
    an aviso for one on the outline that is neither or whose number has no known unit."""
    x0, y0, x1, y1 = contorno.caja
    horizontales: list[tuple[float, float, float]] = []
    verticales: list[tuple[float, float, float]] = []
    avisos: list[str] = []
    for d in dims:
        dx0, dy0, dx1, dy1 = d.bbox
        if dx1 < x0 - tol or dx0 > x1 + tol or dy1 < y0 - tol or dy0 > y1 + tol:
            continue
        tramo = (d.properties or {}).get("measured_segment")
        if not tramo or len(tramo) != 2:
            continue
        p, q = (float(tramo[0][0]), float(tramo[0][1])), (float(tramo[1][0]), float(tramo[1][1]))
        if not (_en_arista(p, contorno.puntos, tol) and _en_arista(q, contorno.puntos, tol)):
            continue
        valor = _cota_cm(d, unit_to_m)
        if valor is None:
            sin_unidad = _sin_unidad(d, unit_to_m)
            if sin_unidad is not None:
                avisos.append(sin_unidad)
            continue
        eje = _eje(d, p, q, tol)
        if eje == "x":
            horizontales.append((min(p[0], q[0]), max(p[0], q[0]), valor))
        elif eje == "y":
            verticales.append((min(p[1], q[1]), max(p[1], q[1]), valor))
        elif valor >= _COTA_CM[0]:
            avisos.append(f"cota de {valor:g} cm en diagonal sobre la sección: no se toma")
    return horizontales, verticales, avisos


def _lado(
    cotas: list[tuple[float, float, float]], desde: float, hasta: float, tol: float
) -> tuple[float | None, str]:
    """A side from the cotas along it: the one that spans it whole, or a chain of cotas
    that tiles it («15 + 55»); with how it was read. Covers and partial cotas are not the
    side."""
    enteras = sorted({v for a, b, v in cotas if abs(a - desde) <= tol and abs(b - hasta) <= tol})
    if len(enteras) == 1:
        return enteras[0], ""
    if len(enteras) > 1:
        return None, "cotas distintas del mismo lado (" + ", ".join(f"{v:g}" for v in enteras) + ")"
    cadena: list[float] = []
    pos = desde
    while abs(pos - hasta) > tol:
        tramo = next(((b, v) for a, b, v in cotas if abs(a - pos) <= tol and b > pos + tol), None)
        if tramo is None:
            return None, ""
        cadena.append(tramo[1])
        pos = tramo[0]
    return float(sum(_exacto(v) for v in cadena)), " + ".join(f"{v:g}" for v in cadena)


@dataclass
class _Cota:
    """A dimension the pair reader takes: what it measures along (``eje``), its two definition
    points and its value in centimetres."""

    eje: str
    p: tuple[float, float]
    q: tuple[float, float]
    valor: float
    entidad: str

    def tramo(self) -> tuple[float, float]:
        i = 0 if self.eje == "x" else 1
        return min(self.p[i], self.q[i]), max(self.p[i], self.q[i])


@dataclass
class _Par:
    """A section drawn without a closed outline (R106): the rectangle of a horizontal and a
    vertical cota sharing a corner, its values and how many of its edges are drawn."""

    contorno: _Contorno
    ancho: float | None
    peralte: float | None
    aristas: int
    avisos: list[str] = campo_de_dataclass(default_factory=list)
    # R153: its corner is one a vertical cota projects (CE-1's «30»), not a drawn one.
    proyectada: bool = False


# R153: the families whose detail is drawn with a projected corner (the CE pattern: a cadena's
# depth cota from its corner up to the slab edge beside it). Any other needs a real corner.
_CON_ESQUINA_PROYECTADA = frozenset({"dala", "cerramiento"})
# R159: the prefixes that say cadena or cerramiento without doubt (D- does not: a dado on Marina).
_PREFIJOS_DE_CADENA = frozenset({"CE", "CI", "CR"})
# R162: a group heading is this many of its section's heights from it, at most («CADENAS DE
# ENRASE» on Marina: 0.8).
_ENCABEZADO_CERCA = 1.5
# R161: along its column, the armado of a section reaches this many of its heights.
_COLUMNA = 1.3


def _encabezado(texto: str) -> str | None:
    """R162: the family a group heading names — its text opens with a family word (the subject,
    as in ``_family_subject``: never after a note number, a parenthesis or another word) and no
    other family's word appears in it («CADENAS DE ENRASE», «CERRAMIENTOS», «DADOS»). A note
    («… ANCLADA AL MURO O CADENA»), a subtitle («(A NIVEL DE CERRAMIENTO)»), a numbered notes
    line or a title («DALA D-2»: a mark) names none."""
    if re.search(r"\d", texto):
        return None  # a title («DALA D-2») or a note names a mark or a size: no group heading
    palabras = re.findall(r"[A-ZÁÉÍÓÚÑ]+|\S", texto.upper())
    if not palabras:
        return None
    familias = {
        familia
        for palabra in palabras
        for familia, patron in _PALABRAS_DE_FAMILIA
        if patron.fullmatch(palabra)
    }
    sujeto = next((f for f, patron in _PALABRAS_DE_FAMILIA if patron.fullmatch(palabras[0])), None)
    return sujeto if sujeto is not None and familias == {sujeto} else None


def _cadena_dicha(e: _Etiqueta, caja: BBox, entities: list[NormalizedEntity]) -> bool:
    """R159, R162: whether the drawing STATES that the title ``e`` is a cadena or a cerramiento —
    its title's family word; else a prefix that says it without doubt (CE, CI, CR); else, when its
    prefix says nothing or is ambiguous (D-: dala or dado), its group's heading: the NEAREST group
    heading (``_encabezado``) to its section, within ``_ENCABEZADO_CERCA`` of its heights, names a
    cadena or a cerramiento («CADENAS DE ENRASE»). A prefix of another family (T, CTA, K…) never
    is one; notes, subtitles and a neighbouring group's heading never are."""
    if e.familia is not None:
        return e.familia in _CON_ESQUINA_PROYECTADA
    prefijo = re.match(r"[A-Z]+", e.marca.upper())
    if prefijo is not None and prefijo.group() in _PREFIJOS_DE_CADENA:
        return True
    if family_of_mark(e.marca) not in {*_CON_ESQUINA_PROYECTADA, "elemento"}:
        return False
    x0, y0, x1, y1 = caja
    r = 3 * max(x1 - x0, y1 - y0)
    ventana = (x0 - r, y0 - r, x1 + r, y1 + r)
    encabezados: list[tuple[float, str]] = []
    for t in _cerca_de(entities, [ventana]):
        if not (t.is_textual and t.text) or t.entity_id == e.texto.entity_id:
            continue
        familia = _encabezado(t.text)
        if familia is None:
            continue
        tx0, ty0, tx1, ty1 = _extension_del_texto(t)  # where it really lies (R120)
        d = math.hypot(max(x0 - tx1, 0.0, tx0 - x1), max(y0 - ty1, 0.0, ty0 - y1))
        encabezados.append((d, familia))
    if not encabezados:
        return False
    d, familia = min(encabezados)
    return familia in _CON_ESQUINA_PROYECTADA and d <= _ENCABEZADO_CERCA * (y1 - y0)


def _sobre_lo_dibujado(
    p: tuple[float, float],
    horizontales: dict[int, list[tuple[float, float, float]]],
    verticales: dict[int, list[tuple[float, float, float]]],
    tol: float,
    holgura: float | None = None,
) -> bool:
    """Whether the point lies on a drawn horizontal or vertical line (R153), within ``holgura``
    (``tol`` by default; ``tol`` is the one the tables are keyed by)."""
    holgura = tol if holgura is None else holgura
    for tabla, fijo, libre in ((horizontales, p[1], p[0]), (verticales, p[0], p[1])):
        for k in range(round((fijo - holgura) / tol) - 1, round((fijo + holgura) / tol) + 2):
            for f, a, b in tabla.get(k, ()):
                if abs(f - fijo) <= holgura and a - holgura <= libre <= b + holgura:
                    return True
    return False


def _esquina_proyectada(
    punto: tuple[float, float],
    h: _Cota,
    v: _Cota,
    horizontales: dict[int, list[tuple[float, float, float]]],
    verticales: dict[int, list[tuple[float, float, float]]],
    cotas_y: list[_Cota],
    tol: float,
) -> bool:
    """R149, R153: whether ``punto`` (an end of the width cota ``h``) is a corner the vertical
    cota ``v`` projects — its points not one above the other: one on the section's side
    (``borde``), the other beside the section at the corner's level (``lejos``, CE-1's «30» up to
    the slab edge) — and the drawing makes it the section's: (a) a drawn line runs along the edge
    from the corner to the far point; both ends of ``h`` lie on drawn lines, and ``borde`` on THIS
    section's drawn side, which runs from it toward the corner (R153: a base line shared with the
    section beside does not lend that section the depth); (b) ``v`` is not the sum of a chain of
    cotas beside it (an overall cota: «53» = «33» + «20»; R153: every cota of 1 cm or more,
    ``cotas_y``, is a piece — «53» = «48» + «5»); (c) no drawn line parallel to the width crosses
    the side from the corner to ``borde`` strictly between its ends (a beam under a slab: the cota
    runs to the slab top)."""
    for borde, lejos in ((v.p, v.q), (v.q, v.p)):
        esquina = (borde[0], lejos[1])
        if math.dist(punto, esquina) > tol or abs(borde[0] - lejos[0]) <= tol:
            continue
        # (a) the edge at the corner's level, from the corner to the far point, is drawn.
        desde, hasta = sorted((esquina[0], lejos[0]))
        if _cubierta(horizontales, esquina[1], desde, hasta, tol) < 1.0 - 1e-6:
            continue
        # R153: the width cota's ends lie on drawn lines, and ``borde`` on the section's own side.
        if not all(_sobre_lo_dibujado(q, horizontales, verticales, tol) for q in (h.p, h.q)):
            continue
        lo, hi = sorted((borde[1], esquina[1]))
        if not any(
            a - tol <= borde[1] <= b + tol and min(b, hi) - max(a, lo) > tol
            for a, b in _linea_en(verticales, borde[0], tol)
        ):
            continue
        # (b) an overall cota is not a section's depth.
        a, b = v.tramo()
        ancho = b - a
        piezas = sorted(
            c.tramo()
            for c in cotas_y
            if c is not v
            and c.entidad != v.entidad
            and min(abs(cx - vx) for cx in (c.p[0], c.q[0]) for vx in (v.p[0], v.q[0])) <= ancho
            and c.tramo()[0] >= a - tol
            and c.tramo()[1] <= b + tol
        )
        # Every way the pieces chain from ``a``: «53» = «48» + «5» or «30» + «18» + «5».
        alcanzados = {a: 0}
        for ca, cb in piezas:
            pasos = next((n for x, n in alcanzados.items() if abs(ca - x) <= tol), None)
            if pasos is not None and cb > ca + tol:
                alcanzados[cb] = max(alcanzados.get(cb, 0), pasos + 1)
        if any(n >= 2 and abs(x - b) <= tol for x, n in alcanzados.items()):
            continue
        # (c) nothing parallel to the width crosses the side strictly between its ends.
        y0, y1 = sorted((esquina[1], borde[1]))
        if any(
            y0 + tol < f < y1 - tol and ta < esquina[0] - tol and tb > esquina[0] + tol
            for clave, lista in horizontales.items()
            if y0 / tol - 1 <= clave <= y1 / tol + 1
            for f, ta, tb in lista
        ):
            continue
        return True
    return False


def _en_cadena(c: _Cota, cotas: list[_Cota], tol: float) -> bool:
    """Whether ``c`` is a link of a chain of cotas: another on the same axis shares one of its
    ends and goes on past it. A side given by a chain is not a pair's (E3)."""
    a, b = c.tramo()
    for o in cotas:
        if o is c or o.eje != c.eje:
            continue
        if not any(math.dist(x, y) <= tol for x in (c.p, c.q) for y in (o.p, o.q)):
            continue
        oa, ob = o.tramo()
        if ob <= a + tol or oa >= b - tol:
            return True
    return False


def _cubierta(
    tramos: dict[int, list[tuple[float, float, float]]],
    fijo: float,
    desde: float,
    hasta: float,
    tol: float,
) -> float:
    """How much of the edge from ``desde`` to ``hasta`` at ``fijo`` the drawn segments cover
    (``tramos``: by the rounded fixed coordinate, (fixed, from, to))."""
    clave = round(fijo / tol)
    trozos = sorted(
        (max(a, desde), min(b, hasta))
        for k in (clave - 1, clave, clave + 1)
        for f, a, b in tramos.get(k, [])
        if abs(f - fijo) <= tol and min(b, hasta) > max(a, desde)
    )
    total, fin = 0.0, desde
    for a, b in trozos:
        a = max(a, fin)
        if b > a:
            total, fin = total + b - a, b
    return total / (hasta - desde) if hasta > desde else 0.0


def _linea_en(
    tramos: dict[int, list[tuple[float, float, float]]], fijo: float, tol: float
) -> list[tuple[float, float]]:
    """The drawn line at ``fijo``: the collinear segments there joined where they touch."""
    clave = round(fijo / tol)
    trozos = sorted(
        (a, b)
        for k in (clave - 1, clave, clave + 1)
        for f, a, b in tramos.get(k, [])
        if abs(f - fijo) <= tol
    )
    linea: list[tuple[float, float]] = []
    for a, b in trozos:
        if linea and a <= linea[-1][1] + tol:
            linea[-1] = (linea[-1][0], max(linea[-1][1], b))
        else:
            linea.append((a, b))
    return linea


def _acaba_en_sus_esquinas(
    tramos: dict[int, list[tuple[float, float, float]]],
    fijo: float,
    desde: float,
    hasta: float,
    tol: float,
) -> bool:
    """R118: the drawn line along an edge stops at the rectangle's corners: it does not run past
    either of them (a slab's or a wall's line that goes on is no section's edge)."""
    return not any(
        (a < desde - tol or b > hasta + tol)
        for a, b in _linea_en(tramos, fijo, tol)
        if b >= desde - tol and a <= hasta + tol
    )


def _atraviesa(
    tramos: dict[int, list[tuple[float, float, float]]],
    claves: list[int],
    lo: float,
    hi: float,
    desde: float,
    hasta: float,
    tol: float,
) -> bool:
    """R118: a drawn line strictly between ``lo`` and ``hi`` that goes from one edge of the
    rectangle to the other (``desde`` to ``hasta``): two regions, not one section. ``claves``:
    the sorted keys of ``tramos``."""
    vistas: set[float] = set()
    for k in claves[bisect.bisect_left(claves, round((lo + tol) / tol)) :]:
        if k * tol > hi:
            break
        for f, _a, _b in tramos[k]:
            if not lo + tol < f < hi - tol or f in vistas:
                continue
            vistas.add(f)
            if any(a <= desde + tol and b >= hasta - tol for a, b in _linea_en(tramos, f, tol)):
                return True
    return False


def _pares_de_cotas(
    dims: list[NormalizedEntity],
    segmentos: list[NormalizedEntity],
    contornos: list[_Contorno],
    unit_to_m: float,
    tol: float,
    tamano: float,
) -> list[_Par]:
    """The sections drawn without a closed outline (R106): each rectangle that one horizontal
    and one vertical cota define when a definition point of each is the same corner, and the
    drawing draws at least ``_ARISTAS_DIBUJADAS`` of its edges, each at least ``_CUBIERTA`` of
    its length (lines and polyline sides). A link of a chain of cotas makes no pair (E3); a
    rectangle inside a closed outline is that outline's (a non-rectangular section is never a
    pair's rectangle); a rectangle bigger than ``tamano`` is not a section. Two pairs on the same
    rectangle with different values give it no section. A rectangle whose corner only a vertical
    cota projects (``_esquina_proyectada``, R149) says so (``proyectada``, R153)."""
    cotas: list[_Cota] = []
    # R153: the pieces an overall cota may be the sum of: every vertical cota of 1 cm or more.
    cotas_y: list[_Cota] = []
    for d in dims:
        tramo = (d.properties or {}).get("measured_segment")
        if not tramo or len(tramo) != 2:
            continue
        p, q = (float(tramo[0][0]), float(tramo[0][1])), (float(tramo[1][0]), float(tramo[1][1]))
        valor = _cota_cm(d, unit_to_m)
        eje = _eje(d, p, q, tol)
        if valor is None or eje is None:
            continue
        if eje == "y" and valor >= 1.0:
            cotas_y.append(_Cota(eje, p, q, valor, d.entity_id))
        if not _COTA_CM[0] <= valor <= _COTA_CM[1]:
            continue
        cotas.append(_Cota(eje, p, q, valor, d.entity_id))
    sueltas = [c for c in cotas if not _en_cadena(c, cotas, tol)]
    por_punto: dict[tuple[int, int], list[_Cota]] = defaultdict(list)
    for c in sueltas:
        if c.eje == "y":
            # Its definition points, and the corners they project to when they are not one above
            # the other (a vertical cota from the section's corner up to the slab's edge beside
            # it, CE-1 in Marina: «30» from (217.536, −62.316) to (217.896, −60.607)).
            for punto in dict.fromkeys([c.p, c.q, (c.p[0], c.q[1]), (c.q[0], c.p[1])]):
                por_punto[(round(punto[0] / tol), round(punto[1] / tol))].append(c)
    horizontales: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
    verticales: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
    for e in segmentos:
        puntos = [(float(x), float(y)) for x, y in (e.points or [])]
        if e.is_closed and len(puntos) > 2:
            puntos.append(puntos[0])
        for (ax, ay), (bx, by) in zip(puntos, puntos[1:], strict=False):
            if abs(ay - by) <= tol and abs(ax - bx) > tol:
                horizontales[round(ay / tol)].append((ay, min(ax, bx), max(ax, bx)))
            elif abs(ax - bx) <= tol and abs(ay - by) > tol:
                verticales[round(ax / tol)].append((ax, min(ay, by), max(ay, by)))
    cajas_cerradas = [
        c.caja for c in contornos if max(c.caja[2] - c.caja[0], c.caja[3] - c.caja[1]) <= tamano
    ]
    rectangulos: dict[
        tuple[int, int, int, int], tuple[BBox, set[tuple[float, float]], list[str], list[bool]]
    ] = {}
    for h in sueltas:
        if h.eje != "x":
            continue
        for punto in (h.p, h.q):
            k = (round(punto[0] / tol), round(punto[1] / tol))
            for v in {
                id(v): v
                for i in (-1, 0, 1)
                for j in (-1, 0, 1)
                for v in por_punto.get((k[0] + i, k[1] + j), [])
            }.values():
                real = min(math.dist(punto, v.p), math.dist(punto, v.q)) <= tol
                if not real and not _esquina_proyectada(
                    punto, h, v, horizontales, verticales, cotas_y, tol
                ):
                    continue
                (x0, x1), (y0, y1) = h.tramo(), v.tramo()
                if x1 - x0 <= tol or y1 - y0 <= tol or max(x1 - x0, y1 - y0) > tamano:
                    continue
                llave = (round(x0 / tol), round(y0 / tol), round(x1 / tol), round(y1 / tol))
                caja, valores, ids, reales = rectangulos.setdefault(
                    llave, ((x0, y0, x1, y1), set(), [], [])
                )
                valores.add((h.valor, v.valor))
                ids += [i for i in (h.entidad, v.entidad) if i not in ids]
                reales.append(real)
    pares: list[_Par] = []
    claves_h, claves_v = sorted(horizontales), sorted(verticales)
    for caja, valores, ids, reales in rectangulos.values():
        x0, y0, x1, y1 = caja
        if any(
            c[0] - tol <= x0 and x1 <= c[2] + tol and c[1] - tol <= y0 and y1 <= c[3] + tol
            for c in cajas_cerradas
        ):
            continue
        cubiertas = [
            (tabla, fijo, a, b)
            for tabla, fijo, a, b in (
                (horizontales, y0, x0, x1),
                (horizontales, y1, x0, x1),
                (verticales, x0, y0, y1),
                (verticales, x1, y0, y1),
            )
            if _cubierta(tabla, fijo, a, b, tol) >= _CUBIERTA
        ]
        aristas = len(cubiertas)
        if aristas < _ARISTAS_DIBUJADAS:
            continue
        # R118: fewer than 2 drawn edges that stop at its corners (continuous slab or wall
        # lines), or a line across it from edge to edge (two regions): no section.
        if sum(_acaba_en_sus_esquinas(*arista, tol) for arista in cubiertas) < _ESQUINAS:
            continue
        if _atraviesa(horizontales, claves_h, y0, y1, x0, x1, tol) or _atraviesa(
            verticales, claves_v, x0, x1, y0, y1, tol
        ):
            continue
        contorno = _Contorno(
            puntos=[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], entidades=ids
        )
        proyectada = not any(reales)
        if len(valores) > 1:
            distintos = ", ".join(f"{a:g}x{b:g}" for a, b in sorted(valores))
            aviso = (
                f"sección: pares de cotas distintos en el mismo rectángulo ({distintos}): "
                "no se toma"
            )
            pares.append(_Par(contorno, None, None, aristas, [aviso], proyectada))
            continue
        ((ancho, peralte),) = valores
        pares.append(_Par(contorno, ancho, peralte, aristas, proyectada=proyectada))
    return pares


def _se_encima(a: BBox, b: BBox) -> bool:
    """Whether two boxes overlap by more than half of the smaller one."""
    ancho = min(a[2], b[2]) - max(a[0], b[0])
    alto = min(a[3], b[3]) - max(a[1], b[1])
    if ancho <= 0 or alto <= 0:
        return False
    menor = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return ancho * alto > 0.5 * menor


def _rectangulos_de_cotas(
    dims: list[NormalizedEntity],
    segmentos: list[NormalizedEntity],
    unit_to_m: float,
    tol: float,
    tamano: float,
) -> list[_Contorno]:
    """R158, R164: the rectangles a horizontal and a vertical cota span, never read — the drawing
    a claimed title's cotas measure where no pair closes it (R106 needs a shared corner and the
    edges R118 accepts; a beam where a slab meets it has neither). The vertical cota stands at an
    end of the horizontal one's span and the horizontal one within the vertical one's span; every
    definition point AND every corner of the rectangle lies on a drawn line (within 2 % of the
    rectangle): the rectangle is drawn, never a corner only projected — T3-8's «60»s on ES-301,
    one across mid-height and one turned corner to corner, span an empty corner. A composite
    section's cotas need not meet (T2-7's «50» and «42.5» on ES-201: its upper part, drawn). At
    least two of its edges are drawn (``_CUBIERTA`` of each). Whose it is, is the caller's
    (``_propio``; a title at the junction of two such pieces claims neither, R164)."""
    cotas: list[_Cota] = []
    for d in dims:
        tramo = (d.properties or {}).get("measured_segment")
        if not tramo or len(tramo) != 2:
            continue
        p, q = (float(tramo[0][0]), float(tramo[0][1])), (float(tramo[1][0]), float(tramo[1][1]))
        valor = _cota_cm(d, unit_to_m)
        eje = _eje(d, p, q, tol)
        if valor is not None and eje is not None and _COTA_CM[0] <= valor <= _COTA_CM[1]:
            cotas.append(_Cota(eje, p, q, valor, d.entity_id))
    horizontales: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
    verticales: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
    for e in segmentos:
        puntos = [(float(x), float(y)) for x, y in (e.points or [])]
        if e.is_closed and len(puntos) > 2:
            puntos.append(puntos[0])
        for (ax, ay), (bx, by) in zip(puntos, puntos[1:], strict=False):
            if abs(ay - by) <= tol and abs(ax - bx) > tol:
                horizontales[round(ay / tol)].append((ay, min(ax, bx), max(ax, bx)))
            elif abs(ax - bx) <= tol and abs(ay - by) > tol:
                verticales[round(ax / tol)].append((ax, min(ay, by), max(ay, by)))
    salida: dict[tuple[int, int, int, int], _Contorno] = {}
    for h in (c for c in cotas if c.eje == "x"):
        x0, x1 = h.tramo()
        for v in (c for c in cotas if c.eje == "y"):
            y0, y1 = v.tramo()
            if x1 - x0 <= tol or y1 - y0 <= tol or max(x1 - x0, y1 - y0) > tamano:
                continue
            if not any(abs(vx - hx) <= tol for vx in (v.p[0], v.q[0]) for hx in (x0, x1)):
                continue
            if not any(y0 - tol <= hy <= y1 + tol for hy in (h.p[1], h.q[1])):
                continue
            junto = max(tol, 0.02 * max(x1 - x0, y1 - y0))
            esquinas = ((x0, y0), (x1, y0), (x0, y1), (x1, y1))
            if not all(
                _sobre_lo_dibujado(q, horizontales, verticales, tol, junto)
                for q in (h.p, h.q, v.p, v.q, *esquinas)
            ):
                continue
            dibujadas = sum(
                _cubierta(tabla, fijo, a, b, tol) >= _CUBIERTA
                for tabla, fijo, a, b in (
                    (horizontales, y0, x0, x1),
                    (horizontales, y1, x0, x1),
                    (verticales, x0, y0, y1),
                    (verticales, x1, y0, y1),
                )
            )
            if dibujadas < 2:
                continue
            llave = (round(x0 / tol), round(y0 / tol), round(x1 / tol), round(y1 / tol))
            salida.setdefault(
                llave,
                _Contorno(
                    puntos=[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)],
                    entidades=[h.entidad, v.entidad],
                ),
            )
    return list(salida.values())


def _sections_from_detail_cotas(
    entities: list[NormalizedEntity],
    config: TextPatternConfig,
    unit_to_m: float,
    detail_boxes: list[BBox],
    widths_by_family: dict[str, int],
    cuadro_marks: list[str] | None = None,
    sheet: Sheet = _no_frames,
    rechazos: list[Rechazo] | None = None,
    duenos: Collection[str] = (),
    dibujadas: Collection[str] = (),
    titulos: list[str] | None = None,
    secciones: list[tuple[str, BBox, str, str]] | None = None,
    pilas: list[SeccionDeTitulo] | None = None,
) -> list[ElementSpec]:
    """A cuadro or detail label's section from ITS OWN drawn section (R81): the closed
    outline (polylines and lines joined end to end, block contents included) nearest
    the label on the side its sheet's convention puts it (Marina: right above, past
    its stack), that the label's text really lies over (a third of it at least,
    R123), and that no other label lies over as much (R120, ``_propio``); an outline
    without cotas is a section only when it looks like one (R123,
    ``_parece_seccion``). Its cotas are the dimensions whose definition points lie
    on the outline's edges: a horizontal one spanning it is the width, a vertical
    one the depth, as drawn (a beam keeps b×h, R75). The outline's own proportions
    corroborate them: at the scale that best fits both cotas, a drawn side more than
    1 cm off is a second reading (``geometria``: the section as drawn), so the
    disagreement stays visible. With one cota only, a square outline of a cuadro is
    taken square, and a missing width is the one the sheet's callouts use for that
    family — both assumed (``seccion_supuesta``, a «supuesto» value, never a
    «detalle» one). A non-rectangular outline (a trapezoid, a rotated one) is never
    a section, nor a sliver, a strip, an octagon or a symbol without cotas; the
    nearest closed outline, section or not, ends the title's reach (R129). Without
    any closed outline where its section goes, the section is the rectangle of a
    pair of cotas sharing a corner whose edges the drawing draws (R106,
    ``_pares_de_cotas``), owned by the same side and claim rule; a corner a cota
    only projects (R149) is a cadena's or a cerramiento's (R153): another
    family's title that reaches it claims it unread. No section from
    cotas (no nearest dimension is ever taken) is said and the section claimed, so
    nothing fills it from elsewhere, whenever the label owns a drawn section (R123)
    or one that carries a cota, two labels reach one section (every claimant, R111)
    or its title lies over two (R120), and where the old nearest-cota reader read
    one. A label that owns a stack (``duenos``) is a candidate even with no armado
    near it (R111). A label whose section the drawing draws at real size is read by
    ``_sections_from_detail_geometry`` (``dibujadas``): its drawn section without
    cotas is not claimed here (R123 blocks what fills it from elsewhere, not the
    reading of that drawing). A title a leader starts or lands at whose section is
    read nowhere is claimed «señalada por flecha» (R124, ``flechas``; where it
    points is E3).

    R145: a label outside the detail frames with no armado beside it (a plan tag, or the title
    of a detail drawn inside a planta sheet: «CADENAS DE ENRASE … SIN ESCALA») is tried apart:
    when it owns a drawn section that carries cotas (an outline with cotas on its edges, or a
    pair of cotas), on its own sheet's side and not owned by another label, it is a detail
    TITLE — its reading is kept and its entity goes to ``titulos`` and ``cuadro_marks`` (a
    definition, never a placement); otherwise nothing of it is kept. ``secciones`` receives,
    for R140, every owned drawn section: the mark, its box and its sheet key. ``pilas`` receives,
    for R147, every drawn section with whether its armado is read from under it: a detail
    title's own (an R81 outline or an R106 pair, read or claimed; a label that owns a stack of
    its own is read by its stack, Task 6), on the side away from its title; the sections a title
    only claims (R111, R120, R158) and those nobody owns compete, never read."""
    dims = [e for e in entities if e.entity_type == EntityType.dimension]
    if not dims:
        return []
    dims = _con_unidad_declarada(dims, entities, unit_to_m, config)  # R151
    etiquetas: list[_Etiqueta] = []
    tentativas: list[_Etiqueta] = []
    for text in entities:
        if not text.is_textual or not text.text:
            continue
        content = text.text.strip()
        mark = marca_en_texto(content, config)
        if mark is None or len(content) > 8:
            continue
        center = bbox_center(text.bbox)
        in_detail = any(bbox_contains_point(box, center) for box in detail_boxes)
        if not in_detail and text.entity_id not in duenos:
            # A cuadro de castillos drawn inside the planta sheet: the mark
            # sits with its armado text ("4#3", "E#2@15") beside the section.
            # A plan tag never has that; its neighbours are castillos.
            armado_radius = 0.8 / unit_to_m
            has_armado = any(
                t.is_textual
                and t.text
                and _ARMADO_TEXT_RE.search(t.text)
                and (
                    (bbox_center(t.bbox)[0] - center[0]) ** 2
                    + (bbox_center(t.bbox)[1] - center[1]) ** 2
                )
                ** 0.5
                <= armado_radius
                for t in entities
            )
            if not has_armado:
                tentativas.append(_etiqueta_de(text, mark, False, unit_to_m, sheet, config))
                continue
            if cuadro_marks is not None:
                cuadro_marks.append(text.entity_id)
        etiquetas.append(_etiqueta_de(text, mark, in_detail, unit_to_m, sheet, config))
    duenas: list[tuple[_Etiqueta, BBox]] = []
    reclamadas: list[tuple[_Etiqueta, BBox]] = []
    libres: list[BBox] = []
    specs = (
        _leer_secciones(
            etiquetas, entities, dims, unit_to_m, widths_by_family, sheet, rechazos, dibujadas,
            duenas, libres=libres, reclamadas=reclamadas,
        )
        if etiquetas
        else []
    )  # fmt: skip
    modal = _alto_modal([*etiquetas, *tentativas])
    tentativas = _con_cotas_cerca(tentativas, dims)
    if tentativas:
        suyas: list[tuple[_Etiqueta, BBox]] = []
        rechazos_t: list[Rechazo] = []
        leidas = _leer_secciones(
            tentativas, entities, dims, unit_to_m, widths_by_family, sheet, rechazos_t,
            dibujadas, suyas, solo_acotadas=True, ocupadas=[caja for _e, caja in duenas],
            libres=libres,
        )  # fmt: skip
        # R150: a title needs the context of a detail; a plan castillo whose marker carries its
        # own cota is not one.
        suyas = [(e, caja) for e, caja in suyas if _en_un_detalle(e, caja, entities, modal)]
        aceptadas = {e.texto.entity_id for e, _caja in suyas}
        specs += [x for x in leidas if x.entidades and x.entidades[0] in aceptadas]
        if rechazos is not None:
            rechazos += [r for r in rechazos_t if r.entidad_id in aceptadas]
        duenas += suyas
        for lista in (titulos, cuadro_marks):
            if lista is not None:
                lista += sorted(aceptadas)
    if secciones is not None:
        # R158: the drawn sections a title claims without owning them are its too, for R140.
        secciones += [
            (e.marca, caja, e.llave, e.texto.entity_id) for e, caja in [*duenas, *reclamadas]
        ]
        # R150: the dimensioned sections nobody owns (a «CI» type detail), on any sheet — those
        # around the armado texts too (R154: the «CI» group of ES-400, out of every title's reach).
        poseidas = [caja for _e, caja in [*duenas, *reclamadas]]
        libres += _acotadas_junto_al_armado(entities, dims, unit_to_m)
        secciones += [
            ("", caja, "", "")
            for caja in dict.fromkeys(libres)
            if not any(_misma_caja(caja, o, 1e-6) for o in poseidas)
        ]
    if pilas is not None:
        pilas += _secciones_para_pilas(
            duenas, reclamadas, libres, set(titulos or []), duenos, entities
        )
    return specs


# R168: a detail title's subtitle declaring the wall its variant is for: «(PARA MUROS DE 15CM)».
_PARA_MUROS = re.compile(
    r"^\(?\s*PARA\s+(?:MUROS?|TABIQUES?|BLOCK)\s+DE\s+(\d+(?:[.,]\d+)?)\s*"
    r"(?:CMS?\.?|CENT[IÍ]METROS)?\s*\)?\.?$",
    re.IGNORECASE,
)
_SUBTITULO = 1.5  # the subtitle lies this many title heights from its title, at most


def _muros_de_los_titulos(
    texts: list[NormalizedEntity], titulos: Collection[str]
) -> dict[str, float]:
    """R168: for each detail title (entity id), the wall thickness in cm its own subtitle declares
    — the one «(PARA MUROS DE n CM)» text right under or over it (within ``_SUBTITULO`` of its
    heights, its real extent spanning the title's centre). Two such subtitles: neither (said by
    the variant never being chosen)."""
    por_id = {t.entity_id: t for t in texts}
    subtitulos = [
        (t, float(m.group(1).replace(",", ".")))
        for t in texts
        if (m := _PARA_MUROS.match(" ".join((t.text or "").split()))) is not None
    ]
    salida: dict[str, float] = {}
    if not subtitulos:
        return salida
    for titulo_id in titulos:
        titulo = por_id.get(titulo_id)
        if titulo is None:
            continue
        x0, y0, x1, y1 = _extension_del_texto(titulo)
        alto = _alto_de_renglon(titulo, y1 - y0)
        cx = (x0 + x1) / 2
        suyos = []
        for sub, cm in subtitulos:
            a0, b0, a1, b1 = _extension_del_texto(sub)
            hueco = max(b0 - y1, y0 - b1, 0.0)
            if a0 <= cx <= a1 and hueco <= _SUBTITULO * alto:
                suyos.append(cm)
        if len(suyos) == 1:
            salida[titulo_id] = suyos[0]
    return salida


def _secciones_para_pilas(
    duenas: list[tuple[_Etiqueta, BBox]],
    reclamadas: list[tuple[_Etiqueta, BBox]],
    libres: list[BBox],
    titulos: set[str],
    duenos: Collection[str],
    entities: list[NormalizedEntity],
) -> list[SeccionDeTitulo]:
    """R147: the drawn sections of the stack reader (``asociar_secciones``). A detail title's own
    section (in a detail frame, a detail title of a planta, R145, or a planta's label over its
    section) is read, on the side away from its title; another label's own section competes on
    that side only. A label that owns a stack of its own (Task 6: a cuadro's label, its stack
    between it and its section) is no section here: its stack is read and its label competes as
    a label. A claimed section competes on the side away from its title, one nobody owns on both
    (so that their armado never goes to a neighbour); nothing is read from them."""
    archivos = {e.source_file for e in entities}
    unico = next(iter(archivos)) if len(archivos) == 1 else None
    salida: list[SeccionDeTitulo] = []
    vistas: set[tuple[str, tuple[float, ...]]] = set()
    for e, caja in duenas:
        clave = (e.texto.entity_id, tuple(round(v, 6) for v in caja))
        if clave in vistas or e.texto.entity_id in duenos:
            continue
        vistas.add(clave)
        encima = e.y > (caja[1] + caja[3]) / 2
        salida.append(
            SeccionDeTitulo(
                marca=e.marca,
                caja=caja,
                archivo=e.texto.source_file,
                titulo_id=e.texto.entity_id,
                # A detail's title (in a detail frame, R145), or a planta's label over its section
                # (CR-2 on ES-200, whose callouts beside it made it a cuadro's label): its armado
                # is written under its section. A cuadro's label under its section (its stack in
                # between, Task 6) never reads past its section.
                lee=e.en_detalle or e.texto.entity_id in titulos or encima,
                sentidos=(-1,) if encima else (+1,),
                familia=e.familia,
            )
        )
    for e, caja in reclamadas:
        centro = (caja[1] + caja[3]) / 2
        salida.append(
            SeccionDeTitulo(
                marca=e.marca,
                caja=caja,
                archivo=e.texto.source_file,
                titulo_id=e.texto.entity_id,
                lee=False,
                sentidos=(-1,) if e.y > centro else (+1,),
            )
        )
    if unico is not None:
        tomadas = [caja for _e, caja in [*duenas, *reclamadas]]
        salida += [
            SeccionDeTitulo(marca="", caja=caja, archivo=unico, lee=False)
            for caja in dict.fromkeys(libres)
            if not any(_misma_caja(caja, o, 1e-6) for o in tomadas)
        ]
    return salida


def solo_armado(texto: str) -> bool:
    """A text that shows armado and nothing else («4#4», «E#4», «1@6,8@10»): never a note, a size
    or a section (R140)."""
    campos = set(campos_de_fragmento(texto))
    return bool(campos) and campos <= {"longitudinales", "estribos", "parrillas"}


def _acotadas_junto_al_armado(
    entities: list[NormalizedEntity], dims: list[NormalizedEntity], unit_to_m: float
) -> list[BBox]:
    """The dimensioned sections drawn near the armado texts (R150, R154): every closed
    rectangular outline within a title's reach of an armado text, no bigger than a section, with
    a cota on its edges, and every rectangle of a pair of cotas there (R106: drawn open, the
    «LOSA FONDO DE ALBERCA» detail of ES-301). Which of them a title owns is the caller's to
    say."""
    armados = [t for t in entities if t.is_textual and t.text and solo_armado(t.text)]
    if not armados:
        return []
    alto = statistics.median(_alto_de_renglon(t, 0.1 / unit_to_m) for t in armados)
    r = 2 * _ALCANCE * alto
    ventanas = [(t.bbox[0] - r, t.bbox[1] - r, t.bbox[2] + r, t.bbox[3] + r) for t in armados]
    segmentos = [
        e
        for e in _cerca_de(entities, ventanas)
        if e.entity_type in (EntityType.line, EntityType.polyline) and not e.is_annotation
    ]
    une = _UNE * alto
    salida: list[BBox] = []
    contornos = _contornos(segmentos, une)
    cerca = _cerca_de(dims, ventanas)
    for c in contornos:
        x0, y0, x1, y1 = c.caja
        if max(x1 - x0, y1 - y0) > _TAMANO * alto or not _es_rectangulo(
            _esquinas(c.puntos, une), une
        ):
            continue
        h, v, _avisos = _cotas_de_arista(c, cerca, _SOBRE_ARISTA * alto, unit_to_m)
        if h or v:
            salida.append(c.caja)
    pares = _pares_de_cotas(
        cerca, segmentos, contornos, unit_to_m, _SOBRE_ARISTA * alto, _TAMANO * alto
    )
    return salida + [par.contorno.caja for par in pares]


def _etiqueta_de(
    text: NormalizedEntity,
    mark: str,
    in_detail: bool,
    unit_to_m: float,
    sheet: Sheet,
    config: TextPatternConfig,
) -> _Etiqueta:
    content = (text.text or "").strip()
    x0, y0, x1, y1 = _extension_del_texto(text)  # where its text really lies (R120)
    return _Etiqueta(
        texto=text,
        marca=mark,
        x=(x0 + x1) / 2,
        y=(y0 + y1) / 2,
        alto=_alto_de_renglon(text, 0.1 / unit_to_m),
        llave=sheet(text)[1],
        en_detalle=in_detail,
        x0=x0,
        x1=x1,
        y0=y0,
        y1=y1,
        familia=_familia_de_titulo((_titulo(content, config) or ([], None))[1], mark),
    )


# R150: what says a group of drawings is a detail: its layer, or a heading or note beside it.
_CAPA_DE_DETALLE = ["DETALLE", "DETALLES", "DET"]
_ENCABEZADO_DE_DETALLE = re.compile(
    r"DETALLE|CORTE|SECCI[OÓ]N|ACOTACION|SIN ESCALA|\bS/E\b|\bESC(?:ALA)?\b", re.IGNORECASE
)


def _alto_modal(etiquetas: list[_Etiqueta]) -> dict[str, float]:
    """The most common height of the mark labels of each sheet (its tags)."""
    por_hoja: dict[str, Counter[float]] = defaultdict(Counter)
    for e in etiquetas:
        por_hoja[e.llave][round(e.alto, 4)] += 1
    return {hoja: c.most_common(1)[0][0] for hoja, c in por_hoja.items()}


def _en_un_detalle(
    e: _Etiqueta, caja: BBox, entities: list[NormalizedEntity], modal: dict[str, float]
) -> bool:
    """R150: a label tried apart is a detail title only in the context of a detail: its layer is
    a detail layer, its text is at least 1.2 times the sheet's most common tag height, or a
    detail heading or note («DETALLE», «CORTE», «ACOTACIONES … SIN ESCALA») lies within three
    times its section's size."""
    if layer_matches(e.texto.layer, _CAPA_DE_DETALLE):
        return True
    if e.alto >= 1.2 * modal.get(e.llave, math.inf):
        return True
    x0, y0, x1, y1 = caja
    r = 3 * max(x1 - x0, y1 - y0)
    ventana = (x0 - r, y0 - r, x1 + r, y1 + r)
    return any(
        t.is_textual
        and t.text
        and t.entity_id != e.texto.entity_id
        and _ENCABEZADO_DE_DETALLE.search(t.text)
        for t in _cerca_de(entities, [ventana])
    )


def _con_cotas_cerca(etiquetas: list[_Etiqueta], dims: list[NormalizedEntity]) -> list[_Etiqueta]:
    """R145: of the labels tried apart, those with a dimension within reach of a section: a
    plan tag far from every cota is never a detail title."""
    if not etiquetas:
        return []
    ventanas = [
        (e.x - r, e.y - r, e.x + r, e.y + r) for e in etiquetas for r in [_ALCANCE * e.alto]
    ]
    cerca = _cerca_de(dims, ventanas)
    return [
        e
        for e, v in zip(etiquetas, ventanas, strict=True)
        if any(
            d.bbox[0] <= v[2] and d.bbox[2] >= v[0] and d.bbox[1] <= v[3] and d.bbox[3] >= v[1]
            for d in cerca
        )
    ]


def _misma_caja(a: BBox, b: BBox, tol: float) -> bool:
    return all(abs(p - q) <= tol for p, q in zip(a, b, strict=True))


def _leer_secciones(
    etiquetas: list[_Etiqueta],
    entities: list[NormalizedEntity],
    dims: list[NormalizedEntity],
    unit_to_m: float,
    widths_by_family: dict[str, int],
    sheet: Sheet,
    rechazos: list[Rechazo] | None,
    dibujadas: Collection[str],
    duenas: list[tuple[_Etiqueta, BBox]],
    solo_acotadas: bool = False,
    ocupadas: list[BBox] | None = None,
    libres: list[BBox] | None = None,
    reclamadas: list[tuple[_Etiqueta, BBox]] | None = None,
) -> list[ElementSpec]:
    """The readings of ``etiquetas``' sections (see ``_sections_from_detail_cotas``); ``duenas``
    receives each label that owns a drawn section, with the section's box. ``solo_acotadas``
    (R145, the labels tried apart): an outline is a section only if it carries cotas on its
    edges; ``ocupadas`` are the sections other labels own, never these labels'. ``libres``
    receives the dimensioned sections drawn here that no label owns (R150: the armado written
    under them is theirs, nobody else's); ``reclamadas``, each label's drawn sections it claims
    without owning them (R158)."""
    alto = statistics.median(e.alto for e in etiquetas)
    # Only what lies near a label is joined into outlines.
    ventanas = [
        (e.x - 2 * _ALCANCE * e.alto, e.y - 2 * _ALCANCE * e.alto,
         e.x + 2 * _ALCANCE * e.alto, e.y + 2 * _ALCANCE * e.alto)
        for e in etiquetas
    ]  # fmt: skip
    # M-7: a leader's lines (LEADER, MULTILEADER) are annotation, never a section's edge.
    segmentos = [
        e
        for e in _cerca_de(entities, ventanas)
        if e.entity_type in (EntityType.line, EntityType.polyline) and not e.is_annotation
    ]
    contornos = [
        c
        for c in _contornos(segmentos, _UNE * alto)
        if not any(_misma_caja(c.caja, o, _UNE * alto) for o in ocupadas or [])
    ]
    con_cotas: dict[tuple[int, float], bool] = {}

    def es_seccion(c: _Contorno, e: _Etiqueta) -> bool:
        """R123, R129: an outline is a section when it is a rectangle (a trapezoid or a rotated
        one is not) that looks like one or carries a cota on its edges (R145: for a label tried
        apart, only one that carries a cota)."""
        if not _es_rectangulo(_esquinas(c.puntos, _UNE * alto), _UNE * alto):
            return False
        if not solo_acotadas and _parece_seccion(c, e.alto, _UNE * alto):
            return True
        clave = (id(c), e.alto)
        if clave not in con_cotas:
            h, v, avisos = _cotas_de_arista(c, dims, _SOBRE_ARISTA * e.alto, unit_to_m)
            con_cotas[clave] = bool(h or v or avisos)
        return con_cotas[clave]

    propios = _propio(etiquetas, contornos, es_seccion)
    # R106: the labels with no closed outline where their section goes, against the rectangles
    # of pairs of cotas, by the same side and claim rule.
    sin_contorno = [
        e
        for e in etiquetas
        if propios[e.texto.entity_id].sin_contorno or propios[e.texto.entity_id].tope is not None
    ]
    # R129: a pair of cotas past the nearest closed outline is out of reach too.
    topes = {i: p.tope for i, p in propios.items() if p.tope is not None and not p.sin_contorno}
    pares: dict[int, _Par] = {}
    de_par: dict[str, _Propio] = {}
    if sin_contorno:
        # A section reaches up to ``_ALCANCE`` from its label and spans up to ``_TAMANO``: its far
        # edge and cota lie that far.
        lejos = [
            (e.x - r, e.y - r, e.x + r, e.y + r)
            for e in sin_contorno
            for r in [(_ALCANCE + _TAMANO) * e.alto]
        ]
        lista = _pares_de_cotas(
            _cerca_de(dims, lejos),
            [
                e
                for e in _cerca_de(entities, lejos)
                if e.entity_type in (EntityType.line, EntityType.polyline) and not e.is_annotation
            ],
            contornos,
            unit_to_m,
            _SOBRE_ARISTA * alto,
            _TAMANO * alto,
        )
        lista = [
            par
            for par in lista
            if not any(_misma_caja(par.contorno.caja, o, _UNE * alto) for o in ocupadas or [])
        ]
        pares = {id(par.contorno): par for par in lista}
        # R157: whose each rectangle is, among every title; whether its owner may read it is
        # decided after (R153, R159).
        de_par = _propio(sin_contorno, [par.contorno for par in lista], topes=topes)

    specs: list[ElementSpec] = []
    sin_caja: list[_Etiqueta] = []
    de_nadie: list[BBox] = []
    for e in etiquetas:
        par = de_par.get(e.texto.entity_id)
        if par is not None and (par.contorno is not None or par.otras or par.dudosa):
            if par.contorno is None:
                # R158: a section several titles reach (R111) or two its title lies over (R120):
                # claimed by each of them, its armado may be any's.
                if reclamadas is not None:
                    reclamadas += [(e, caja) for caja in par.reclamados]
                specs += _seccion_de_par(e, par, pares, sheet, rechazos)
                continue
            duenas.append((e, par.contorno.caja))
            suyo = pares[id(par.contorno)]
            if suyo.proyectada and not _cadena_dicha(e, par.contorno.caja, entities):
                # R153, R159: a corner a cota only projects is a cadena's or a cerramiento's,
                # stated: any other title owning it claims it, never reads it.
                valores = (
                    f" {suyo.ancho:g}x{suyo.peralte:g}"
                    if suyo.ancho is not None and suyo.peralte is not None
                    else ""
                )
                aviso = (
                    f"sección: el par de cotas{valores} no tiene su esquina dibujada (su cota de "
                    "alto llega a una esquina proyectada, que sólo se acepta en una cadena o un "
                    "cerramiento dichos): no se toma"
                )
                specs.append(
                    _lectura_de_cotas(
                        e, sheet, None, [aviso], "par de cotas con esquina proyectada"
                    )
                )
                continue
            specs += _seccion_de_par(e, par, pares, sheet, rechazos)
            continue
        suyo_cerrado = propios[e.texto.entity_id]
        if suyo_cerrado.contorno is not None:
            duenas.append((e, suyo_cerrado.contorno.caja))
        elif suyo_cerrado.reclamados:
            if reclamadas is not None:
                reclamadas += [(e, caja) for caja in suyo_cerrado.reclamados]
        else:
            sin_caja.append(e)
        specs += _seccion_de_etiqueta(
            e,
            suyo_cerrado,
            dims,
            unit_to_m,
            widths_by_family,
            sheet,
            rechazos,
            alto,
            leida_a_escala=e.texto.entity_id in dibujadas,
        )
    if reclamadas is not None:
        # R158: a title whose section is claimed with no drawing it owns («no se encontró», the
        # nearby cotas not taken: a beam where a slab meets it) claims the rectangle its cotas
        # span on its side: its armado may be its.
        reclamantes = {
            i for s in specs if s.section_cm is None for i in s.entidades if s.metodo == "cotas"
        }
        sueltas = [e for e in sin_caja if e.texto.entity_id in reclamantes]
        if sueltas:
            lejos = [
                (e.x - r, e.y - r, e.x + r, e.y + r)
                for e in sueltas
                for r in [(_ALCANCE + _TAMANO) * e.alto]
            ]
            tomadas = [caja for _e, caja in [*duenas, *reclamadas]] + list(ocupadas or [])
            rectangulos = [
                c
                for c in _rectangulos_de_cotas(
                    _cerca_de(dims, lejos),
                    [
                        e
                        for e in _cerca_de(entities, lejos)
                        if e.entity_type in (EntityType.line, EntityType.polyline)
                        and not e.is_annotation
                    ],
                    unit_to_m,
                    _SOBRE_ARISTA * alto,
                    _TAMANO * alto,
                )
                if not any(_se_encima(c.caja, o) for o in tomadas)
            ]
            # R165: these boxes only attribute armado (never a reading): a title over the box by a
            # quarter of its real text is enough (``_ENCIMA_MINIMO`` was measured on the old
            # 0.6-height-per-character boxes; T3-1 lies 28 % over its own section on ES-301, D-5's
            # graze 10 %).
            de_cotas = _propio(sueltas, rectangulos, topes=topes, encima_minimo=_ENCIMA_RECLAMADA)
            reclamadas += [
                (e, p.contorno.caja)
                for e in sueltas
                if (p := de_cotas[e.texto.entity_id]).contorno is not None
                and not _en_la_junta(e, p.contorno.caja, rectangulos, _UNE * alto)
            ]
            # R164: a drawn, dimensioned piece no title claims (the slab's step beside T3-8, the
            # wing of T2-7's composite section) is a section nobody owns: the armado written on
            # it, or pointed into it, is its own — unowned, never the nearest title's (R150).
            suyas_ya = [caja for _e, caja in [*duenas, *reclamadas]] + list(ocupadas or [])
            de_nadie = [
                c.caja for c in rectangulos if not any(_se_encima(c.caja, o) for o in suyas_ya)
            ]
    if libres is not None:
        libres += de_nadie
        une = _UNE * alto
        suyas = [caja for _e, caja in [*duenas, *(reclamadas or [])]] + list(ocupadas or [])
        for c in contornos:
            x0, y0, x1, y1 = c.caja
            if (
                max(x1 - x0, y1 - y0) > _TAMANO * alto
                or not _es_rectangulo(_esquinas(c.puntos, une), une)
                or any(_misma_caja(c.caja, o, une) for o in suyas)
            ):
                continue
            h, v, _avisos = _cotas_de_arista(c, dims, _SOBRE_ARISTA * alto, unit_to_m)
            if h or v:
                libres.append(c.caja)
        libres += [
            par.contorno.caja
            for par in pares.values()
            if not any(_misma_caja(par.contorno.caja, o, une) for o in suyas)
        ]
    return specs


def _en_la_junta(e: _Etiqueta, caja: BBox, rectangulos: list[_Contorno], une: float) -> bool:
    """R164: whether the title stands at the junction of its claimed box and another dimensioned
    piece drawn side by side with it (sharing a vertical edge, not overlapping it) — its text
    ends within ``_EN_LA_JUNTA`` of its heights of that edge (R115's tolerance). Its own section is
    then either piece: T3-8 on ES-301, whose title lies over the slab's step («60» × «30», with
    its own «3#6», «2E#3@15», «#4@15») and ends 0.05 short of its own beam («20» × «60»). It
    claims neither: a claimed box must be the title's OWN drawn section."""
    x0, y0, x1, y1 = caja
    tolerancia = _EN_LA_JUNTA * e.alto
    for otro in rectangulos:
        a0, b0, a1, b1 = otro.caja
        if _misma_caja(otro.caja, caja, une) or min(y1, b1) - max(y0, b0) <= une:
            continue  # the same piece, or not side by side
        if min(x1, a1) - max(x0, a0) > une:
            continue  # one over the other: not two pieces side by side
        for junta in (x for x in (x0, x1) if min(abs(x - a0), abs(x - a1)) <= une):
            if e.x0 - tolerancia <= junta <= e.x1 + tolerancia:
                return True
    return False


def _seccion_de_par(
    e: _Etiqueta,
    suyo: _Propio,
    pares: dict[int, _Par],
    sheet: Sheet,
    rechazos: list[Rechazo] | None,
) -> list[ElementSpec]:
    """The reading of a label's section from a pair of cotas (R106): the pair's rectangle with
    its values as written (72.5 stays 72.5), or, when another label reaches the same rectangle or
    its pairs disagree, the section claimed with no value."""
    if suyo.contorno is None and suyo.dudosa:
        aviso = "sección: su título está sobre dos rectángulos de pares de cotas"
        return [_lectura_de_cotas(e, sheet, None, [aviso], "par de cotas dudoso")]
    if suyo.contorno is None:
        if rechazos is not None:
            rechazos.append(
                Rechazo(
                    entidad_id=e.texto.entity_id,
                    texto=(e.texto.text or "").strip(),
                    hoja=sheet(e.texto)[0],
                    motivo="ambigua",
                    marcas=[e.marca, *suyo.otras],
                )
            )
        aviso = (
            f"sección: el rectángulo de su par de cotas lo alcanza también {', '.join(suyo.otras)}"
        )
        return [_lectura_de_cotas(e, sheet, None, [aviso], "par de cotas compartido")]
    par = pares[id(suyo.contorno)]
    if par.ancho is None or par.peralte is None:
        return [_lectura_de_cotas(e, sheet, None, list(par.avisos), "pares de cotas distintos")]
    section = (_cm(par.ancho), _cm(par.peralte))
    nota = (
        f"par de cotas {section[0]}x{section[1]} sin contorno cerrado "
        f"({par.aristas} de 4 aristas dibujadas)"
    )
    return [_lectura_de_cotas(e, sheet, section, list(par.avisos), nota)]


def _lectura_de_cotas(
    e: _Etiqueta,
    sheet: Sheet,
    section: tuple[int | float, int | float] | None,
    avisos: list[str],
    note: str,
    metodo: Metodo = "cotas",
    supuesta: bool = False,
    campos: list[Campo] | None = None,
) -> ElementSpec:
    """A reading of the section of a cuadro or detail label (``_sections_from_detail_cotas``);
    ``campos`` are the fields the drawing has text (or drawing) for, the section by default."""
    content = (e.texto.text or "").strip()
    hoja, llave = sheet(e.texto)
    return ElementSpec(
        mark=e.marca,
        family=e.familia or family_of_mark(e.marca),
        familia_supuesta=e.familia is None,
        section_cm=section,
        source="detalle",
        metodo=metodo,
        hoja=hoja,
        hoja_llave=llave,
        entidades=[e.texto.entity_id],
        campos_con_texto=list(campos) if campos is not None else ["seccion"],
        avisos=avisos,
        source_text=f"{content} · {note}"[:120],
        confidence=0.7 if section is not None and not supuesta else 0.55,
        seccion_supuesta=supuesta,
    )


def _seccion_de_etiqueta(
    e: _Etiqueta,
    suyo: _Propio,
    dims: list[NormalizedEntity],
    unit_to_m: float,
    widths_by_family: dict[str, int],
    sheet: Sheet,
    rechazos: list[Rechazo] | None,
    alto: float,
    leida_a_escala: bool = False,
) -> list[ElementSpec]:
    """The readings of one label's section (see ``_sections_from_detail_cotas``)."""
    family = family_of_mark(e.marca)
    tol = _SOBRE_ARISTA * e.alto

    # A section this reader cannot read is claimed and said, so nothing fills it from elsewhere,
    # when it owns a drawn section (R123), two labels reach it (R111) or its title lies over two
    # (R120), and where the old nearest-dimension reader took a value (a section-range vertical
    # cota near the label, and a horizontal one, or a cuadro's square, or the family's usual
    # width).
    ancla = ancla_texto(e.texto)  # where the old reader measured from (as R115)

    def cerca(vertical: bool, rango: tuple[int, int]) -> list[int | float]:
        return sorted(
            {
                _cm(v)
                for d in dims
                if math.dist(bbox_center(d.bbox), ancla) <= 2.5 / unit_to_m
                and ((d.bbox[3] - d.bbox[1]) > (d.bbox[2] - d.bbox[0])) == vertical
                and (v := _cota_cm(d, unit_to_m)) is not None
                and rango[0] <= v <= rango[1]
            }
        )

    verticales_cerca, horizontales_cerca = cerca(True, _COTA_DEPTH_CM), cerca(False, (12, 60))
    leia = bool(verticales_cerca) and (
        bool(horizontales_cerca) or not e.en_detalle or family in widths_by_family
    )
    cercanas = sorted(set(verticales_cerca) | set(horizontales_cerca)) if leia else []

    def sin_seccion(avisos: list[str], nota: str, reclama: bool = False) -> list[ElementSpec]:
        if not cercanas and not reclama:
            return []
        if cercanas:
            cifras = ", ".join(f"{v:g}" for v in cercanas)
            avisos = [*avisos, f"las cotas cercanas ({cifras}) no se toman"]
        return [_lectura_de_cotas(e, sheet, None, avisos, nota)]

    propio = suyo.contorno
    if suyo.otras and rechazos is not None:
        # Two labels reach one drawn section: whose it is, the geometry does not say.
        rechazos.append(
            Rechazo(
                entidad_id=e.texto.entity_id,
                texto=(e.texto.text or "").strip(),
                hoja=sheet(e.texto)[0],
                motivo="ambigua",
                marcas=[e.marca, *suyo.otras],
            )
        )
    if propio is None:
        nota = (
            "sección dibujada compartida"
            if suyo.otras
            else "sección dibujada dudosa"
            if suyo.dudosa
            else "sección dibujada no encontrada"
        )
        salida = sin_seccion(
            [f"sección: {suyo.por_que}"] + ([_NO_RECTANGULAR] if suyo.no_rectangular else []),
            nota,
            reclama=bool(suyo.otras) or suyo.dudosa,
        )
        for s in salida:
            s.seccion_no_rectangular = suyo.no_rectangular
        return salida
    x0, y0, x1, y1 = propio.caja
    w, h = x1 - x0, y1 - y0
    # R123: the outline it owns is its section, drawn, even without cotas: claimed when it looks
    # like one (``_parece_seccion``; without cotas it is owned only then), unless the section
    # drawn at real size is read (``leida_a_escala``).
    reclama = _parece_seccion(propio, e.alto, _UNE * alto) and not leida_a_escala
    horizontales, verticales, avisos = _cotas_de_arista(propio, dims, tol, unit_to_m)
    con_cota = bool(horizontales or verticales or avisos)  # its own section carries a cota
    ancho, como_ancho = _lado(horizontales, x0, x1, tol)
    peralte, como_peralte = _lado(verticales, y0, y1, tol)
    for valor, nombre, como in ((ancho, "ancho", como_ancho), (peralte, "peralte", como_peralte)):
        if valor is not None and " + " in como:
            avisos.append(f"{nombre} {valor:g} = {como} (cotas en cadena)")
        elif valor is None and como:
            avisos.append(f"{nombre}: {como}: no se toma")
    if ancho is not None and not _COTA_CM[0] <= ancho <= _COTA_CM[1]:
        avisos.append(f"ancho {ancho:g} cm fuera de rango: no se toma")
        ancho = None
    if peralte is not None and not _COTA_CM[0] <= peralte <= _COTA_CM[1]:
        avisos.append(f"peralte {peralte:g} cm fuera de rango: no se toma")
        peralte = None
    if ancho is not None and peralte is not None:
        section = (_cm(ancho), _cm(peralte))
        salida = [
            _lectura_de_cotas(
                e, sheet, section, avisos, f"cotas de su sección {section[0]}x{section[1]}"
            )
        ]
        # The outline's own proportions corroborate the cotas: at the scale that best fits both,
        # each drawn side within 2 cm or 10 % (R112). If not, the section as drawn is a reading too.
        escala = (ancho * w + peralte * h) / (w * w + h * h)
        dibujada = (w * escala, h * escala)
        if any(
            abs(d - c) > max(_COINCIDE_CM, _COINCIDE_PARTE * c)
            for d, c in ((dibujada[0], ancho), (dibujada[1], peralte))
        ):
            redonda = (_cm(round(dibujada[0], 1)), _cm(round(dibujada[1], 1)))
            aviso = (
                f"sección dibujada {dibujada[0]:.1f}x{dibujada[1]:.1f} cm a la escala de sus cotas "
                f"(1 unidad = {escala:.2f} cm): no coincide con sus cotas {section[0]}x{section[1]}"
            )
            salida.append(
                _lectura_de_cotas(
                    e, sheet, redonda, [aviso], f"sección dibujada {redonda[0]}x{redonda[1]}",
                    metodo="geometria",
                )
            )  # fmt: skip
        return salida
    uno = ancho if ancho is not None else peralte
    if uno is not None and not e.en_detalle and abs(w - h) <= _CUADRADA * max(w, h):
        lado = _cm(uno)
        avisos.append(
            f"una sola cota ({lado} cm) y la sección dibujada cuadrada: se supone cuadrada"
        )
        return [
            _lectura_de_cotas(e, sheet, (lado, lado), avisos, f"una cota {lado}", supuesta=True)
        ]
    if peralte is not None and ancho is None and family in widths_by_family:
        section = (widths_by_family[family], _cm(peralte))
        avisos.append(
            f"ancho {section[0]} supuesto: el de las demás secciones de {family} del plano"
        )
        nota = f"peralte {section[1]} acotado; ancho {section[0]} como las demás de {family}"
        return [_lectura_de_cotas(e, sheet, section, avisos, nota, supuesta=True)]
    acotado = (
        f"sólo su {'ancho' if ancho is not None else 'peralte'} ({_cm(uno)} cm) está acotado"
        if uno is not None
        else "no tiene cotas que se tomen"
        if con_cota
        else "no tiene cotas en sus aristas"
    )
    # Its own section is drawn (R123) or carries a cota (R111): the section is the drawing's,
    # claimed.
    return sin_seccion(
        [*avisos, f"sección: su sección dibujada {acotado}"],
        "sección sin cotas",
        reclama=con_cota or reclama,
    )


def _cerca_de(entities: list[NormalizedEntity], ventanas: list[BBox]) -> list[NormalizedEntity]:
    """The entities whose box meets one of ``ventanas`` (a grid of the windows)."""
    if not ventanas:
        return []
    lado = max(max(v[2] - v[0], v[3] - v[1]) for v in ventanas) or 1.0
    celdas: dict[tuple[int, int], list[BBox]] = defaultdict(list)
    for v in ventanas:
        for i in range(math.floor(v[0] / lado), math.floor(v[2] / lado) + 1):
            for j in range(math.floor(v[1] / lado), math.floor(v[3] / lado) + 1):
                celdas[(i, j)].append(v)
    salida = []
    for e in entities:
        x0, y0, x1, y1 = e.bbox
        vistas = (
            {
                (i, j)
                for i in range(math.floor(x0 / lado), math.floor(x1 / lado) + 1)
                for j in range(math.floor(y0 / lado), math.floor(y1 / lado) + 1)
                if (i, j) in celdas
            }
            if (x1 - x0) / lado < 50 and (y1 - y0) / lado < 50
            else set(celdas)
        )
        if any(
            v[0] <= x1 and x0 <= v[2] and v[1] <= y1 and y0 <= v[3]
            for c in vistas
            for v in celdas[c]
        ):
            salida.append(e)
    return salida


# The armado fields of a spec: the field name, its canonical string and its list in ``Armado``.
_ARMADO_FIELDS: tuple[tuple[Campo, str, str], ...] = (
    ("longitudinales", "rebar", "longitudinales"),
    ("estribos", "stirrups", "estribos"),
    ("parrillas", "mesh", "parrillas"),
)


def _union(*lists: list) -> list:
    return list(dict.fromkeys(item for items in lists for item in items))


def _merge_fields(chosen: ElementSpec, others: list[ElementSpec]) -> ElementSpec:
    """Same-rank readings of the same sheet complete each other (the drawn
    section plus the armado written beside the mark). The caller passes only
    readings of ``chosen``'s sheet: readings from different sheets are never
    merged. Returns a copy; the readings themselves are never touched."""
    merged = chosen.model_copy(deep=True)
    for other in others:
        if merged.section_cm is None and other.section_cm is not None:
            merged.section_cm = other.section_cm
        for _campo, attr, lista in _ARMADO_FIELDS:
            if getattr(merged, attr) is not None or getattr(other, attr) is None:
                continue
            setattr(merged, attr, getattr(other, attr))
            if other.armado is not None:
                if merged.armado is None:
                    merged.armado = Armado(texto_original=other.armado.texto_original)
                copia = [x.model_copy() for x in getattr(other.armado, lista)]
                setattr(merged.armado, lista, copia)
        merged.campos_con_texto = [
            c for c in CAMPOS if c in set(merged.campos_con_texto) | set(other.campos_con_texto)
        ]
        merged.entidades = _union(merged.entidades, other.entidades)
        merged.avisos = _union(merged.avisos, other.avisos)
    return merged


def _same_sheet(a: ElementSpec, b: ElementSpec) -> bool:
    """Two readings of the same sheet: by its unique key (a reader that does
    not set one falls back to the sheet's name)."""
    return (a.hoja_llave or a.hoja) == (b.hoja_llave or b.hoja)


def _value_text(value: object, family: str | None = None) -> str:
    """How a value is compared and quoted: a section as read (a beam's b×h,
    R75), a castillo's, a columna's or a pilote's by its sides, smaller first."""
    if isinstance(value, tuple):
        a, b = sorted(value) if family in FAMILIAS_QUE_SE_ORDENAN else value
        return f"{a}x{b}"
    return str(value)


def _disagreements(readings: list[ElementSpec], used: ElementSpec) -> list[str]:
    """Where the same-rank readings of a mark do not agree with each other or
    with the value the by-mark view uses — another sheet says something else,
    or says what this sheet leaves empty. Never resolved in silence."""
    avisos = []
    for field, name in (
        ("section_cm", "sección"),
        ("rebar", "longitudinales"),
        ("stirrups", "estribos"),
        ("mesh", "parrillas"),
    ):
        said: dict[str, set[str]] = {}
        for r in readings:
            value = getattr(r, field)
            if value is not None:
                said.setdefault(_value_text(value, used.family), set()).add(
                    _sheet_name(r, readings)
                )
        current = getattr(used, field)
        if not said or (len(said) == 1 and current is not None):
            continue
        listed = ", ".join(f"«{v}» ({', '.join(sorted(h))})" for v, h in said.items())
        here = f"«{_value_text(current, used.family)}»" if current is not None else "nada"
        avisos.append(
            f"{name}: las lecturas no coinciden — {listed}; aquí se usa {here} "
            f"(hoja {_sheet_name(used, readings)})"
        )
    return avisos


def _sheet_name(r: ElementSpec, readings: list[ElementSpec]) -> str:
    """A sheet as an aviso names it: its code, plus its file and frame when
    another sheet among ``readings`` has the same code (two frames sharing
    one, R64-D)."""
    name = r.hoja or "sin hoja"
    shared = any(o.hoja == r.hoja and not _same_sheet(o, r) for o in readings)
    if shared and r.hoja_llave:
        archivo, _, marco = r.hoja_llave.rpartition("#")
        return f"{name} [{marco or 'sin marco'} de {archivo.rsplit('/', 1)[-1]}]"
    return name


# An armado-shaped fragment: a bar number («#4», «Ø 4», «%%C4»), a spacing
# («@20») or the line that continues a zoned stirrup («CENTRO@20»).
_FORMA_DE_ARMADO = re.compile(r"(?:#|Ø|⌀|%%C)\s*\d|@\s*\d|^\s*(?:CENTRO|EXT)\s*@", re.I | re.M)


def _texts_naming_marks(
    texts: list[NormalizedEntity], config: TextPatternConfig, sheet: Sheet
) -> tuple[list[TextoConMarca], list[HojaConFragmentos]]:
    """Every line of every drawing text (model space and block contents, every
    sheet, MTEXT line by line) that holds an armado-, section- or
    length-shaped fragment and a letter (R68, R80: a line without a letter
    names no mark), by sheet; and among them those that name marks — the one
    mark grammar (``leer_marcas``, R67): its marks and ranges, every candidate
    of a glued mark and the glued token itself (R64). Each line keeps the
    fields its fragments show (``campos_de_fragmento``)."""
    found: list[TextoConMarca] = []
    hojas: dict[str, HojaConFragmentos] = {}
    for text in texts:
        for line in (text.text or "").split("\n"):
            line = line.strip()
            if not (
                _FORMA_DE_ARMADO.search(line)
                or _read_section(line)[2]
                or _LONGITUD.search(line.upper())
                or tiene_armado(line)  # R91: «K-1 4 VARS 3/8"», sin «#»
            ):
                continue
            if re.search(r"[A-Z]", normalizar(line)[1]) is None:
                continue
            campos = campos_de_fragmento(line)
            hoja, llave = sheet(text)
            hojas.setdefault(llave, HojaConFragmentos(hoja=hoja, hoja_llave=llave)).lineas.append(
                LineaConFragmento(entidad_id=text.entity_id, texto=line, campos=campos)
            )
            lectura = leer_marcas(line, config)
            marks = list(dict.fromkeys(lectura.piezas + lectura.pegadas))
            if not marks:
                continue
            found.append(
                TextoConMarca(
                    entidad_id=text.entity_id,
                    texto=line,
                    hoja=hoja,
                    hoja_llave=llave,
                    marcas=marks,
                    campos=campos,
                )
            )
    return found, list(hojas.values())


def _marcas_del_plano(texts: list[NormalizedEntity], config: TextPatternConfig) -> dict[str, int]:
    """Every mark a drawing text names without ambiguity — the whole text or one
    of its MTEXT lines read as «unica» by the mark grammar — in its one spelling,
    with how many texts name it (R84). A placement's label is a drawing text,
    so the placements' marks are here too."""
    cuenta: Counter[str] = Counter()
    for text in texts:
        contenido = text.text or ""
        lineas = [contenido, *contenido.split("\n")] if "\n" in contenido else [contenido]
        nombradas = set()
        for linea in lineas:
            lectura = leer_marcas(linea, config)
            if lectura.tipo == "unica" and lectura.marca is not None:
                nombradas.add(_normal(lectura.marca, config))
        cuenta.update(nombradas)
    return dict(sorted(cuenta.items()))


def _flechas_de_titulos(
    entities: list[NormalizedEntity],
    config: TextPatternConfig,
    detail_boxes: list[BBox],
    sheet: Sheet,
    etiquetas: Collection[str],
) -> list[tuple[str, ElementSpec]]:
    """R124, R128: the titles a leader starts or lands at — texts made only of family words,
    marks and connectors (``_titulo``), of any length, inside a detail or labels of the cotas
    reader — each mark a candidate claim «señalada por flecha», with the family its title
    states (R130). Which of them stand is ``_senaladas_por_flecha``'s call."""
    titulos: list[tuple[NormalizedEntity, list[str], str | None, BBox, float]] = []
    for text in entities:
        if not text.is_textual or not text.text:
            continue
        leido = _titulo(text.text, config)
        if leido is None:
            continue
        centro = bbox_center(text.bbox)
        if text.entity_id not in etiquetas and not any(
            bbox_contains_point(box, centro) for box in detail_boxes
        ):
            continue
        alto = alto_de_texto(text)
        titulos.append((text, leido[0], leido[1], _extension_del_texto(text), alto))
    if not titulos:
        return []
    mediana = statistics.median(t[4] for t in titulos)
    ventanas = [
        (c[0] - _PUNTA_DE_FLECHA * h, c[1] - _PUNTA_DE_FLECHA * h,
         c[2] + _PUNTA_DE_FLECHA * h, c[3] + _PUNTA_DE_FLECHA * h)
        for _t, _m, _f, c, h in titulos
    ]  # fmt: skip
    abiertas = _Abiertas(
        [
            x
            for x in _cerca_de(entities, ventanas)
            if x.entity_type == EntityType.polyline and not x.is_closed
        ],
        4 * mediana,
        _SOBRE_ARISTA * mediana,
    )
    con_flecha = [
        (t, flecha) for t in titulos if (flecha := abiertas.flecha_de(t[3], t[4])) is not None
    ]
    # Texts that share one leader are one title («DADO D-1B» over the landing, «O D-1C» under it):
    # the family word of one states the family of all (R130).
    de_la_flecha: dict[str, str] = {}
    for (_t, _m, familia, _c, _h), flecha in con_flecha:
        if familia is not None:
            de_la_flecha.setdefault(flecha.entity_id, familia)
    salida: list[tuple[str, ElementSpec]] = []
    for (text, marcas, familia, caja, alto), flecha in con_flecha:
        familia = familia or de_la_flecha.get(flecha.entity_id)
        for marca in marcas:
            e = _Etiqueta(
                texto=text,
                marca=marca,
                x=(caja[0] + caja[2]) / 2,
                y=(caja[1] + caja[3]) / 2,
                alto=alto,
                llave=sheet(text)[1],
                en_detalle=True,
                familia=_familia_de_titulo(familia, marca),
            )
            aviso = f"sección: {_SENALADA}"
            # R139: the detail the leader points at draws the section AND the armado (CE-1's
            # pointed sections draw 4 bars and a stirrup): both are the drawing's, unread.
            # R155: a family only the prefix gives exempts nothing (D-1C: the AI's dado): the
            # parrillas are claimed too; the definition drops that claim when its final family,
            # stated, is a beam's (``_definir``).
            campos: list[Campo] = ["seccion", "longitudinales", "estribos"]
            if e.familia in FAMILIAS_CON_PARRILLA or e.familia is None:
                campos.append("parrillas")
            salida.append(
                (
                    text.entity_id,
                    _lectura_de_cotas(e, sheet, None, [aviso], _SENALADA, campos=campos),
                )
            )
    return salida


def _senaladas_por_flecha(
    specs: list[ElementSpec], flechas: list[tuple[str, ElementSpec]], config: TextPatternConfig
) -> list[ElementSpec]:
    """R124, R128, R132: a title a leader starts or lands at claims each of its marks whose
    section nothing in the drawing reads: ilegible, «señalada por flecha; se lee en E3», so the
    AI does not fill what the drawing points at. It is a block on the AI only: it stands only
    when no reading that names the mark (a note of the mark, a stack, a cuadro row, cotas, a
    callout; never the AI's) gives a section, so it never outranks and erases a value the
    drawing reads. A note of the family is not one (R132): it is the family's fallback. The
    title's own claimed readings of that mark, if any, say so; otherwise the claim is added.
    Marks compare in their one spelling (``_normal``, as the definitions join them, R136): a
    «K1» title never outranks a read «K-1 20X40». Where the leader points is E3."""
    if not flechas:
        return specs
    leidas = {
        _normal(s.mark, config)
        for s in specs
        if s.section_cm is not None
        and s.source != "ia"
        and not (s.source == "nota" and s.mark == s.family.upper())
    }
    salida = list(specs)
    for entidad, reclamo in flechas:
        marca = _normal(reclamo.mark, config)
        if marca in leidas:
            continue
        aviso = reclamo.avisos[0]
        suyas = [
            s
            for s in salida
            if s.metodo == "cotas" and entidad in s.entidades and _normal(s.mark, config) == marca
        ]
        for s in suyas:
            if aviso not in s.avisos:
                s.avisos.append(aviso)
            # R139: the leader claims the armado too.
            s.campos_con_texto = [
                c for c in CAMPOS if c in {*s.campos_con_texto, *reclamo.campos_con_texto}
            ]
        if not suyas:
            salida.append(reclamo)
    return salida


def _family_notes_that_name_a_mark(
    specs: list[ElementSpec],
    rechazos: list[Rechazo],
    texts: list[NormalizedEntity],
    config: TextPatternConfig,
) -> tuple[list[ElementSpec], list[Rechazo]]:
    """A family note («DALA 15X30 4#3 E#2@20») is the whole family's only when
    it names no mark (R79): a text in which a mark the drawing reads occurs —
    by the grammar (a title «CORTE K-1 …») or by the backstop's loose
    comparison — is not read as the family's. It is a «sin_lector» rejection
    naming those marks."""
    marks = {s.mark for s in specs if not (s.source == "nota" and s.mark == s.family.upper())}
    by_id = {t.entity_id: t for t in texts}
    kept: list[ElementSpec] = []
    nuevos: list[Rechazo] = []
    for spec in specs:
        if not (spec.source == "nota" and spec.mark == spec.family.upper()):
            kept.append(spec)
            continue
        entidad = by_id.get(spec.entidades[0]) if spec.entidades else None
        texto = (entidad.text or "") if entidad is not None else spec.source_text
        nombradas = titulos(texto, config) + [
            m for m in sorted(marks) if any(_aparece(m, line) for line in texto.split("\n"))
        ]
        if not nombradas:
            kept.append(spec)
            continue
        if any(r.entidad_id in spec.entidades for r in rechazos):
            continue  # ya la reporta la asociación («sin_lector»: un título)
        nuevos.append(
            Rechazo(
                entidad_id=spec.entidades[0] if spec.entidades else "",
                texto=texto.strip(),
                hoja=spec.hoja,
                motivo="sin_lector",
                marcas=list(dict.fromkeys(nombradas)),
            )
        )
    return kept, rechazos + nuevos


def _junto_a_su_seccion(
    rechazos: list[Rechazo],
    texts: list[NormalizedEntity],
    secciones: list[tuple[str, BBox, str, str]],
    sheet: Sheet,
    entities: list[NormalizedEntity] | None = None,
) -> None:
    """R140, R150, R154: an unowned armado text (``sin_dueno``) may be the armado of a drawn
    section a title owns: it carries the title's mark as «posible», which blocks the mark's AI
    for the fields it shows (``bloqueos_de``). Only a text that shows armado and nothing else
    counts (a general note, a size, a section never). Its section is the one a drawn leader from
    it ends inside, whatever the distance (R154: T4-4's «2#6» and the V from it to two bars of
    the section); else the nearest section its sheet's titles own or claim (R158: a section
    several titles reach, a beam where a slab meets it) within that section's larger side (R140)
    and three of its heights (R150) — three of its heights along its height band (a beam's
    elevation beside its section), 1.3 along its column (R161) — with no other heading or title
    between them (the section's own title is not another); of two equally near (within 10 %)
    both. A text nearer
    a dimensioned section nobody owns (a «CI» type detail), or whose leader ends inside one, is
    that section's: it stays unowned. So does anything else. Reading it is Task 9c."""
    if not secciones:
        return
    por_id = {t.entity_id: t for t in texts}
    candidatos = [
        (r, por_id[r.entidad_id])
        for r in rechazos
        if r.motivo == "sin_dueno"
        and not r.posibles
        and solo_armado(r.texto)  # only armado («4#4», «E#4», «1@6,8@10»)
        and r.entidad_id in por_id
    ]
    if not candidatos:
        return

    # The texts that may stand between an armado line and a section: headings, titles, notes
    # (anything with letters that is not itself an armado line) and every section's title, by
    # grid cell, where they really lie (R120: a notes MTEXT is its column, never the unwrapped
    # paragraph the normalizer's box spans across the sheet).
    altos = [h for t in texts if (h := _alto_de_renglon(t, 0.0)) > 0]
    celda = 20 * (statistics.median(altos) if altos else 1.0)
    titulos = {titulo for _m, _c, _l, titulo in secciones if titulo}
    rejilla: dict[tuple[int, int], list[tuple[str, BBox]]] = defaultdict(list)
    for t in texts:
        letras = re.search(r"[A-ZÁÉÍÓÚÑ]{2,}", (t.text or "").upper())
        if t.entity_id not in titulos and (not letras or solo_armado(t.text or "")):
            continue
        x0, y0, x1, y1 = real = _extension_del_texto(t)
        for i in range(math.floor(x0 / celda), math.floor(x1 / celda) + 1):
            for j in range(math.floor(y0 / celda), math.floor(y1 / celda) + 1):
                rejilla[(i, j)].append((t.entity_id, real))

    extension = {t.entity_id: _extension_del_texto(t) for _r, t in candidatos}

    def entre(texto: NormalizedEntity, caja: BBox, suyo: str) -> bool:
        """Whether a heading or title other than the section's own (``suyo``) lies on the way
        from ``texto`` to the section ``caja``."""
        cx, cy = bbox_center(extension[texto.entity_id])
        p = (min(max(cx, caja[0]), caja[2]), min(max(cy, caja[1]), caja[3]))
        vistos: set[str] = set()
        for i in range(math.floor(min(cx, p[0]) / celda), math.floor(max(cx, p[0]) / celda) + 1):
            for j in range(
                math.floor(min(cy, p[1]) / celda), math.floor(max(cy, p[1]) / celda) + 1
            ):
                for otro, real in rejilla.get((i, j), []):
                    if otro in vistos or otro in (texto.entity_id, suyo):
                        continue
                    vistos.add(otro)
                    if _distancia_tramo_caja((cx, cy), p, real) == 0.0:
                        return True
        return False

    # R154: the drawn leaders (open lines and polylines, LEADER and MULTILEADER) with a vertex at
    # an armado text: where their other ends lie.
    margen = {t.entity_id: _PUNTA_DE_FLECHA * _alto_de_renglon(t, 0.0) for _r, t in candidatos}
    ventanas = [
        (x0 - margen[i], y0 - margen[i], x1 + margen[i], y1 + margen[i])
        for i, (x0, y0, x1, y1) in extension.items()
    ]
    lineas = [
        [(float(q[0]), float(q[1])) for q in e.points or []]
        for e in _cerca_de(entities or [], ventanas)
        if e.entity_type in (EntityType.line, EntityType.polyline)
        and not e.is_closed
        and len(e.points or []) >= 2
    ]
    por_celda: dict[tuple[int, int], set[int]] = defaultdict(set)
    for n, puntos in enumerate(lineas):
        for qx, qy in puntos:
            por_celda[(math.floor(qx / celda), math.floor(qy / celda))].add(n)

    def puntas(texto: NormalizedEntity) -> list[tuple[float, float]]:
        """The far ends of the leaders drawn from ``texto``: of a line or polyline with a vertex
        at the text, its ends other than that vertex."""
        caja, m = extension[texto.entity_id], margen[texto.entity_id]
        cerca = {
            n
            for i in range(math.floor((caja[0] - m) / celda), math.floor((caja[2] + m) / celda) + 1)
            for j in range(math.floor((caja[1] - m) / celda), math.floor((caja[3] + m) / celda) + 1)
            for n in por_celda.get((i, j), ())
        }
        salida: list[tuple[float, float]] = []
        for n in sorted(cerca):
            puntos = lineas[n]
            junto = [k for k, q in enumerate(puntos) if _distancia_tramo_caja(q, q, caja) <= m]
            if junto:
                salida += [puntos[k] for k in (0, len(puntos) - 1) if k not in junto]
        return salida

    # R158: a beam's elevation drawn as one closed outline beside its section (a sloped one: TE-A's
    # ramp on ES-007): what is written on it is that title's, as with a leader.
    alzados = _alzados(
        [(marca, caja, suya) for marca, caja, suya, _t in secciones if marca],
        entities or [],
    )

    for r, texto in candidatos:
        llave = sheet(texto)[1]
        holgura = _alto_de_renglon(texto, 0.0)
        dentro = 0.05 * holgura
        apuntadas = {
            marca
            for q in puntas(texto)
            for marca, caja, suya, _titulo in secciones
            if suya in (llave, "")
            and caja[0] + dentro < q[0] < caja[2] - dentro
            and caja[1] + dentro < q[1] < caja[3] - dentro
        }
        if apuntadas:
            # Its leader ends inside the section: that section's, whatever the distance (one
            # nobody owns: its own armado, unowned).
            r.posibles = sorted(m for m in apuntadas if m)
            continue
        x0, y0, x1, y1 = extension[texto.entity_id]
        en_alzado = {
            marca
            for marca, suya, poligono in alzados
            if suya == llave
            and _junto_al_poligono(((x0 + x1) / 2, (y0 + y1) / 2), poligono, 2 * holgura)
        }
        if en_alzado:
            r.posibles = sorted(en_alzado)
            continue
        cerca: list[tuple[float, str]] = []
        for marca, caja, suya, titulo in secciones:
            if suya not in (llave, ""):
                continue
            dx = max(caja[0] - x1, 0.0, x0 - caja[2])
            dy = max(caja[1] - y1, 0.0, y0 - caja[3])
            d = math.hypot(dx, dy)
            # Its group (R140, R150, R158, R161): within the section's larger side and three of
            # its heights; along its height band (a beam's elevation beside its section, with its
            # bars and stirrups), three of its heights; along its column (the stack under or over
            # it), 1.3 of them. Nothing else between.
            w, h = caja[2] - caja[0], caja[3] - caja[1]
            banda = y1 >= caja[1] - 0.25 * h and y0 <= caja[3] + 0.25 * h
            columna = x1 >= caja[0] - 0.25 * w and x0 <= caja[2] + 0.25 * w
            alcance = min(max(w, h), 3 * h)
            if banda:
                alcance = 3 * h
            elif columna:
                alcance = max(alcance, _COLUMNA * h)
            if d <= alcance and not entre(texto, caja, titulo):
                cerca.append((d, marca))
        if cerca:
            minimo = min(d for d, _m in cerca)
            marcas = {m for d, m in cerca if d <= minimo * 1.1 + 1e-9}
            if "" not in marcas:  # nearest a section nobody owns: its armado, unowned
                r.posibles = sorted(marcas)


def _pilas_de_secciones(
    entities: list[NormalizedEntity],
    frames: list[SheetFrame],
    config: TextPatternConfig,
    secciones: list[SeccionDeTitulo],
    specs: list[ElementSpec],
    rechazos: list[Rechazo],
    sheet: Sheet,
    muros: dict[str, float],
) -> tuple[list[ElementSpec], list[Rechazo]]:
    """R147: the stacks under the detail titles' own drawn sections (``asociar_secciones``), read
    as ``detalle`` / ``pila`` under the title's mark, with the family its title states. Only an
    unowned text (all its rejections «sin_dueno», read by nobody) can be a stack line. A field is
    read from the stack only when the stack is ALL the detail writes of it: if any other text of
    the title's group shows that field — its elevation's labels, a callout, a line beside the
    section (a rejection on its sheet whose «posible» or whose marks name the title) — the stack
    holds part of it and the field is not read: it stays claimed (ilegible, the AI blocked) and
    the stack's line is quoted. What a stack reads leaves the rejections; a line two sections
    (or a section and a label) dispute keeps its rejection and carries them as «posible» (a
    block only)."""
    if not secciones:
        return [], rechazos
    consumidas = {e for s in specs if s.source != "ia" for e in s.entidades}
    motivos: dict[str, set[str]] = defaultdict(set)
    for r in rechazos:
        motivos[r.entidad_id].add(r.motivo)
    libres = {i for i, m in motivos.items() if m == {"sin_dueno"} and i not in consumidas}
    asociaciones, disputados = asociar_secciones(entities, frames, config, secciones, libres)
    por_id = {e.entity_id: e for e in entities}
    de_titulo = {s.titulo_id: s for s in secciones if s.lee}
    leidos = {
        (i, _plano(t)) for a in asociaciones for i, t in zip(a.entidades, a.textos, strict=True)
    }
    restantes = [r for r in rechazos if (r.entidad_id, _plano(r.texto)) not in leidos]
    for r in restantes:
        if r.motivo == "sin_dueno" and r.entidad_id in disputados:
            r.posibles = sorted({*r.posibles, *disputados[r.entidad_id]})
    salida: list[ElementSpec] = []
    for a in asociaciones:
        seccion = de_titulo[a.etiqueta_id]
        family = seccion.familia or family_of_mark(a.marca)
        marca = _normal(a.marca, config)
        lectura = _reading(a.textos, family)
        armado: Armado = lectura["armado"]
        suyos = {(i, _plano(t)) for i, t in zip(a.entidades, a.textos, strict=True)}
        titulo = por_id.get(a.etiqueta_id)
        llave = sheet(titulo)[1] if titulo is not None else ""
        fuera = [
            r
            for r in restantes
            if (r.entidad_id, _plano(r.texto)) not in suyos
            and r.entidad_id in por_id
            and sheet(por_id[r.entidad_id])[1] == llave
            and marca in {_normal(m, config) for m in [*r.posibles, *r.marcas] if m}
        ]
        for campo, clave in (
            ("longitudinales", "rebar"),
            ("estribos", "stirrups"),
            ("parrillas", "mesh"),
        ):
            if not getattr(armado, campo):
                continue
            otros = [r.texto for r in fuera if campo in campos_de_fragmento(r.texto, family)]
            if not otros:
                continue
            setattr(armado, campo, [])
            lectura[clave] = None
            de_la_pila = [t for t in a.textos if campo in campos_de_fragmento(t, family)]
            lectura["avisos"].append(
                f"{campo}: no se lee de la pila bajo su sección («"
                + "», «".join(de_la_pila)
                + f"»): el detalle de {a.marca} lo escribe también fuera de ella («"
                + "», «".join(dict.fromkeys(otros[:6]))
                + ("», …)" if len(dict.fromkeys(otros)) > 6 else "»)")
            )
        salida.append(
            ElementSpec(
                mark=a.marca,
                family=family,
                familia_supuesta=seccion.familia is None,
                source="detalle",
                metodo="pila",
                hoja=a.hoja,
                hoja_llave=llave,
                entidades=list(a.entidades),
                source_text=f"{a.marca} · {' / '.join(a.textos)} · bajo su sección",
                confidence=0.75,
                para_muro_cm=muros.get(a.etiqueta_id),
                **lectura,
            )
        )
    return salida, restantes


def _alzados(
    secciones: list[tuple[str, BBox, str]], entities: list[NormalizedEntity]
) -> list[tuple[str, str, list[tuple[float, float]]]]:
    """R158, R163: the elevation of each beam section drawn as one closed polyline beside it — its
    near end within the section's larger side of the section's side, overlapping at least half its
    height there and no taller there than 1.5 of its heights (beam-like: never a sheet's notes
    panel), and running away at least three of its widths (TE-A's ramp on ES-007): the mark, its
    sheet key and the polygon."""
    if not secciones:
        return []
    ventanas = []
    for _m, (x0, y0, x1, y1), _l in secciones:
        r = max(x1 - x0, y1 - y0)
        ventanas.append((x0 - r, y0, x1 + r, y1))
    poligonos = [
        [(float(q[0]), float(q[1])) for q in e.points or []]
        for e in _cerca_de(entities, ventanas)
        if e.entity_type == EntityType.polyline and e.is_closed and len(e.points or []) >= 4
    ]
    salida: list[tuple[str, str, list[tuple[float, float]]]] = []
    for marca, (x0, y0, x1, y1), llave in secciones:
        w, h = x1 - x0, y1 - y0
        for puntos in poligonos:
            xs = [x for x, _y in puntos]
            for lado, cerca, lejos in ((1, min(xs), max(xs)), (-1, max(xs), min(xs))):
                hueco = cerca - x1 if lado > 0 else x0 - cerca
                if not -0.05 * w <= hueco <= max(w, h) or abs(lejos - cerca) < 3 * w:
                    continue
                ys = [y for x, y in puntos if abs(x - cerca) <= 0.05 * w]
                if (
                    ys
                    and min(max(ys), y1) - max(min(ys), y0) >= 0.5 * h
                    and max(ys) - min(ys) <= 1.5 * h
                ):
                    salida.append((marca, llave, puntos))
    return salida


def _junto_al_poligono(
    p: tuple[float, float], poligono: list[tuple[float, float]], margen: float
) -> bool:
    """Whether the point lies inside the polygon or within ``margen`` of its edges."""
    dentro = False
    for (ax, ay), (bx, by) in zip(poligono, poligono[1:] + poligono[:1], strict=True):
        if (ay > p[1]) != (by > p[1]) and p[0] < ax + (p[1] - ay) * (bx - ax) / (by - ay):
            dentro = not dentro
    if dentro:
        return True
    return any(
        _distancia_tramo_caja(a, b, (p[0], p[1], p[0], p[1])) <= margen
        for a, b in zip(poligono, poligono[1:] + poligono[:1], strict=True)
    )


def _lo_que_nadie_leyo(
    texts: list[NormalizedEntity],
    specs: list[ElementSpec],
    rechazos: list[Rechazo],
    config: TextPatternConfig,
    sheet: Sheet,
    posibles: dict[str, set[str]] | None = None,
    leidos_por_reglas: dict[str, list[str]] | None = None,
) -> list[Rechazo]:
    """R104, the lossless audit after every reader: each line of a drawing text
    (an MTEXT, line by line) in which the parser reads or reports armado
    (``lo_ve_el_parser``, R108: a bar group, a stirrup set, a mesh, a section, a
    length, «V#3 @15», «@20», a lone «#3») is consumed by a reading
    — which reads or quotes each span (``_reading``) — or is in ``rechazos``.
    Anything else gets a rejection here: «sin_lector» with the marks it names
    (the grammar's, or its title's; «varias_marcas» for a list, as the
    association says), «sin_dueno» if it names none («1. 30X30 8#6», a section
    alone on a stack line, «3.- 4#3 E#2@20 VER CORTE C-2»: a pointer names
    nobody). A rejection in a label's column past its stack's cut carries that
    label as «posible» (``posibles``, R111, R116): it blocks that label's AI. A
    line the rules reader read (``leidos_por_reglas``: a weld or lap note, an fy
    note) is consumed (R119)."""
    consumidas = {e for s in specs if s.source != "ia" for e in s.entidades}
    reglas = {
        entidad: {_plano(r) for r in renglones}
        for entidad, renglones in (leidos_por_reglas or {}).items()
    }
    rechazadas: dict[str, list[str]] = {}
    for r in rechazos:
        rechazadas.setdefault(r.entidad_id, []).append(_plano(r.texto))
    nuevos: list[Rechazo] = []
    for text in texts:
        if text.entity_id in consumidas:
            continue
        for linea in (text.text or "").split("\n"):
            linea = linea.strip()
            if not linea or not lo_ve_el_parser(linea):
                continue
            plana = _plano(linea)
            leidos = reglas.get(text.entity_id)
            if leidos is not None and (not leidos or plana in leidos):
                continue  # the rules reader read it (R119)
            if any(plana in r for r in rechazadas.get(text.entity_id, [])):
                continue
            lectura = leer_marcas(linea, config)
            marcas = lectura.piezas or titulos(linea, config)
            motivo: Literal["sin_lector", "varias_marcas", "sin_dueno"] = (
                "varias_marcas"
                if lectura.tipo == "varias"
                else "sin_lector"
                if marcas
                else "sin_dueno"
            )
            nuevos.append(
                Rechazo(
                    entidad_id=text.entity_id,
                    texto=linea,
                    hoja=sheet(text)[0],
                    motivo=motivo,
                    marcas=list(marcas),
                    posibles=sorted((posibles or {}).get(text.entity_id, set())),
                )
            )
            rechazadas.setdefault(text.entity_id, []).append(plana)
    return nuevos


def build_schedule_inventory(
    entities: list[NormalizedEntity],
    config: TextPatternConfig | None = None,
    unit_to_m: float | None = None,
    detail_boxes: list[BBox] | None = None,
    extra_readers: list[Callable[[list[NormalizedEntity]], list[ElementSpec]]] | None = None,
    frames: list[SheetFrame] | None = None,
) -> ScheduleInventory:
    """Every reading of the sheet's specifications, with its source, and the
    by-mark / by-family view the takeoff reads. ``frames`` names the sheets
    (and, when ``detail_boxes`` is not given, the detail frames are its
    «excluded» frames); without frames each file is one sheet."""
    config = config or TextPatternConfig()
    frames = frames or []
    if detail_boxes is None and frames:
        detail_boxes = [f.bbox for f in frames if f.kind == "excluded"]
    sheet = hoja_y_llave(frames)
    texts = [e for e in entities if e.is_textual and e.text]
    posibles: dict[str, set[str]] = {}
    specs, labels, rechazos, tables = _read_associations(entities, frames, config, posibles)
    notes, rechazos_de_notas = _parse_annotations(texts, config, sheet)
    specs += notes
    rechazos = rechazos + rechazos_de_notas
    inventory_cuadro_marks: list[str] = []
    titulos_de_detalle: list[str] = []
    secciones_dibujadas: list[tuple[str, BBox, str, str]] = []
    para_pilas: list[SeccionDeTitulo] = []
    dibujadas: set[str] = set()
    flechas: list[tuple[str, ElementSpec]] = []
    if unit_to_m and detail_boxes:
        de_geometria = _sections_from_detail_geometry(
            entities, config, unit_to_m, detail_boxes, sheet
        )
        specs += de_geometria
        dibujadas = {i for s in de_geometria if s.section_cm for i in s.entidades}
    if detail_boxes or unit_to_m:
        callouts = (
            _sections_from_section_callouts(texts, config, detail_boxes, sheet)
            if detail_boxes
            else []
        )
        specs += callouts
        if unit_to_m:
            widths: dict[str, Counter] = {}
            for spec in callouts:
                if spec.section_cm:
                    widths.setdefault(spec.family, Counter())[spec.section_cm[0]] += 1
            usual = {f: c.most_common(1)[0][0] for f, c in widths.items()}
            cuadro_marks: list[str] = []
            de_cotas: list[Rechazo] = []
            specs += _sections_from_detail_cotas(
                entities,
                config,
                unit_to_m,
                detail_boxes or [],
                usual,
                cuadro_marks,
                sheet,
                de_cotas,
                set(labels),
                dibujadas,
                titulos_de_detalle,
                secciones_dibujadas,
                para_pilas,
            )
            # R124, R128: the titles a leader starts or lands at, each mark a candidate claim.
            flechas = _flechas_de_titulos(
                entities, config, detail_boxes or [], sheet, {*cuadro_marks, *labels}
            )
            # R156: a title a leader starts or lands at has its section where the leader points
            # (E3): the outline under it is not its own and says nothing of its shape (CTA-15 on
            # ES-500 over D-4's trapezoid).
            con_flecha = {entidad for entidad, _reclamo in flechas}
            for lectura in specs:
                if lectura.seccion_no_rectangular and set(lectura.entidades[:1]) & con_flecha:
                    lectura.seccion_no_rectangular = False
                    lectura.avisos = [a for a in lectura.avisos if a != _NO_RECTANGULAR]
            rechazos = rechazos + de_cotas
            inventory_cuadro_marks = cuadro_marks
    # Lectores por disciplina (cuadro de cancelería, tablero eléctrico…):
    # sus entradas llegan con el rango que ellas declaren — normalmente
    # «cuadro», porque la tabla del plano es la autoridad de su disciplina.
    for reader in extra_readers or []:
        specs += reader(entities)
    specs, rechazos = _family_notes_that_name_a_mark(specs, rechazos, texts, config)
    specs = _senaladas_por_flecha(specs, flechas, config)
    # R145: a title carrying a «señalada» leader is a detail title too.
    senaladas = {e for s in specs if s.source_text.endswith(_SENALADA) for e in s.entidades} | {
        e for s in specs if any(a.endswith(_SENALADA) for a in s.avisos) for e in s.entidades
    }
    titulos_de_detalle = sorted({*titulos_de_detalle, *senaladas})
    # R168: a title whose subtitle declares the wall its detail is for makes its readings that
    # variant of its mark («CI (PARA MUROS DE 15CM)»).
    muros = _muros_de_los_titulos(
        texts, {s.entidades[0] for s in specs if s.metodo == "cotas" and s.entidades}
    )
    for s in specs:
        if s.metodo in ("cotas", "geometria") and s.entidades and s.entidades[0] in muros:
            s.para_muro_cm = muros[s.entidades[0]]
    leidos_por_reglas = leer_reglas(entities, frames).textos_leidos
    rechazos = rechazos + _lo_que_nadie_leyo(
        texts, specs, rechazos, config, sheet, posibles, leidos_por_reglas
    )
    for r in rechazos:  # R116: every rejection past a cut, whoever made it, carries the label
        if not r.posibles and r.entidad_id in posibles:
            r.posibles = sorted(posibles[r.entidad_id])
    _junto_a_su_seccion(rechazos, texts, secciones_dibujadas, sheet, entities)
    # R147: the armado of a detail title, read from under its own drawn section.
    de_secciones, rechazos = _pilas_de_secciones(
        entities, frames, config, para_pilas, specs, rechazos, sheet, muros
    )
    specs += de_secciones
    inventory = ScheduleInventory(
        specs=specs,
        tables_found=tables,
        concrete_fc=parse_concrete_fc([t.text or "" for t in texts]),
        pile_length_m=parse_pile_length([t.text or "" for t in texts]),
        # Both feed it: a label that owns a stack or a cuadro row, and a mark
        # drawn with armado beside it in a planta (the cotas reader).
        cuadro_mark_entities=_union(labels, inventory_cuadro_marks, titulos_de_detalle),
        titulos_de_detalle=titulos_de_detalle,
        rechazos=rechazos,
        leidos_por_reglas=leidos_por_reglas,
    )
    inventory.textos_con_marca, inventory.textos_con_fragmento = _texts_naming_marks(
        texts, config, sheet
    )
    inventory.marcas_del_plano = _marcas_del_plano(texts, config)

    grouped: dict[str, list[ElementSpec]] = {}
    for spec in specs:
        grouped.setdefault(spec.mark.upper(), []).append(spec)
    disagreeing: list[str] = []
    for mark, candidates in grouped.items():
        best_rank = max(_SOURCE_RANK[s.source] for s in candidates)
        top = [s for s in candidates if _SOURCE_RANK[s.source] == best_rank]
        # A section read from the drawing's text beats one measured on the drawn outline, and
        # both beat an assumed one (R81: «detalle» > «seccion_dibujada» > «supuesto»).
        con_seccion = [s for s in top if s.section_cm]
        mejor = max((_peso_de_seccion(s) for s in con_seccion), default=0)
        sections = Counter(s.section_cm for s in con_seccion if _peso_de_seccion(s) == mejor)
        chosen = next(
            (
                s
                for s in top
                if sections
                and s.section_cm == sections.most_common(1)[0][0]
                and _peso_de_seccion(s) == mejor
            ),
            top[0],
        )
        same_sheet = sorted(
            (s for s in top if s is not chosen and _same_sheet(s, chosen)),
            key=lambda s: -_peso_de_seccion(s),
        )
        chosen = _merge_fields(chosen, same_sheet)
        disagreements = _disagreements(top, chosen)
        if disagreements:
            chosen.avisos = _union(chosen.avisos, disagreements)
            disagreeing.append(mark)
        if any(s.source != "nota" or s.mark != s.family.upper() for s in candidates):
            inventory.by_mark[mark] = chosen
        else:
            inventory.by_family[chosen.family] = chosen
    for spec in list(inventory.by_mark.values()):
        if spec.mark == spec.family.upper():
            inventory.by_family[spec.family] = inventory.by_mark.pop(spec.mark)

    stacks = [s for s in specs if s.metodo == "pila"]
    rows = [s for s in specs if s.metodo == "fila"]
    if rows:
        inventory.notes.append(
            f"{tables} cuadro(s) de elementos leído(s) del plano ({len(rows)} fila(s))."
        )
    if stacks:
        inventory.notes.append(
            f"{len(stacks)} pila(s) de armado leída(s) junto a su marca en "
            f"{len({s.hoja for s in stacks})} hoja(s)."
        )
    unread = [s for s in specs if s.avisos and s.metodo in ("fila", "pila", "nota")]
    if unread:
        inventory.notes.append(
            f"{len(unread)} lectura(s) con texto que no se pudo leer entero (se avisa en cada una)."
        )
    if rechazos:
        motivos = Counter(r.motivo for r in rechazos)
        inventory.notes.append(
            "Textos de armado que no se pegaron a una marca: "
            + ", ".join(f"{n} {_MOTIVOS[motivo]}" for motivo, n in sorted(motivos.items()))
            + "."
        )
    if disagreeing:
        inventory.notes.append(
            "Lecturas que no coinciden (se comparan en la lectura estructural): "
            + ", ".join(sorted(disagreeing)[:12])
            + (f" y {len(disagreeing) - 12} más" if len(disagreeing) > 12 else "")
            + "."
        )
    if inventory.by_mark:
        marks = ", ".join(sorted(inventory.by_mark)[:8])
        inventory.notes.append(f"Especificaciones por marca: {marks}.")
    if inventory.by_family:
        families = ", ".join(
            f"{f} {s.section_cm[0]}x{s.section_cm[1]}" if s.section_cm else f
            for f, s in sorted(inventory.by_family.items())
        )
        inventory.notes.append(f"Especificaciones generales: {families}.")
    if inventory.concrete_fc:
        inventory.notes.append(
            "Resistencias declaradas: "
            + ", ".join(f"{k} f'c={v}" for k, v in inventory.concrete_fc.items())
            + "."
        )
    if inventory.pile_length_m is not None:
        inventory.notes.append(f"Longitud de pilote declarada: {inventory.pile_length_m:g} m.")
    if not inventory.specs:
        inventory.notes.append("El plano no declara secciones ni armados por marca.")
    return inventory


def _peso_de_seccion(spec: ElementSpec) -> int:
    """How much a reading's section weighs against another of the same source: read from
    the drawing's text (2), measured on its drawn outline (1), assumed (0)."""
    if spec.seccion_supuesta:
        return 0
    return 1 if spec.metodo == "geometria" else 2


_MOTIVOS = {
    "ambigua": "ambiguos",
    "otra_familia": "de otra familia",
    "sin_lector": "sin lector",
    "varias_marcas": "de etiquetas con varias marcas",
    "sin_dueno": "sin dueño",
}


# The by-mark field an AI reading may fill, and the field of the drawing's text
# that keeps it from doing so.
_AI_FIELDS: tuple[tuple[str, Campo | None], ...] = (
    ("section_cm", "seccion"),
    ("rebar", "longitudinales"),
    ("stirrups", "estribos"),
    ("mesh", "parrillas"),
    ("length_m", "longitud"),
)


# The rejections that know whose text they are: a text two marks may claim, the
# stack or note of several marks, a text that names its mark but nobody reads.
_RECHAZOS_CON_MARCA = frozenset({"ambigua", "varias_marcas", "sin_lector"})


_PUNTO_ENTRE_LETRA_Y_CIFRA = re.compile(r"(?<=[A-Z])\.(?=\d)|(?<=\d)\.(?=[A-Z])")
_GUIONES_Y_ESPACIOS = re.compile(r"[\s\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]+")


def _loose_key(mark: str) -> str:
    """A mark as the AI block compares it (R65), on both sides, AI marks
    included: uppercase, without hyphens (any Unicode dash: «–», «‑», «—», R66)
    or spaces, without a dot between a letter and a digit. «K7», «K-7» and
    «K 7» are one key; «T1-1» and «T-11» too (they over-block each other: the
    safe direction). Only for blocking: readings and ``by_mark`` keep their
    marks as written."""
    return _GUIONES_Y_ESPACIOS.sub("", _PUNTO_ENTRE_LETRA_Y_CIFRA.sub("", mark.upper()))


def _normal(mark: str, config: TextPatternConfig) -> str:
    """A mark's one spelling (``marcas.marca_normalizada``); what is not a mark, as written."""
    return marca_normalizada(mark, config) or " ".join(mark.upper().split())


def marcas_del_dibujo(inventory: ScheduleInventory, config: TextPatternConfig) -> set[str]:
    """The marks of the drawing (R84), in their one spelling: those its readings
    read, and every mark a drawing text names without ambiguity — a rejected
    text, a cuadro row, a label, a placement's label (``marcas_del_plano``)."""
    return {_normal(s.mark, config) for s in inventory.specs if s.source != "ia"} | set(
        inventory.marcas_del_plano
    )


_CEROS = re.compile(r"(?<!\d)0+(?=\d)")


def _llave_sin_ceros(mark: str) -> str:
    """The loose key without the leading zeros of its numbers (K-07 ≡ K-7, R68)."""
    return _CEROS.sub("", _loose_key(mark))


def misma_marca(a: str, b: str, dibujo: set[str], config: TextPatternConfig) -> bool:
    """Whether two marks are the same one for the AI block: the same spelling
    («K7», «K-7», «K 7», «K–7»), or the same loose key without leading zeros
    (R65, R68: «T1-1» and «T-11», «K-07» and «K-7») when they are not both
    distinct marks of the drawing (R74, R84)."""
    na, nb = _normal(a, config), _normal(b, config)
    if na == nb:
        return True
    if _llave_sin_ceros(a) != _llave_sin_ceros(b):
        return False
    return not (na in dibujo and nb in dibujo)


def _names(
    piece: str, mark: str, known: set[str], config: TextPatternConfig, dibujo: set[str]
) -> bool:
    """Whether a mark as a text writes it names ``mark`` (``misma_marca``;
    ``known`` holds the loose keys of the known marks). A range names both
    endpoints always, and every mark between same-letter endpoints («K-1 A
    K-4» → K-2A, K-3); a mixed-letter range («K-1 A C-4») only its endpoints.
    A glued form that is not a known mark («K-7E#3@20», «K7E#3») names every
    known mark it starts with, when what is left starts with a letter or a sign
    (so «K-15AE#3» is K-15A, never K-1) — R66."""
    if es_rango(piece, config):
        if any(misma_marca(end, mark, dibujo, config) for end in extremos_de_rango(piece, config)):
            return True
        return marca_en_rango(piece, mark, config)
    if misma_marca(piece, mark, dibujo, config):
        return True
    written, key = _loose_key(piece), _loose_key(mark)
    if written in known:
        return False
    # R66: a glued token blocks every known mark it validly starts with (default-deny when it
    # is ambiguous: «K7E#3» with K7 and K7E both known blocks both).
    return written.startswith(key) and _glued_rest(written[len(key) :]) and key in known


def _una_marca(texto: str, config: TextPatternConfig) -> str | None:
    """The one mark a text names without ambiguity (the grammar's «unica», or a
    single title «CORTE K-1 …»), or ``None``."""
    lectura = leer_marcas(texto, config)
    if lectura.tipo == "unica":
        return lectura.marca
    if lectura.tipo == "ninguna":
        nombradas = titulos(texto, config)
        return nombradas[0] if len(nombradas) == 1 else None
    return None


def _inequivoco(texto: str, mark: str, config: TextPatternConfig, dibujo: set[str]) -> bool:
    """Whether a text names ``mark`` and no other in its place: its one mark, a
    member of its list or an end of its range. A mark between the ends of a
    range, a candidate of a glued mark, a loose match: ambiguous (R74)."""
    una = _una_marca(texto, config)
    if una is not None:
        return misma_marca(una, mark, dibujo, config)
    lectura = leer_marcas(texto, config)
    if lectura.tipo != "varias":
        return False
    for pieza in lectura.piezas:
        extremos = extremos_de_rango(pieza, config) if es_rango(pieza, config) else [pieza]
        if any(misma_marca(e, mark, dibujo, config) for e in extremos):
            return True
    return False


def _glued_rest(rest: str) -> bool:
    """What follows a known mark inside a glued token: a letter or a sign («E#3@20», «#3@20»),
    never a digit or a decimal (that would be another, longer mark)."""
    return bool(rest) and not rest[0].isdigit() and rest[0] != "."


# R68: how the backstop sees a mark in a line. Between a mark's prefix letters
# and its number any spaces and dashes (ASCII or Unicode) are ignored («K 7»,
# «K–7», «K7» are K-7); where the mark has a dash between two numbers or before
# a letter of its own («T1-1», «K-1-A», «TE-A») the line must have a dash too;
# a letter glued to the number («K-15A») stays glued.
_SEPARA = rf"[\s{re.escape(GUIONES)}]"
_UN_GUION = rf"\s*[{re.escape(GUIONES)}]\s*"
_ATOMO = re.compile(rf"[^\W\d_]+|\d+|{_SEPARA}+|.")


@lru_cache(maxsize=4096)
def _patron_suelto(mark: str) -> re.Pattern[str] | None:
    """The loose pattern of ``mark`` for the backstop (R68): uppercase, the
    separators above, leading zeros of a number ignored (K-07 is K-7); on the
    left, the start or a character that is neither a letter nor a digit (a
    hyphen after a word counts: «TRABE-T 1»); on the right, never another digit
    or a decimal (K-1 is never in K-15 or K-1.1). A letter may follow a number
    (K-7 is in «K-7E#3@20») or a letter glued to it (K-15A is in
    «K-15AE#3@20»), never a mark that ends in a letter of its own («TE-A» is
    not in «TE-AB»)."""
    tipos: list[str] = []
    separado: list[bool] = []
    partes: list[str] = []
    cortes: list[int] = []  # where each atom (with what joins it to the previous one) starts
    trozos: list[str] = []
    antes = False
    for m in _ATOMO.finditer(mark.upper()):
        trozo = m.group(0)
        if re.fullmatch(_SEPARA + "+", trozo):
            antes = True
            continue
        tipo = "cifras" if trozo.isdigit() else "letras" if trozo.isalpha() else "otro"
        cortes.append(len(partes))
        trozos.append(trozo)
        if tipos:
            previo = tipos[-1]
            if previo == "letras" and tipo == "cifras" or "otro" in (previo, tipo):
                partes.append(f"{_SEPARA}*")
            elif antes or previo == tipo:
                partes.append(_UN_GUION)
            # a letter glued to the number stays glued
        partes.append(rf"0*{int(trozo)}" if tipo == "cifras" else re.escape(trozo))
        tipos.append(tipo)
        separado.append(antes)
        antes = False
    if not tipos:
        return None
    derecha = r"(?!\d|\.\d)"
    pegada = len(tipos) > 1 and tipos[-2] == "cifras" and not separado[-1]
    if tipos[-1] == "letras" and not pegada:
        derecha += r"(?![^\W\d_])"
    patron = "".join(partes) + derecha
    if len(tipos) > 1 and tipos[-2] == "cifras" and tipos[-1] == "letras" and len(trozos[-1]) == 1:
        # R78: the mark's own letter written apart, standing alone («K-15 A 4#3», «K-1 A 4#3»);
        # never the connector of a range or a list («K-1 A K-4», «K-1 A 4») nor a stirrup head
        # («K-8 E #3@20»).
        letra = trozos[-1]
        aparte = (
            "".join(partes[: cortes[-1]])
            + rf"\s+{letra}(?![^\W_])(?!\s+(?:\d|[A-Z]{{1,5}}{_SEPARA}*\d))"
            + (r"(?!\s*[#Ø])" if letra in "EG" else "")
        )
        patron = f"(?:{patron}|{aparte})"
    return re.compile(r"(?<![^\W_])" + patron)


@lru_cache(maxsize=65536)
def _sin_cuentas(line: str) -> str:
    return sin_cuentas_de_varillas(sin_referencias(line))


def _aparece(mark: str, line: str) -> bool:
    """Whether ``mark`` occurs in ``line`` under the backstop's loose
    comparison (``_patron_suelto``). A bar count is never a mark: «V4 #4», «P
    4#3» are looked at without their bar groups (``sin_cuentas_de_varillas``).
    A pointer names nothing (R99): «E#2@15 VER CORTE C-2» is looked at without
    it, so it never blocks C-2."""
    patron = _patron_suelto(mark)
    return patron is not None and patron.search(_sin_cuentas(line)) is not None


def bloqueos_de(
    inventory: ScheduleInventory,
    mark: str,
    config: TextPatternConfig,
    known: set[str] | None = None,
    family: str | None = None,
) -> list[Bloqueo]:
    """The drawing texts that say something about a field of ``mark``, read or
    not (default-deny), each with the field it claims (``campos_de_fragmento``,
    with the mark's ``family``: a castillo has no parrillas, R76):
    - its readings, read or not (their ``campos_con_texto``);
    - every line the mark grammar says names it (R64), unless a reading of
      ``mark`` consumed that text;
    - every rejected text that names it: ambiguous between marks, of several
      marks, unread;
    - every rejected line (any motive) in the mark's column past its stack's
      cut (R111, R116, «posible»): a block, never a Dato;
    - the backstop (R68), independent of the grammar: every line with a
      fragment where the mark occurs under a loose comparison
      (``_patron_suelto``), unless a reading of ``mark`` consumed it.
    A text that names one other mark the drawing reads («K-2A 20X20 4#4» for
    K-2, «K-1-A 15X20» for K-1, «T1-1 …» for T-11) never says anything of
    ``mark`` (R74). Each block says whether the text names ``mark`` and no
    other (``inequivoco``). Marks are compared by ``misma_marca``."""
    family = family or family_of_mark(mark)
    dibujo = marcas_del_dibujo(inventory, config)
    if known is None:
        known = {_loose_key(s.mark) for s in inventory.specs} | {
            _loose_key(m) for m in inventory.by_mark
        }
    drawing = [s for s in inventory.specs if s.source != "ia"]
    readings = [s for s in drawing if misma_marca(s.mark, mark, dibujo, config)]
    consumed = {e for s in readings for e in s.entidades}
    # A text a reading of any mark consumed sits in that reading's cuadro or detail.
    where: dict[str, Literal["cuadro", "detalle", "nota"]] = {}
    for s in drawing:
        if s.source in ("cuadro", "detalle", "nota"):
            for e in s.entidades:
                where.setdefault(e, s.source)  # type: ignore[arg-type]

    def de_otra(texto: str) -> bool:
        """R74: the text names one other mark the drawing reads."""
        una = _una_marca(texto, config)
        return (
            una is not None
            and _normal(una, config) in dibujo
            and not misma_marca(una, mark, dibujo, config)
        )

    found: list[Bloqueo] = []
    for s in readings:
        fuente = s.source if s.source in ("cuadro", "detalle") else "nota"
        found += [
            Bloqueo(
                campo=campo,
                texto=s.source_text,
                entidades=list(s.entidades),
                hoja=s.hoja,
                hoja_llave=s.hoja_llave,
                fuente=fuente,
                por="lectura",
            )
            for campo in s.campos_con_texto
        ]
    for t in inventory.textos_con_marca:
        if t.entidad_id in consumed or de_otra(t.texto):
            continue
        if any(_names(p, mark, known, config, dibujo) for p in t.marcas):
            found += [
                Bloqueo(
                    campo=campo,
                    texto=t.texto,
                    entidades=[t.entidad_id],
                    hoja=t.hoja,
                    hoja_llave=t.hoja_llave,
                    fuente=where.get(t.entidad_id, "nota"),
                    por="texto",
                    inequivoco=_inequivoco(t.texto, mark, config, dibujo),
                )
                for campo in campos_de_fragmento(t.texto, family)
            ]
    for r in inventory.rechazos:
        if r.motivo not in _RECHAZOS_CON_MARCA or r.entidad_id in consumed or de_otra(r.texto):
            continue
        if any(_names(p, mark, known, config, dibujo) for p in r.marcas):
            # A note names its marks; a stack line of a label (ambiguous, of several marks) not.
            nota = leer_marcas(r.texto, config).nombra or bool(titulos(r.texto, config))
            found += [
                Bloqueo(
                    campo=campo,
                    texto=r.texto,
                    entidades=[r.entidad_id],
                    hoja=r.hoja,
                    fuente="nota" if nota else "detalle",
                    por="rechazo",
                    inequivoco=nota and _inequivoco(r.texto, mark, config, dibujo),
                )
                for campo in campos_de_fragmento(r.texto, family)
            ]
    for r in inventory.rechazos:
        # R111, R116: a rejected line (any motive) in the mark's column past its stack's cut may be
        # the mark's.
        if not r.posibles or r.entidad_id in consumed:
            continue
        if any(_names(p, mark, known, config, dibujo) for p in r.posibles):
            found += [
                Bloqueo(
                    campo=campo,
                    texto=r.texto,
                    entidades=[r.entidad_id],
                    hoja=r.hoja,
                    fuente="detalle",
                    por="posible",
                    inequivoco=False,
                )
                for campo in campos_de_fragmento(r.texto, family)
            ]
    for hoja, linea in inventory.lineas_con_fragmento():
        if linea.entidad_id in consumed or not _aparece(mark, linea.texto):
            continue
        if de_otra(linea.texto):
            continue
        found += [
            Bloqueo(
                campo=campo,
                texto=linea.texto,
                entidades=[linea.entidad_id],
                hoja=hoja.hoja,
                hoja_llave=hoja.hoja_llave,
                fuente=where.get(linea.entidad_id, "nota"),
                por="respaldo",
                inequivoco=_inequivoco(linea.texto, mark, config, dibujo),
            )
            for campo in campos_de_fragmento(linea.texto, family)
        ]
    unique: dict[tuple[str, tuple[str, ...], str], Bloqueo] = {}
    for b in found:
        unique.setdefault((b.campo, tuple(b.entidades), b.texto), b)
    return list(unique.values())


def merge_external_specs(
    inventory: ScheduleInventory, specs: list[dict], config: TextPatternConfig
) -> int:
    """Specs read elsewhere (the AI reading of the sheet images): every one is
    kept as a reading (``source="ia"``), and it fills a by-mark field only when
    the view has nothing there and the drawing has no text for that field
    (``bloqueos_de``: its readings, any drawing line that names it and no reading
    of it consumed, any rejected text that names it, and the backstop: any
    line with a fragment where the mark occurs). An AI value never covers a
    drawing text, and the reading itself carries what was blocked and by which
    texts (``campos_bloqueados``, ``bloqueos``, R69): kept in ``specs`` with
    every field, it is never elected for a blocked one. A mark the drawing does
    not define takes what the AI says of the other fields (por confirmar).
    ``config`` is the project's: the marks are recognised with its tags.
    Returns how many marks were completed."""
    marks = {s.mark for s in inventory.specs if s.source != "ia"} | set(inventory.by_mark)
    marks |= {str(raw.get("mark") or "").strip() for raw in specs} - {""}
    known = {_loose_key(m) for m in marks}
    added = 0
    for raw in specs:
        try:
            spec = ElementSpec.model_validate(raw)
        except ValueError:
            continue
        if spec.source == "ia":
            spec.metodo = "ia"
        # An AI mark written with a Unicode dash («K‑7») is the same key as the drawing's.
        mark = con_guion(spec.mark).upper()
        bloqueos = bloqueos_de(inventory, mark, config, known, family=spec.family)
        with_text = {b.campo for b in bloqueos}
        # R69: the reading carries its block, so that no later stage elects a blocked value.
        spec.campos_bloqueados = [
            campo
            for field, campo in _AI_FIELDS
            if campo is not None and campo in with_text and getattr(spec, field) not in (None, "")
        ]
        spec.bloqueos = [b for b in bloqueos if b.campo in spec.campos_bloqueados]
        inventory.specs.append(spec)
        current = inventory.by_mark.get(mark)
        new = current is None
        if current is None:
            current = spec.model_copy(deep=True, update={"mark": mark})
            current.campos_bloqueados, current.bloqueos = [], []
            for field, _campo in _AI_FIELDS:
                setattr(current, field, None)
        filled: list[str] = []
        blocked: list[str] = []
        for field, campo in _AI_FIELDS:
            if getattr(current, field) is not None or getattr(spec, field) in (None, ""):
                continue
            if campo is not None and campo in with_text:
                blocked.append(field)  # the drawing has text for it: read, or reported
                continue
            setattr(current, field, getattr(spec, field))
            filled.append(field)
        if blocked:
            current.avisos = _union(
                current.avisos,
                [
                    f"{', '.join(blocked)}: el plano tiene texto (sin leer o sin marca segura); "
                    f"la lectura IA no lo llena"
                ],
            )
        if new:
            if filled:
                inventory.by_mark[mark] = current
                added += 1
            continue  # with nothing filled there is nothing the AI may say about this mark
        if filled:
            current.source_text = f"{current.source_text} + {spec.source_text}"[:120]
            current.avisos = _union(
                current.avisos,
                [f"{', '.join(filled)} de la lectura IA, por confirmar: «{spec.source_text}»"],
            )
            added += 1
    if added:
        inventory.notes.append(
            f"{added} marcas completadas con la lectura IA de las hojas (por confirmar)."
        )
    return added


def mark_cuadro_detections(detections: list[Detection], inventory: ScheduleInventory) -> int:
    """Detections born from a cuadro's mark text are type labels, not
    elements: they keep their evidence but carry role='cuadro' so no
    quantity counts them."""
    cuadro = set(inventory.cuadro_mark_entities)
    titulos = set(inventory.titulos_de_detalle)
    if not cuadro:
        return 0
    tagged = 0
    for detection in detections:
        if detection.detection_type not in (DetectionType.column_tag, DetectionType.beam_tag):
            continue
        if any(entity_id in cuadro for entity_id in detection.source_entities):
            detection.properties["role"] = "cuadro"
            if any(entity_id in titulos for entity_id in detection.source_entities):
                # R145: the title of a detail (its section is drawn, or a leader points at it).
                detection.properties["titulo_de_detalle"] = True
            detection.evidence.notes.append(
                "Marca dentro de un cuadro/detalle dibujado en la planta: nombra un tipo, "
                "no cuenta como elemento."
            )
            tagged += 1
    return tagged


# What a stamped section says of its source: the sheet's (read), or the sheet's with one side
# assumed (R112). Neither is a measured marker's.
_DEL_PLANO = frozenset({"cuadro", "supuesto"})


def apply_schedule(
    detections: list[Detection], inventory: ScheduleInventory, meters_factor: float | None
) -> int:
    """Stamp column/beam detections with the section their mark declares.
    The sheet's statement outranks a measured marker and any assumption. A
    section with an assumed side (``seccion_supuesta``) is stamped «supuesto»,
    never «cuadro» (R112)."""
    if meters_factor is None or meters_factor <= 0:
        return 0
    stamped = 0
    for detection in detections:
        if detection.detection_type not in (DetectionType.column_tag, DetectionType.beam_tag):
            continue
        mark = detection.label.strip().upper()
        spec = inventory.by_mark.get(mark) or inventory.by_family.get(family_of_mark(mark))
        if spec is None or spec.section_cm is None:
            continue
        a, b = spec.section_cm
        area_m2 = (a / 100.0) * (b / 100.0)
        props = detection.properties
        if "section_area_du2" in props and props.get("section_source") not in _DEL_PLANO:
            props["section_marker_du2"] = props["section_area_du2"]
        props["section_area_du2"] = round(area_m2 / (meters_factor**2), 6)
        props["section_source"] = "supuesto" if spec.seccion_supuesta else "cuadro"
        props["section_cm"] = f"{a}x{b}"
        props["spec_source"] = spec.source
        if spec.rebar:
            props["spec_rebar"] = spec.rebar
        if spec.stirrups:
            props["spec_stirrups"] = spec.stirrups
        origin = {
            "cuadro": "cuadro del plano",
            "detalle": "detalle",
            "nota": "nota",
            "ia": "lectura IA de la imagen de la hoja (por confirmar)",
        }[spec.source]
        como = "con un lado supuesto, " if spec.seccion_supuesta else ""
        detection.evidence.notes.append(
            f"Sección {a}x{b} cm {como}según {origin}: «{spec.source_text[:60]}»"
        )
        stamped += 1
    return stamped
