"""Element specifications stated on the sheet: the cuadro de castillos and
its informal cousins.

A structural sheet says what a mark *is* in one of three places, in
descending authority: a text table (MARCA | SECCIÓN | ARMADO | ESTRIBOS),
a detail where the mark sits next to "15x20  4#3  E#2@20", or a general
note ("ARMEX 15X30"). This module reads all three into one inventory keyed
by mark — with the source recorded — and stamps the matching detections
with their section so the takeoff uses the sheet's own numbers instead of
a typical value.
"""

import re
import statistics
from collections import Counter
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

from klave_engine.detection.results import Detection, DetectionType
from klave_engine.detection.text_patterns import TextPatternConfig, match_category
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import (
    BBox,
    bbox_center,
    bbox_contains_point,
    bbox_height,
    point_to_bbox_distance,
)

_SECTION_RE = re.compile(r"(?<![\dxX×])(\d{1,3})\s*[xX×]\s*(\d{1,3})(?![\dxX×])")
_BLOCK_RE = re.compile(r"\d{1,3}\s*[xX×]\s*\d{1,3}\s*[xX×]\s*\d{1,3}")
_REBAR_RE = re.compile(r"(\d{1,2})\s*(?:V|VAR|VARS|VARILLAS)?\s*#\s*(\d)(?!\s*@)", re.I)
_STIRRUP_RE = re.compile(r"E\s*#?\s*(\d)\s*@\s*(\d{1,3})", re.I)
_MESH_RE = re.compile(r"(?<![E\d])#\s*(\d)\s*@\s*(\d{1,3})", re.I)
_MARK_RE = re.compile(r"\b([KCT]|COL|CT|CTA|TB|ZC|ZCM|Z|D)\s*-?\s*(\d{1,2})([A-Z]?)\b")

_FAMILY_KEYWORDS: list[tuple[str, re.Pattern[str]]] = [
    ("dala", re.compile(r"\bDALA|\bCADENA\b", re.I)),
    ("contratrabe", re.compile(r"\bCONTRATRABE", re.I)),
    ("trabe", re.compile(r"\bTRABE|\bVIGA\b", re.I)),
    ("castillo", re.compile(r"\bCASTILLO|\bARMEX\b", re.I)),
    ("columna", re.compile(r"\bCOLUMNA", re.I)),
    ("zapata", re.compile(r"\bZAPATA", re.I)),
    ("muro", re.compile(r"\bMURO", re.I)),
]
_HEADER_KEYWORDS = re.compile(
    r"MARCA|CLAVE|TIPO|CASTILLO|COLUMNA|SECC|DIMENS|ARMADO|REFUERZO|VARILLA|ESTRIBO", re.I
)
_MIN_SIDE_CM, _MAX_SIDE_CM = 8, 400  # up to a 4 m zapata; a castillo starts at 8 cm
_SOURCE_RANK = {"cuadro": 3, "detalle": 2, "nota": 1, "ia": 0}

Source = Literal["cuadro", "detalle", "nota", "ia"]


class ElementSpec(BaseModel):
    mark: str  # "K-1", or the family name for family-level notes
    family: str
    section_cm: tuple[int, int] | None = None
    rebar: str | None = None  # longitudinal, e.g. "4#3"
    stirrups: str | None = None  # e.g. "#2@20"
    mesh: str | None = None  # parrilla / malla, e.g. "#4@20" (no E)
    # Declared length in m (pilotes): from the notes, the cuadro or the AI.
    length_m: float | None = None
    source: Source
    source_text: str
    confidence: float


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

def _parse_section(text: str) -> tuple[int, int] | None:
    blocked = [m.span() for m in _BLOCK_RE.finditer(text)]
    for m in _SECTION_RE.finditer(text):
        if any(s <= m.start() < e for s, e in blocked):
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if _MIN_SIDE_CM <= a <= _MAX_SIDE_CM and _MIN_SIDE_CM <= b <= _MAX_SIDE_CM:
            return (min(a, b), max(a, b))
    return None


