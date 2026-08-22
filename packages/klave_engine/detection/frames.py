"""Sheet frames: a drawing that is really a set of sheets tiled in model space.

Offices often keep a whole discipline in one file — twenty sheet frames laid
out side by side, each with its cajetín (sheet code, title, date, scale).
Nothing in a frame belongs to another frame, so frames are the strongest
segmentation there is: a plan frame is a plan view, a detail frame is
excluded from quantities, and a closed rectangle that *is* a frame is never
a slab.

A frame is a closed 4-corner polyline whose size repeats across the sheet
(≥ 2 of the same size, within 2 %) and that contains a sheet code like
``ES-101`` or ``S-101``; its title is the longest keyword-bearing text in the
cajetín strip, else in the frame.
"""

import re
from collections import Counter

from pydantic import BaseModel, Field

from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import BBox, bbox_center, bbox_contains_point

_SHEET_CODE_RE = re.compile(r"^[A-Z]{1,3}[- ]?\d{2,4}[A-Z]?$")
_TITLE_RE = re.compile(
    r"PLANTA|CIMENTACI|NIVEL|AZOTEA|ENTREPISO|SÓTANO|SOTANO|DETALLE|CORTE|ARMADO|CUADRO|"
    r"NOTAS|ISOM|FACHADA|ALZADO|LOSA|ESCALERA|ESTRUCTURA",
    re.I,
)
_EXCLUDE_RE = re.compile(
    r"DETALLE|TABLA|NOTAS?|CUADRO|ISOMETRIC|CORTE|FACHADA|SECCION|SECCIÓN|ARMADO|ANCLAJE|"
    r"SIMBOLOG|CROQUIS|LOCALIZAC|ESCALERA|ALZADO",
    re.I,
)
# A heading in the drawing area that says the sheet is a section or detail,
# whatever the cajetín claims (cajetines get copy-pasted between sheets).
_CONTENT_SECTION_RE = re.compile(
    r"^\s*[\"']?(CORTE|SECCI[OÓ]N|DETALLES?|ALZADO|FACHADA|NOTAS)\b", re.I
)
_CONTENT_PLAN_RE = re.compile(r"PLANTA|LOSA|NIVEL|ESTRUCTURA\s+DE", re.I)
_CONTACT_RE = re.compile(r"@|\bCEL\b|\bTEL\b|\bwww\.", re.I)
# Sheet formats are landscape or portrait paper: A-series is 1.41, common
# Mexican formats run up to ~2.1. Labels and strips are far outside that.
_FRAME_ASPECT = (1.15, 2.6)
_FRAME_MIN_ENTITIES = 40
_LEVEL_KEYWORDS: list[tuple[str, re.Pattern[str]]] = [
    ("cimentacion", re.compile(r"CIMENTACI", re.I)),
    ("roof_garden", re.compile(r"ROOF", re.I)),
    ("sotano", re.compile(r"S[ÓO]TANO", re.I)),
    ("planta_baja", re.compile(r"PLANTA\s+BAJA|\bP\.?B\.?\b", re.I)),
    ("planta_alta", re.compile(r"PLANTA\s+ALTA|\bP\.?A\.?\b", re.I)),
    ("azotea", re.compile(r"AZOTEA", re.I)),
    ("entrepiso", re.compile(r"ENTREPISO", re.I)),
]
_NIVEL_RE = re.compile(r"\bNIVEL\s*[-]?\s*(\d+)|\bN\s*[-+]?\s*(\d+)\b", re.I)


class SheetFrame(BaseModel):
    frame_id: str
    bbox: BBox
    code: str = ""
    title: str = ""
    kind: str = "plan"  # plan | excluded | unknown
    level_key: str | None = None
    text_count: int = 0
    notes: list[str] = Field(default_factory=list)

    def contains(self, point: tuple[float, float]) -> bool:
        return bbox_contains_point(self.bbox, point)


def _rect_size(entity: NormalizedEntity) -> tuple[float, float] | None:
    if entity.entity_type != EntityType.polyline or not entity.is_closed or not entity.points:
        return None
    if len(entity.points) not in (4, 5):
        return None
    w = entity.bbox[2] - entity.bbox[0]
    h = entity.bbox[3] - entity.bbox[1]
    if w <= 0 or h <= 0:
        return None
    return (round(w, 2), round(h, 2))


def _classify(title: str) -> tuple[str, str | None]:
    if not title:
        return "unknown", None
    if _EXCLUDE_RE.search(title):
        return "excluded", None
    for key, pattern in _LEVEL_KEYWORDS:
        if pattern.search(title):
            return "plan", key
    nivel = _NIVEL_RE.search(title)
    if nivel:
        return "plan", f"nivel_{nivel.group(1) or nivel.group(2)}"
    if re.search(r"PLANTA|LOSA|ESTRUCTURA", title, re.I):
        return "plan", "planta"
    return "unknown", None


