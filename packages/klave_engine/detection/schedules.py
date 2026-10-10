"""Element specifications stated on the sheet: the cuadro de castillos and
its informal cousins.

A structural sheet says what a mark *is* in one of three places, in
descending authority: a text table (MARCA | SECCIÓN | ARMADO | ESTRIBOS),
a detail where the mark sits under its stack of armado lines ("8#6" /
"2E#3EXT@10" / "CENTRO@20"), or a general note ("ARMEX 15X30"). This module
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

import re
from collections import Counter
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection, DetectionType
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.estructura.armado import (
    Armado,
    parsear_armado,
    texto_estribos,
    texto_longitudinal,
    texto_parrillas,
)
from klave_engine.estructura.asociacion import (
    ARMADO_RE,
    Rechazo,
    asociar,
    extremos_de_rango,
    fichas_de_marca,
    hoja_y_llave,
    lo_lee_una_nota,
    marca_en_rango,
    marca_en_texto,
    marcas_en_nota,
    nombra_varias,
)
from klave_engine.geometry.bbox import (
    BBox,
    bbox_center,
    bbox_contains_point,
    bbox_height,
)

_SECTION_RE = re.compile(r"(?<![\dxX×])(\d{1,3})\s*[xX×]\s*(\d{1,3})(?![\dxX×])")
_BLOCK_RE = re.compile(r"\d{1,3}\s*[xX×]\s*\d{1,3}\s*[xX×]\s*\d{1,3}")

_FAMILY_KEYWORDS: list[tuple[str, re.Pattern[str]]] = [
    ("dala", re.compile(r"\bDALA|\bCADENAS?\b", re.I)),
    ("contratrabe", re.compile(r"\bCONTRATRABE", re.I)),
    ("trabe", re.compile(r"\bTRABE|\bVIGAS?\b", re.I)),
    ("castillo", re.compile(r"\bCASTILLO|\bARMEX\b", re.I)),
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
Campo = Literal["seccion", "longitudinales", "estribos", "parrillas"]
CAMPOS: tuple[Campo, ...] = ("seccion", "longitudinales", "estribos", "parrillas")
_CAMPOS_DE_ARMADO: tuple[Campo, ...] = ("longitudinales", "estribos", "parrillas")
# A text's sheet: its name (``hoja``) and its unique key (``hoja_llave``).
Sheet = Callable[[NormalizedEntity], tuple[str, str]]


def _no_frames(e: NormalizedEntity) -> tuple[str, str]:
    return e.source_file, f"{e.source_file}#"


class ElementSpec(BaseModel):
    mark: str  # "K-1", or the family name for family-level notes
    family: str
    section_cm: tuple[int, int] | None = None
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
    # Armado texts the association could not give to a mark (ambiguous, unowned,
    # another family's…): reported, never read in silence.
    rechazos: list[Rechazo] = Field(default_factory=list)
    # Every drawing line that names marks and holds armado or a section (R64):
    # the AI never covers what they say, whoever reads them.
    textos_con_marca: list[TextoConMarca] = Field(default_factory=list)


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


def _read_section(text: str) -> tuple[tuple[int, int] | None, list[str], bool]:
    """The section written in ``text`` (the first NNxNN with both sides in
    8–400 cm), the avisos for what was not taken (a side out of range, a second
    different section) and whether the text has a section at all."""
    blocked = [m.span() for m in _BLOCK_RE.finditer(text)]
    section: tuple[int, int] | None = None
    avisos: list[str] = []
    found = False
    for m in _SECTION_RE.finditer(text):
        if any(s <= m.start() < e for s, e in blocked):
            continue
        found = True
        a, b = int(m.group(1)), int(m.group(2))
        if not (_MIN_SIDE_CM <= a <= _MAX_SIDE_CM and _MIN_SIDE_CM <= b <= _MAX_SIDE_CM):
            avisos.append(f"sección fuera de rango: «{m.group(0)}»: no se toma")
        elif section is None:
            section = (min(a, b), max(a, b))
        elif (min(a, b), max(a, b)) != section:
            avisos.append(
                f"otra sección en el mismo texto: «{m.group(0)}»; se toma {section[0]}x{section[1]}"
            )
    return section, avisos, found


def family_of_mark(mark: str) -> str:
    prefix = re.match(r"[A-Z]+", mark.upper())
    head = prefix.group(0) if prefix else ""
    return {
        "K": "castillo",
        "C": "columna",
        "COL": "columna",
        "T": "trabe",
        "TB": "trabe",
        "CT": "contratrabe",
        "CTA": "contratrabe",
        "Z": "zapata",
        "ZC": "zapata",
        "ZCM": "zapata",
        "D": "dala",
        "DL": "dala",
        "DAL": "dala",
        "CE": "dala",
        "CR": "cerramiento",
        "MC": "muro_concreto",
        "P": "pilote",
    }.get(head, "elemento")


def _family_in_text(text: str) -> str | None:
    for family, pattern in _FAMILY_KEYWORDS:
        if pattern.search(text):
            return family
    return None


def _render(render: Callable[[Armado], str], armado: Armado, avisos: list[str]) -> str | None:
    try:
        return render(armado) or None
    except ValueError as error:  # a parsed armado always renders; say so if it ever does not
        avisos.append(f"no se pudo escribir el armado leído: {error}")
        return None


def _reading(textos: list[str], family: str, section_of_the_element: bool = True) -> dict:
    """One reading of an armado text (one string per line) for an element of
    ``family``: its section, its parsed armado and the canonical renders, the
    fields whose text is there and every aviso. Text that could not be read
    leaves every armado field marked as present: nobody can tell which one it
    was meant for, so nobody fills them from elsewhere."""
    section, avisos, has_section = _read_section(" | ".join(textos))  # never across lines
    if not section_of_the_element:
        section, avisos, has_section = None, [], False
    armado = parsear_armado(textos, family)
    avisos = avisos + list(armado.avisos)
    rebar = _render(texto_longitudinal, armado, avisos)
    stirrups = _render(texto_estribos, armado, avisos)
    mesh = _render(texto_parrillas, armado, avisos)
    unread = bool(armado.avisos)
    campos: list[Campo] = []
    if has_section:
        campos.append("seccion")
    if armado.longitudinales or unread:
        campos.append("longitudinales")
    if armado.estribos or unread:
        campos.append("estribos")
    if armado.parrillas or unread:
        campos.append("parrillas")
    return {
        "section_cm": section,
        "rebar": rebar,
        "stirrups": stirrups,
        "mesh": mesh,
        "armado": armado,
        "campos_con_texto": campos,
        "avisos": avisos,
    }


def _has_something(reading: dict, content: str) -> bool:
    """A family note is a reading when it gave a section or armado, or when an
    armado-shaped text in it could not be read (a note about holes whose only
    numbers are its own numbering is not an armado reading)."""
    if reading["section_cm"] is not None or not reading["armado"].vacio():
        return True
    return bool(reading["avisos"]) and ARMADO_RE.search(content) is not None


# ------------------------------------------- cuadro rows, stacks and notes


def _read_associations(
    entities: list[NormalizedEntity],
    frames: list[SheetFrame],
    config: TextPatternConfig,
) -> tuple[list[ElementSpec], list[str], list[Rechazo], int]:
    """The cuadro rows and the stacks ``estructura.asociacion`` gives each
    mark, read through the parser: (specs, the labels that define a mark,
    the rejections, how many cuadros had rows read). A label that owns a
    stack or a row is a definition, never a placement."""
    asociaciones, rechazos = asociar(entities, frames, config)
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


_NOT_A_SECTION = re.compile(r"HUECO|PASO|ABERTURA|HASTA|M[AÁ]X|PERFORACI|PLACA|ANCLA", re.I)


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
    family ("DALA 15x30 4#3,E#2@20", "ARMEX 15X30"), read when it has a
    section, bars, a mesh or stirrups the parser reads (``lo_lee_una_nota``:
    the association reports the others as «sin lector»). A mark inside a
    reference ("VER CORTE C-2") is not the note's. A note naming several marks
    («K-1 Y K-2 15X20 4#3», «K-1 A K-4 …») is not read: it is a «varias_marcas»
    rejection with the marks as written (R63, like a stack under such a label).
    Bare armado lines are the association's, not a note's."""
    specs: list[ElementSpec] = []
    rechazos: list[Rechazo] = []
    for text in texts:
        content = " ".join((text.text or "").split())
        if not content or not lo_lee_una_nota(content):
            continue
        hoja, llave = sheet(text)
        marks = marcas_en_nota(content, config)
        if nombra_varias(marks):
            rechazos.append(
                Rechazo(
                    entidad_id=text.entity_id,
                    texto=(text.text or "").strip(),
                    hoja=hoja,
                    motivo="varias_marcas",
                    marcas=marks,
                )
            )
            continue
        mark = marks[0] if marks else None
        family = _family_in_text(content)
        if mark is not None:
            family = family or family_of_mark(mark)
            specs.append(
                ElementSpec(
                    mark=mark,
                    family=family,
                    source="nota",
                    metodo="nota",
                    hoja=hoja,
                    hoja_llave=llave,
                    entidades=[text.entity_id],
                    source_text=content[:120],
                    confidence=0.8,
                    **_reading([content], family),
                )
            )
        elif family is not None:
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
        height = bbox_height(text.bbox) or 1.0
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
    found: dict[tuple[str, str], list[tuple[int, tuple[int, int]]]] = {}
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
        height = bbox_height(t.bbox) or 0.1
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
            (int(label[1]), (int(match.group(1)), int(match.group(2))))
        )
        title_of.setdefault(key, best[2])
        cut_texts.setdefault(key, []).append(t.entity_id)
    specs: list[ElementSpec] = []
    for (mark, llave), cuts in found.items():
        cuts.sort()
        largest = max(cuts, key=lambda c: c[1][0] * c[1][1])[1]
        listed = ", ".join(f"sección {n} {a}x{b}" for n, (a, b) in cuts)
        aviso = (
            [f"varios cortes con secciones distintas ({listed}): se toma la mayor"]
            if len({c[1] for c in cuts}) > 1
            else []
        )
        title = title_of[(mark, llave)]
        specs.append(
            ElementSpec(
                mark=mark,
                family=family_of_mark(mark),
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
_COTA_WIDTH_CM = (12, 60)
_ARMADO_TEXT_RE = re.compile(r"\d\s*#\s*\d|#\s*\d\s*@\s*\d", re.I)


def _cota_cm(entity: NormalizedEntity, unit_to_m: float) -> float | None:
    """A dimension's value in centimetres: the displayed number when the
    sheet scales cotas (dimlfac), else the measured length."""
    props = entity.properties or {}
    display = props.get("display_value")
    dimlfac = props.get("dimlfac")
    if isinstance(display, (int, float)) and display > 0:
        if isinstance(dimlfac, (int, float)) and dimlfac > 0:
            # display = measured × dimlfac; measured is in drawing units.
            return float(display) / float(dimlfac) * unit_to_m * 100.0
        return float(display) * unit_to_m * 100.0
    measurement = props.get("measurement")
    if isinstance(measurement, (int, float)) and measurement > 0:
        return float(measurement) * unit_to_m * 100.0
    return None


def _sections_from_detail_cotas(
    entities: list[NormalizedEntity],
    config: TextPatternConfig,
    unit_to_m: float,
    detail_boxes: list[BBox],
    widths_by_family: dict[str, int],
    cuadro_marks: list[str] | None = None,
    sheet: Sheet = _no_frames,
) -> list[ElementSpec]:
    """The section drawing beside a mark in a detail carries its cotas: a
    vertical one is the peralte, a horizontal one the width. With only the
    peralte, the width the sheet's callouts use for that family is taken and
    said so; with neither, nothing is invented."""
    dims = [e for e in entities if e.entity_type == EntityType.dimension]
    if not dims:
        return []
    radius = 2.5 / unit_to_m
    specs: list[ElementSpec] = []
    for text in entities:
        if not text.is_textual or not text.text:
            continue
        content = text.text.strip()
        mark = marca_en_texto(content, config)
        if mark is None or len(content) > 8:
            continue
        center = bbox_center(text.bbox)
        in_detail = any(bbox_contains_point(box, center) for box in detail_boxes)
        if not in_detail:
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
                continue
            if cuadro_marks is not None:
                cuadro_marks.append(text.entity_id)
        depth: tuple[float, float] | None = None
        width: tuple[float, float] | None = None
        for dim in dims:
            dc = bbox_center(dim.bbox)
            distance = ((dc[0] - center[0]) ** 2 + (dc[1] - center[1]) ** 2) ** 0.5
            if distance > radius:
                continue
            value = _cota_cm(dim, unit_to_m)
            if value is None:
                continue
            vertical = (dim.bbox[3] - dim.bbox[1]) > (dim.bbox[2] - dim.bbox[0])
            if vertical and _COTA_DEPTH_CM[0] <= value <= _COTA_DEPTH_CM[1]:
                if depth is None or distance < depth[0]:
                    depth = (distance, value)
            elif not vertical and _COTA_WIDTH_CM[0] <= value <= _COTA_WIDTH_CM[1]:
                if width is None or distance < width[0]:
                    width = (distance, value)
        avisos: list[str] = []
        if depth is None and width is not None and not in_detail:
            depth = width  # a square castillo drawn with one cota
            avisos.append(f"una sola cota ({round(width[1])} cm): se supone sección cuadrada")
        if depth is None:
            continue
        family = family_of_mark(mark)
        if width is not None:
            section = (round(width[1]), round(depth[1]))
            note = f"{content} · cotas del detalle {section[0]}x{section[1]}"
            confidence = 0.7
        elif family in widths_by_family:
            section = (widths_by_family[family], round(depth[1]))
            note = (
                f"{content} · peralte {section[1]} acotado en el detalle; ancho "
                f"{section[0]} como las demás secciones de {family} del plano"
            )
            avisos.append(
                f"ancho {section[0]} supuesto: el de las demás secciones de {family} del plano"
            )
            confidence = 0.55
        else:
            continue
        specs.append(
            ElementSpec(
                mark=mark,
                family=family,
                section_cm=section,
                source="detalle",
                metodo="cotas",
                hoja=sheet(text)[0],
                hoja_llave=sheet(text)[1],
                entidades=[text.entity_id],
                campos_con_texto=["seccion"],
                avisos=avisos,
                source_text=note[:120],
                confidence=confidence,
            )
        )
    return specs


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


def _value_text(value: object) -> str:
    """How a value is compared and quoted: a section by its two sides, smaller
    first (the cotas give width × depth, the notes either way)."""
    if isinstance(value, tuple):
        a, b = sorted(value)
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
                said.setdefault(_value_text(value), set()).add(_sheet_name(r, readings))
        current = getattr(used, field)
        if not said or (len(said) == 1 and current is not None):
            continue
        listed = ", ".join(f"«{v}» ({', '.join(sorted(h))})" for v, h in said.items())
        here = f"«{_value_text(current)}»" if current is not None else "nada"
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
) -> list[TextoConMarca]:
    """Every line of every drawing text (model space and block contents, every
    sheet, MTEXT line by line) that names marks (``fichas_de_marca`` and the
    ranges of ``marcas_en_nota``; references excluded) and holds an armado- or
    section-shaped fragment (R64)."""
    found: list[TextoConMarca] = []
    for text in texts:
        for line in (text.text or "").split("\n"):
            line = line.strip()
            campos: list[Campo] = []
            if _read_section(line)[2]:
                campos.append("seccion")
            if _FORMA_DE_ARMADO.search(line):
                campos.extend(_CAMPOS_DE_ARMADO)
            if not campos:
                continue
            # Each mark-shaped token, plus the ranges as written («K-1 A 4» names K-2, K-3).
            ranges = [m for m in marcas_en_nota(line, config) if nombra_varias([m])]
            marks = list(dict.fromkeys(fichas_de_marca(line, config) + ranges))
            if not marks:
                continue
            hoja, llave = sheet(text)
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
    return found


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
    specs, labels, rechazos, tables = _read_associations(entities, frames, config)
    notes, rechazos_de_notas = _parse_annotations(texts, config, sheet)
    specs += notes
    rechazos = rechazos + rechazos_de_notas
    inventory_cuadro_marks: list[str] = []
    if unit_to_m and detail_boxes:
        specs += _sections_from_detail_geometry(entities, config, unit_to_m, detail_boxes, sheet)
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
            specs += _sections_from_detail_cotas(
                entities, config, unit_to_m, detail_boxes or [], usual, cuadro_marks, sheet
            )
            inventory_cuadro_marks = cuadro_marks
    # Lectores por disciplina (cuadro de cancelería, tablero eléctrico…):
    # sus entradas llegan con el rango que ellas declaren — normalmente
    # «cuadro», porque la tabla del plano es la autoridad de su disciplina.
    for reader in extra_readers or []:
        specs += reader(entities)
    inventory = ScheduleInventory(
        specs=specs,
        tables_found=tables,
        concrete_fc=parse_concrete_fc([t.text or "" for t in texts]),
        pile_length_m=parse_pile_length([t.text or "" for t in texts]),
        # Both feed it: a label that owns a stack or a cuadro row, and a mark
        # drawn with armado beside it in a planta (the cotas reader).
        cuadro_mark_entities=_union(labels, inventory_cuadro_marks),
        rechazos=rechazos,
        textos_con_marca=_texts_naming_marks(texts, config, sheet),
    )

    grouped: dict[str, list[ElementSpec]] = {}
    for spec in specs:
        grouped.setdefault(spec.mark.upper(), []).append(spec)
    disagreeing: list[str] = []
    for mark, candidates in grouped.items():
        best_rank = max(_SOURCE_RANK[s.source] for s in candidates)
        top = [s for s in candidates if _SOURCE_RANK[s.source] == best_rank]
        sections = Counter(s.section_cm for s in top if s.section_cm)
        chosen = next(
            (s for s in top if sections and s.section_cm == sections.most_common(1)[0][0]),
            top[0],
        )
        same_sheet = [s for s in top if s is not chosen and _same_sheet(s, chosen)]
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
    ("length_m", None),
)