def _parse_rebar(text: str) -> tuple[str | None, str | None, str | None]:
    stirrups = None
    stirrup_match = _STIRRUP_RE.search(text)
    if stirrup_match:
        stirrups = f"#{stirrup_match.group(1)}@{stirrup_match.group(2)}"
        text = text[: stirrup_match.start()] + text[stirrup_match.end():]
    mesh = None
    mesh_match = _MESH_RE.search(text)
    if mesh_match:
        mesh = f"#{mesh_match.group(1)}@{mesh_match.group(2)}"
        text = text[: mesh_match.start()] + text[mesh_match.end():]
    rebar_match = _REBAR_RE.search(text)
    rebar = f"{int(rebar_match.group(1))}#{rebar_match.group(2)}" if rebar_match else None
    return rebar, stirrups, mesh


def family_of_mark(mark: str) -> str:
    prefix = re.match(r"[A-Z]+", mark.upper())
    head = prefix.group(0) if prefix else ""
    return {
        "K": "castillo", "C": "columna", "COL": "columna", "T": "trabe", "TB": "trabe",
        "CT": "contratrabe", "CTA": "contratrabe", "Z": "zapata", "ZC": "zapata",
        "ZCM": "zapata", "D": "dala", "DL": "dala", "DAL": "dala", "CE": "dala",
        "CR": "cerramiento", "MC": "muro_concreto", "P": "pilote",
    }.get(head, "elemento")


def _family_in_text(text: str) -> str | None:
    for family, pattern in _FAMILY_KEYWORDS:
        if pattern.search(text):
            return family
    return None


def _mark_in_text(text: str, config: TextPatternConfig) -> str | None:
    stripped = text.strip().upper()
    if match_category(stripped, config, "column_tag") or match_category(
        stripped, config, "beam_tag"
    ):
        return stripped
    m = _MARK_RE.search(stripped)
    return f"{m.group(1)}-{int(m.group(2))}{m.group(3)}" if m else None


def _spec_from_text(
    text: str,
) -> tuple[tuple[int, int] | None, str | None, str | None, str | None]:
    return _parse_section(text), *_parse_rebar(text)


# -------------------------------------------------------------------- tables

def _rows(texts: list[NormalizedEntity]) -> list[list[NormalizedEntity]]:
    heights = [bbox_height(t.bbox) for t in texts if bbox_height(t.bbox) > 0]
    if not heights:
        return []
    tolerance = statistics.median(heights) * 0.6
    ordered = sorted(texts, key=lambda t: -bbox_center(t.bbox)[1])
    rows: list[list[NormalizedEntity]] = []
    for text in ordered:
        y = bbox_center(text.bbox)[1]
        if rows and abs(bbox_center(rows[-1][0].bbox)[1] - y) <= tolerance:
            rows[-1].append(text)
        else:
            rows.append([text])
    for row in rows:
        row.sort(key=lambda t: bbox_center(t.bbox)[0])
    return rows