def detect_frames(entities: list[NormalizedEntity]) -> list[SheetFrame]:
    texts = [e for e in entities if e.is_textual and e.text]
    # A cajetín drawn as a block keeps its fields as attributes (plano:,
    # clave:); each value reads as a text standing at the insert.
    for e in entities:
        attributes = (e.properties or {}).get("attributes") if e.block_name else None
        if not isinstance(attributes, dict):
            continue
        for value in attributes.values():
            if isinstance(value, str) and value.strip():
                texts.append(
                    e.model_copy(
                        update={
                            "entity_type": EntityType.text,
                            "text": value.strip(),
                            "properties": {**(e.properties or {}), "height": 0.0},
                        }
                    )
                )
    codes = [e for e in texts if _SHEET_CODE_RE.match((e.text or "").strip().upper())]
    if len(codes) < 2:
        return []
    rects = [(e, size) for e in entities if (size := _rect_size(e)) is not None]
    # Frames repeat: keep rectangle sizes seen at least twice (±2 %).
    sizes = Counter(size for _e, size in rects)
    repeated = {size for size, n in sizes.items() if n >= 2}
    if not repeated:
        return []

    def size_matches(size: tuple[float, float]) -> bool:
        return any(
            abs(size[0] - r[0]) <= 0.02 * r[0] and abs(size[1] - r[1]) <= 0.02 * r[1]
            for r in repeated
        )

    candidates = [e for e, size in rects if size_matches(size)]
    centers = [bbox_center(e.bbox) for e in entities]
    frames: list[SheetFrame] = []
    taken: set[str] = set()
    for code_text in codes:
        point = bbox_center(code_text.bbox)
        containing = [e for e in candidates if bbox_contains_point(e.bbox, point)]
        if not containing:
            continue
        # The frame is the largest repeated rectangle around the code; the
        # cajetín is the smallest (used to find the title).
        containing.sort(key=lambda e: (e.bbox[2] - e.bbox[0]) * (e.bbox[3] - e.bbox[1]))
        outer = containing[-1]
        if outer.entity_id in taken:
            continue
        taken.add(outer.entity_id)
        width = outer.bbox[2] - outer.bbox[0]
        height = outer.bbox[3] - outer.bbox[1]
        aspect = max(width, height) / min(width, height)
        if not (_FRAME_ASPECT[0] <= aspect <= _FRAME_ASPECT[1]):
            continue
        if sum(1 for c in centers if bbox_contains_point(outer.bbox, c)) < _FRAME_MIN_ENTITIES:
            continue
        strip = containing[0].bbox if len(containing) > 1 else outer.bbox
        inside = [t for t in texts if bbox_contains_point(outer.bbox, bbox_center(t.bbox))]
        in_strip = [t for t in inside if bbox_contains_point(strip, bbox_center(t.bbox))]
        # The title lives in the cajetín: the strip, else the right-hand
        # fifth of the frame. Never the drawing area — a note like "CAMBIO
        # NIVEL EN LOSA" is not a sheet title.
        cajetin_zone = [
            t for t in inside if bbox_center(t.bbox)[0] >= outer.bbox[2] - 0.2 * width
        ]
        title = _pick_title(in_strip) or _pick_title(cajetin_zone)
        kind, level_key = _classify(title)
        notes: list[str] = []
        if kind == "plan":
            content = _content_heading(
                [t for t in inside if not bbox_contains_point(strip, bbox_center(t.bbox))],
                _text_height(next((t for t in in_strip if _norm(t) == title), None)),
            )
            if content:
                kind, level_key = "excluded", None
                notes.append(f"El cajetín dice «{title}» pero el contenido es «{content}».")
        frames.append(
            SheetFrame(
                frame_id=f"frame_{len(frames):02d}",
                bbox=outer.bbox,
                code=(code_text.text or "").strip().upper(),
                title=title,
                kind=kind,
                level_key=level_key,
                text_count=len(inside),
                notes=[f"Marco de {width:.1f}×{height:.1f}", *notes],
            )
        )
    frames.sort(key=lambda f: f.code)
    return frames


def _norm(t: NormalizedEntity) -> str:
    return " ".join((t.text or "").split())


def _text_height(t: NormalizedEntity | None) -> float:
    if t is None:
        return 0.0
    return float(t.properties.get("height", 0.0)) or (t.bbox[3] - t.bbox[1])


def _pick_title(texts: list[NormalizedEntity]) -> str:
    """Tallest keyword-bearing text; length only breaks ties. Contact lines
    ("INGENIERÍA ESTRUCTURAL … @ … Cel.") never are the title."""
    best = ""
    best_score = 0.0
    for t in texts:
        value = _norm(t)
        if not _TITLE_RE.search(value) or _SHEET_CODE_RE.match(value.upper()):
            continue
        if _CONTACT_RE.search(value):
            continue
        score = _text_height(t) * 10 + min(len(value), 80) / 800
        if score > best_score:
            best, best_score = value, score
    return best


def _content_heading(texts: list[NormalizedEntity], title_height: float) -> str:
    """The drawing-area heading that overrides a plan cajetín: a CORTE/DETALLE
    heading that is the tallest text in the area, clearly taller than the
    cajetín title, with no plan heading of its size."""
    section: tuple[float, str] | None = None
    tallest_plan = 0.0
    for t in texts:
        value = _norm(t)
        h = _text_height(t)
        if _CONTENT_SECTION_RE.search(value):
            if section is None or h > section[0]:
                section = (h, value)
        elif _CONTENT_PLAN_RE.search(value):
            tallest_plan = max(tallest_plan, h)
    if section is None:
        return ""
    h, value = section
    if h < 1.5 * title_height or tallest_plan >= h:
        return ""
    return value


def frame_boxes(frames: list[SheetFrame]) -> list[BBox]:
    return [f.bbox for f in frames]
