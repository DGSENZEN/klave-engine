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
from typing import Literal

from pydantic import BaseModel, Field

from klave_engine.detection.results import Detection, DetectionType
from klave_engine.detection.text_patterns import TextPatternConfig, match_category
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.geometry.bbox import bbox_center, bbox_height, point_to_bbox_distance

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
_MIN_SIDE_CM, _MAX_SIDE_CM = 8, 150
_SOURCE_RANK = {"cuadro": 3, "detalle": 2, "nota": 1}

Source = Literal["cuadro", "detalle", "nota"]


class ElementSpec(BaseModel):
    mark: str  # "K-1", or the family name for family-level notes
    family: str
    section_cm: tuple[int, int] | None = None
    rebar: str | None = None  # longitudinal, e.g. "4#3"
    stirrups: str | None = None  # e.g. "#2@20"
    mesh: str | None = None  # parrilla / malla, e.g. "#4@20" (no E)
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
    tables_found: int = 0
    notes: list[str] = Field(default_factory=list)


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
        "ZCM": "zapata", "D": "dala",
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
                _distance, title = min(columns, key=lambda col: abs(col[0] - x))
                cells[title] = ((cells.get(title, "") + " " + (cell.text or "")).strip())
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

def build_schedule_inventory(
    entities: list[NormalizedEntity], config: TextPatternConfig | None = None
) -> ScheduleInventory:
    config = config or TextPatternConfig()
    texts = [e for e in entities if e.is_textual and e.text]
    table_specs, tables = _parse_tables(texts, config)
    specs = table_specs + _parse_annotations(texts, config)
    inventory = ScheduleInventory(
        specs=specs,
        tables_found=tables,
        concrete_fc=parse_concrete_fc([t.text or "" for t in texts]),
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
    if not inventory.specs:
        inventory.notes.append("El plano no declara secciones ni armados por marca.")
    return inventory


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
        origin = {"cuadro": "cuadro del plano", "detalle": "detalle", "nota": "nota"}[spec.source]
        detection.evidence.notes.append(
            f"Sección {a}x{b} cm según {origin}: «{spec.source_text[:60]}»"
        )
        stamped += 1
    return stamped