def _parse_tables(
    texts: list[NormalizedEntity], config: TextPatternConfig
) -> tuple[list[ElementSpec], int]:
    rows = _rows(texts)
    specs: list[ElementSpec] = []
    tables = 0
    index = 0
    while index < len(rows):
        header = rows[index]
        keyword_cells = [
            cell for cell in header if cell.text and _HEADER_KEYWORDS.search(cell.text)
        ]
        # A header is a row of short column titles, not a line of notes.
        short = all(len((cell.text or "").split()) <= 3 for cell in header)
        if len(header) < 3 or len(keyword_cells) < 2 or not short:
            index += 1
            continue
        columns = [(bbox_center(cell.bbox)[0], (cell.text or "").upper()) for cell in header]
        xs = sorted(x for x, _t in columns)
        gaps = [b - a for a, b in zip(xs, xs[1:], strict=False)]
        spacing = statistics.median(gaps) if gaps else 1.0
        max_offset = 0.5 * spacing
        row_height = statistics.median(bbox_height(c.bbox) for c in header) or 1.0
        table_rows = 0
        cursor = index + 1
        previous_y = bbox_center(header[0].bbox)[1]
        while cursor < len(rows):
            row = rows[cursor]
            y = bbox_center(row[0].bbox)[1]
            if previous_y - y > row_height * 4:
                break
            previous_y = y
            cells: dict[str, str] = {}
            for cell in row:
                x = bbox_center(cell.bbox)[0]
                col_x, title = min(columns, key=lambda col: abs(col[0] - x))
                if abs(col_x - x) > max_offset:
                    continue  # not under a header column: not this table
                cells[title] = ((cells.get(title, "") + " " + (cell.text or "")).strip())
            if not cells:
                break
            mark = None
            for title, value in cells.items():
                if re.search(r"MARCA|CLAVE|TIPO|CASTILLO|COLUMNA|TRABE", title):
                    mark = _mark_in_text(value, config)
                    break
            if mark is None:
                for value in cells.values():
                    mark = _mark_in_text(value, config)
                    if mark:
                        break
            if mark is None:
                break
            joined = " ".join(cells.values())
            section, rebar, stirrups, mesh = _spec_from_text(joined)
            # A schedule row states a section, or at least bars and stirrups.
            if section is None and not (rebar and stirrups) and mesh is None:
                cursor += 1
                continue
            table_rows += 1
            specs.append(
                ElementSpec(
                    mark=mark, family=family_of_mark(mark), section_cm=section,
                    rebar=rebar, stirrups=stirrups, mesh=mesh, source="cuadro",
                    source_text=joined[:120], confidence=0.95,
                )
            )
            cursor += 1
        if table_rows:
            tables += 1
        index = max(cursor, index + 1)
    return specs, tables


# ------------------------------------------------------------- details/notes

_NOT_A_SECTION = re.compile(r"HUECO|PASO|ABERTURA|HASTA|M[AÁ]X|PERFORACI|PLACA|ANCLA", re.I)


def _section_is_the_elements(content: str) -> bool:
    """A family-level note names the element and then its section ("CADENA DE
    ENRASE 15x25"); a section preceded by hole/opening words is not one."""
    match = _SECTION_RE.search(content)
    if match is None:
        return False
    before = content[max(0, match.start() - 40):match.start()]
    return not _NOT_A_SECTION.search(before)


def _parse_annotations(
    texts: list[NormalizedEntity], config: TextPatternConfig
) -> list[ElementSpec]:
    specs: list[ElementSpec] = []
    spec_texts = []
    for text in texts:
        content = " ".join((text.text or "").split())
        if not content:
            continue
        section, rebar, stirrups, mesh = _spec_from_text(content)
        if section is None and rebar is None and mesh is None:
            continue
        mark = _mark_in_text(content, config)
        family = _family_in_text(content)
        if mark is not None:
            specs.append(
                ElementSpec(
                    mark=mark, family=family or family_of_mark(mark), section_cm=section,
                    rebar=rebar, stirrups=stirrups, mesh=mesh, source="nota",
                    source_text=content[:120], confidence=0.8,
                )
            )
        elif family is not None:
            if section is not None and not _section_is_the_elements(content):
                section = None  # "HUECOS DE HASTA 15X20 … CONTRATRABE": a hole, not a section
            if section is None and rebar is None and mesh is None:
                continue
            specs.append(
                ElementSpec(
                    mark=family.upper(), family=family, section_cm=section, rebar=rebar,
                    stirrups=stirrups, mesh=mesh, source="nota", source_text=content[:120],
                    confidence=0.6,
                )
            )
        else:
            spec_texts.append((text, section, rebar, stirrups, mesh, content))

    # Bare marks next to a bare spec: the detail drawing convention.
    for text in texts:
        content = (text.text or "").strip()
        mark = _mark_in_text(content, config)
        if mark is None or len(content) > 8:
            continue
        height = bbox_height(text.bbox) or 1.0
        radius = height * 6
        cx, cy = bbox_center(text.bbox)
        best = None
        for spec_text, section, rebar, stirrups, mesh, source_text in spec_texts:
            # Distance to the annotation's box: a long spec line starts next
            # to the mark even though its centre sits far to the right.
            distance = point_to_bbox_distance((cx, cy), spec_text.bbox)
            if distance <= radius and (best is None or distance < best[0]):
                best = (distance, section, rebar, stirrups, mesh, source_text)
        if best is not None:
            specs.append(
                ElementSpec(
                    mark=mark, family=family_of_mark(mark), section_cm=best[1],
                    rebar=best[2], stirrups=best[3], mesh=best[4], source="detalle",
                    source_text=f"{content} · {best[5]}"[:120], confidence=0.75,
                )
            )
    return specs


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
) -> list[ElementSpec]:
    """The detail convention without a cuadro: the mark sits right above a
    section drawn at real size (30×80 cm rectangle with its cotas). Only
    inside detail frames — a mark in a plan view has castillos beside it."""
    closed = [
        e for e in entities
        if e.entity_type == EntityType.polyline and e.is_closed
        and len(e.points or []) in (4, 5)
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
            lo <= o.bbox[0] - x0 <= hi and lo <= o.bbox[1] - y0 <= hi
            and lo <= x1 - o.bbox[2] <= hi and lo <= y1 - o.bbox[3] <= hi
            for o in closed if o is not e
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
        mark = _mark_in_text(content, config)
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
                mark=mark, family=family_of_mark(mark), section_cm=(a, b), source="detalle",
                source_text=f"{content} · sección dibujada {a}x{b} cm", confidence=0.7,
            )
        )
    return specs