# The rejections that know whose text they are: a text two marks may claim, the
# stack or note of several marks, a text that names its mark but nobody reads.
_RECHAZOS_CON_MARCA = frozenset({"ambigua", "varias_marcas", "sin_lector"})


def _names(piece: str, mark: str, known: set[str]) -> bool:
    """Whether a mark as a text writes it names ``mark``. A range names both
    endpoints always, and every mark between same-letter endpoints
    («K-1 A K-4» → K-2A, K-3); a mixed-letter range («K-1 A C-4») only its
    endpoints. A glued form that is not a known mark («K-7E#3@20») is the
    longest known mark it starts with, when what is left starts with a letter
    or a sign (so «K-15AE#3» is K-15A, never K-1)."""
    if nombra_varias([piece]):
        return mark in extremos_de_rango(piece) or marca_en_rango(piece, mark)
    piece = piece.upper()
    if piece == mark:
        return True
    if piece in known:
        return False
    prefixes = [k for k in known if piece.startswith(k) and _glued_rest(piece[len(k) :])]
    return bool(prefixes) and max(prefixes, key=len) == mark


def _glued_rest(rest: str) -> bool:
    """What follows a known mark inside a glued token: a letter or a sign («E#3@20», «#3@20»),
    never a digit or a decimal (that would be another, longer mark)."""
    return bool(rest) and not rest[0].isdigit() and rest[0] != "."