_SECTION_LABEL_RE = re.compile(r"^SECCI[OÓ]N\s*(\d+)", re.I)
_BARE_SECTION_RE = re.compile(r"^(\d{2,3})\s*[xX×]\s*(\d{2,3})$")


def _sections_from_section_callouts(
    texts: list[NormalizedEntity], config: TextPatternConfig, detail_boxes: list[BBox]
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
        mark = _mark_in_text(content, config)
        if mark is None or len(content) > 8:
            continue
        box = box_of(t)
        if box is not None:
            marks.append((mark, bbox_center(t.bbox), box))
    found: dict[str, list[tuple[int, tuple[int, int]]]] = {}
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
        best: tuple[float, str] | None = None
        for mark, (mx, my), mbox in marks:
            if mbox != box:
                continue
            dx, dy = cx - mx, my - cy
            if not (-1.0 <= dx <= 30.0 and 0.0 <= dy <= 6.0):
                continue
            score = dx + 2 * dy
            if best is None or score < best[0]:
                best = (score, mark)
        if best is None:
            continue
        found.setdefault(best[1], []).append(
            (int(label[1]), (int(match.group(1)), int(match.group(2))))
        )
    specs: list[ElementSpec] = []
    for mark, cuts in found.items():
        cuts.sort()
        largest = max(cuts, key=lambda c: c[1][0] * c[1][1])[1]
        listed = ", ".join(f"sección {n} {a}x{b}" for n, (a, b) in cuts)
        specs.append(
            ElementSpec(
                mark=mark, family=family_of_mark(mark), section_cm=largest, source="detalle",
                source_text=f"{mark} · {listed} (se toma la mayor)"[:120], confidence=0.65,
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
        mark = _mark_in_text(content, config)
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
                t.is_textual and t.text and _ARMADO_TEXT_RE.search(t.text)
                and ((bbox_center(t.bbox)[0] - center[0]) ** 2
                     + (bbox_center(t.bbox)[1] - center[1]) ** 2) ** 0.5 <= armado_radius
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
        if depth is None and width is not None and not in_detail:
            depth = width  # a square castillo drawn with one cota
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
            confidence = 0.55
        else:
            continue
        specs.append(
            ElementSpec(
                mark=mark, family=family, section_cm=section, source="detalle",
                source_text=note[:120], confidence=confidence,
            )
        )
    return specs


def _merge_fields(chosen: ElementSpec, others: list[ElementSpec]) -> ElementSpec:
    """Same-rank specs complete each other: the drawn section plus the
    armado written beside the mark."""
    merged = chosen.model_copy()
    for other in others:
        if merged.section_cm is None and other.section_cm is not None:
            merged.section_cm = other.section_cm
        if merged.rebar is None and other.rebar is not None:
            merged.rebar = other.rebar
        if merged.stirrups is None and other.stirrups is not None:
            merged.stirrups = other.stirrups
        if merged.mesh is None and other.mesh is not None:
            merged.mesh = other.mesh
    return merged


def build_schedule_inventory(
    entities: list[NormalizedEntity],
    config: TextPatternConfig | None = None,
    unit_to_m: float | None = None,
    detail_boxes: list[BBox] | None = None,
    extra_readers: list[Callable[[list[NormalizedEntity]], list[ElementSpec]]] | None = None,
) -> ScheduleInventory:
    config = config or TextPatternConfig()
    texts = [e for e in entities if e.is_textual and e.text]
    table_specs, tables = _parse_tables(texts, config)
    specs = table_specs + _parse_annotations(texts, config)
    inventory_cuadro_marks: list[str] = []
    if unit_to_m and detail_boxes:
        specs += _sections_from_detail_geometry(entities, config, unit_to_m, detail_boxes)
    if detail_boxes or unit_to_m:
        callouts = (
            _sections_from_section_callouts(texts, config, detail_boxes) if detail_boxes else []
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
                entities, config, unit_to_m, detail_boxes or [], usual, cuadro_marks
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
        cuadro_mark_entities=inventory_cuadro_marks,
    )

    grouped: dict[str, list[ElementSpec]] = {}
    for spec in specs:
        grouped.setdefault(spec.mark.upper(), []).append(spec)
    for mark, candidates in grouped.items():
        best_rank = max(_SOURCE_RANK[s.source] for s in candidates)
        top = [s for s in candidates if _SOURCE_RANK[s.source] == best_rank]
        sections = Counter(s.section_cm for s in top if s.section_cm)
        chosen = next(
            (s for s in top if sections and s.section_cm == sections.most_common(1)[0][0]),
            top[0],
        )
        chosen = _merge_fields(chosen, [s for s in top if s is not chosen])
        if any(s.source != "nota" or s.mark != s.family.upper() for s in candidates):
            inventory.by_mark[mark] = chosen
        else:
            inventory.by_family[chosen.family] = chosen
    for spec in list(inventory.by_mark.values()):
        if spec.mark == spec.family.upper():
            inventory.by_family[spec.family] = inventory.by_mark.pop(spec.mark)

    if tables:
        inventory.notes.append(f"{tables} cuadro(s) de elementos leído(s) del plano.")
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


def merge_external_specs(inventory: ScheduleInventory, specs: list[dict]) -> int:
    """Specs read elsewhere (the AI reading of the sheet images) fill what the
    rules did not read: a mark without a section or armado takes them, a
    mark the rules already specified keeps the rules. Returns how many marks
    were completed."""
    added = 0
    for raw in specs:
        try:
            spec = ElementSpec.model_validate(raw)
        except ValueError:
            continue
        mark = spec.mark.upper()
        current = inventory.by_mark.get(mark)
        if current is None:
            inventory.by_mark[mark] = spec
            inventory.specs.append(spec)
            added += 1
            continue
        filled = False
        if current.section_cm is None and spec.section_cm is not None:
            current.section_cm = spec.section_cm
            filled = True
        if current.rebar is None and spec.rebar:
            current.rebar = spec.rebar
            filled = True
        if current.stirrups is None and spec.stirrups:
            current.stirrups = spec.stirrups
            filled = True
        if current.length_m is None and spec.length_m:
            current.length_m = spec.length_m
            filled = True
        if filled:
            current.source_text = f"{current.source_text} + {spec.source_text}"[:120]
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
            "cuadro": "cuadro del plano", "detalle": "detalle", "nota": "nota",
            "ia": "lectura IA de la imagen de la hoja (por confirmar)",
        }[spec.source]
        detection.evidence.notes.append(
            f"Sección {a}x{b} cm según {origin}: «{spec.source_text[:60]}»"
        )
        stamped += 1
    return stamped