def _fields_with_text(inventory: ScheduleInventory, mark: str, known: set[str]) -> set[Campo]:
    """The fields of ``mark`` the drawing has text for (R64, default-deny):
    - those of its readings, read or not;
    - every field a drawing line that names it has a fragment for (armado →
      the three armado fields, a section → «seccion»), unless a reading of
      ``mark`` consumed that text;
    - every armado field (and the section, if it has one) of a rejected text
      that names it: ambiguous between marks, of several marks, unread.
    Glued forms and ranges are resolved by ``_names``."""
    readings = [s for s in inventory.specs if s.mark.upper() == mark and s.source != "ia"]
    campos: set[Campo] = {campo for s in readings for campo in s.campos_con_texto}
    consumed = {e for s in readings for e in s.entidades}
    for t in inventory.textos_con_marca:
        if t.entidad_id not in consumed and any(_names(p, mark, known) for p in t.marcas):
            campos.update(t.campos)
    for r in inventory.rechazos:
        if r.motivo in _RECHAZOS_CON_MARCA and any(_names(p, mark, known) for p in r.marcas):
            campos.update(_CAMPOS_DE_ARMADO)
            if _read_section(r.texto)[2]:
                campos.add("seccion")
    return campos


def merge_external_specs(inventory: ScheduleInventory, specs: list[dict]) -> int:
    """Specs read elsewhere (the AI reading of the sheet images): every one is
    kept as a reading (``source="ia"``), and it fills a by-mark field only when
    the view has nothing there and the drawing has no text for that field
    (``_fields_with_text``: its readings, any drawing line that names it and
    no reading of it consumed, any rejected text that names it). An AI value
    never covers a drawing text. A mark the drawing does not define takes what
    the AI says of the other fields (por confirmar). Returns how many marks
    were completed."""
    known = {s.mark.upper() for s in inventory.specs if s.source != "ia"} | set(inventory.by_mark)
    known |= {str(raw.get("mark") or "").strip().upper() for raw in specs} - {""}
    added = 0
    for raw in specs:
        try:
            spec = ElementSpec.model_validate(raw)
        except ValueError:
            continue
        if spec.source == "ia":
            spec.metodo = "ia"
        inventory.specs.append(spec)
        mark = spec.mark.upper()
        with_text = _fields_with_text(inventory, mark, known)
        current = inventory.by_mark.get(mark)
        new = current is None
        if current is None:
            current = spec.model_copy(deep=True)
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
    if not cuadro:
        return 0
    tagged = 0
    for detection in detections:
        if detection.detection_type not in (DetectionType.column_tag, DetectionType.beam_tag):
            continue
        if any(entity_id in cuadro for entity_id in detection.source_entities):
            detection.properties["role"] = "cuadro"
            detection.evidence.notes.append(
                "Marca dentro de un cuadro/detalle dibujado en la planta: nombra un tipo, "
                "no cuenta como elemento."
            )
            tagged += 1
    return tagged


def apply_schedule(
    detections: list[Detection], inventory: ScheduleInventory, meters_factor: float | None
) -> int:
    """Stamp column/beam detections with the section their mark declares.
    The sheet's statement outranks a measured marker and any assumption."""
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
        if "section_area_du2" in props and props.get("section_source") != "cuadro":
            props["section_marker_du2"] = props["section_area_du2"]
        props["section_area_du2"] = round(area_m2 / (meters_factor**2), 6)
        props["section_source"] = "cuadro"
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
        detection.evidence.notes.append(
            f"Sección {a}x{b} cm según {origin}: «{spec.source_text[:60]}»"
        )
        stamped += 1
    return stamped
