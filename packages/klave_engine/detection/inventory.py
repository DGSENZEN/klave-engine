"""Levantamiento por hoja: what a sheet contains, counted, before any price.

Instalaciones, acabados, cancelería and the rest are not drawn as
structural elements: they are symbols (block inserts — a luminaria, a
salida sanitaria, a cámara, a cancel) and runs of linework on a layer
(tubería hidráulica, ducto, línea de gas). The honest first reading of
such a sheet is an inventory: how many of each symbol, how many metres on
each layer, per sheet and per planta. Nothing here is priced; a taller
maps a symbol or a layer to a concept of its catálogo, and only then does
a count become a quantity.
"""

import math
import re
from collections import defaultdict

from pydantic import BaseModel, Field

from klave_engine.detection.frames import SheetFrame
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.dxf.units import DrawingUnits
from klave_engine.geometry.bbox import BBox, bbox_center, bbox_contains_point

# Symbols that belong to the sheet's apparatus, not to the work: cajetines,
# north arrows, level markers, axis bubbles, ezdxf/AutoCAD anonymous blocks.
_ANNOTATION_BLOCK_RE = re.compile(
    r"PIE DE PLANO|CAJET|TITLE|NORTE|^N$|^NPT$|^NIVEL|^EJE$|^EJES?\b|^A\$C|^\*|XREF|LOGO|"
    r"ESCALA|SIMBOLOG|^col$|^CH$",
    re.I,
)
_ANNOTATION_LAYER_RE = re.compile(
    r"COTA|DIM|TEXT|PIE DE PLANO|CAJET|PAPEL|DEFPOINTS|UBICA|EJE|GRID|AXIS|MARCO|FRAME|"
    r"SIMBOLOG|LEYENDA|HATCH|ACHUR|^0$",
    re.I,
)
_DISCIPLINE_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("hidraulica", re.compile(r"HIDR|AGUA|HPIP|CPIP|H\.?F\.?|H\.?C\.?", re.I)),
    ("sanitaria", re.compile(r"SANIT|PLUV|DREN|ALBA[ÑN]AL", re.I)),
    ("electrica", re.compile(r"ELEC|LUMIN|LAMP|CONTACT|APAG|TABLERO", re.I)),
    ("gas", re.compile(r"\bGAS\b|PEAD", re.I)),
    ("aire", re.compile(r"AIRE|\bAA\b|DUCTO|CLIMA|HVAC|MINISPLIT|COND", re.I)),
    ("cctv", re.compile(r"CCTV|CAMARA|CÁMARA|SEGURIDAD|SENSOR|ALARMA", re.I)),
    ("canceleria", re.compile(r"CANCEL|VENTANA|PUERTA|ALUM|HERRER", re.I)),
    ("acabados", re.compile(r"ACABAD|\bPISOS?\b|PLAFON|PINTURA|AZULEJO|LAMBR", re.I)),
    ("carpinteria", re.compile(r"CARPINT|MADERA|CLOSET|COCINA", re.I)),
    # La subida slugifica y pierde la ñ: «albañilería» llega como "alba iler a".
    ("albanileria", re.compile(r"ALBA[ÑN]ILER|ALBA\W?ILER", re.I)),
    ("indice", re.compile(r"\bINDICE\b|ÍNDICE|PORTADA|CAR[ÁA]TULA", re.I)),
    ("estructural", re.compile(r"EST|TRABE|LOSA|ZAPATA|CASTILL|COLUMN|CIMENT", re.I)),
]
# Element tags: one or two letters, a dash or nothing, one to three digits,
# an optional letter — V-1, P-12, VA-3, C2, M-1A. Not NPT levels or axes.
_TAG_RE = re.compile(r"^[A-Z]{1,2}-?\d{1,3}[A-Z]?$")
# Tags live on nomenclature/text layers; only cotas, cajetín and axes are not tags.
_TAG_SKIP_LAYER_RE = re.compile(
    r"COTA|DIM|PIE DE PLANO|CAJET|PAPEL|DEFPOINTS|UBICA|EJE|GRID|AXIS", re.I
)
_NOT_A_TAG_RE = re.compile(r"^(N|NPT|NIV|E|EJE|ES|IS|IH|IE|A|AR)-?\d", re.I)
_SPEC_RE = re.compile(
    r"(\d+\s*(?:MM|\")|Ø\s*\d+(?:/\d+)?\"?|\d+/\d+\"|PEAD|PVC|CPVC|COBRE|GALV|CAL\.?\s*\d+|"
    r"\d+\s*TON|\d+\s*BTU|\d+\s*W\b)",
    re.I,
)


class InventoryBlock(BaseModel):
    block_name: str
    layer: str
    count: int
    by_view: dict[str, int] = Field(default_factory=dict)


class InventoryRun(BaseModel):
    layer: str
    length_m: float | None  # None when the drawing unit is unknown
    length_du: float
    segments: int
    by_view: dict[str, float] = Field(default_factory=dict)


class InventoryTag(BaseModel):
    """A short mark repeated on the sheet: V-1, P-3, C-2 (cancelería,
    carpintería, plafones name each element type this way)."""

    tag: str
    count: int
    by_view: dict[str, int] = Field(default_factory=dict)


class InventoryArea(BaseModel):
    """Closed shapes and hatches on a layer: pisos, plafones, acabados de
    muro drawn as regions (m²)."""

    layer: str
    area_m2: float | None  # None when the drawing unit is unknown
    area_du2: float
    count: int
    by_view: dict[str, float] = Field(default_factory=dict)


class SheetInventory(BaseModel):
    sheet: str  # the parsed file, as entities name it
    label: str = ""  # the sheet as the user uploaded it
    discipline: str | None
    blocks: list[InventoryBlock] = Field(default_factory=list)
    runs: list[InventoryRun] = Field(default_factory=list)
    tags: list[InventoryTag] = Field(default_factory=list)
    areas: list[InventoryArea] = Field(default_factory=list)
    specs: list[str] = Field(default_factory=list)  # "TUBERÍA DE PEAD 19MM", "Ø 1/2""
    notes: list[str] = Field(default_factory=list)


class Inventory(BaseModel):
    sheets: list[SheetInventory] = Field(default_factory=list)
    unit: str | None = None
    notes: list[str] = Field(default_factory=list)


def guess_discipline(text: str) -> str | None:
    """Discipline named by a file name or by layer/block words. Uploaded
    files arrive slugified ("03-09_gas_l_04.dwg"), so separators become
    spaces before word-boundary hints like GAS or AA are tried."""
    words = re.sub(r"[_\-./]+", " ", text)
    for key, pattern in _DISCIPLINE_HINTS:
        if pattern.search(words):
            return key
    return None


# Sheets whose content is symbols and runs, never zapatas or trabes: the
# structural detectors stay off them, the levantamiento reads them.
NON_STRUCTURAL = frozenset(
    {"hidraulica", "sanitaria", "electrica", "gas", "aire", "cctv", "canceleria",
     "carpinteria", "acabados", "albanileria", "indice"}
)


def reads_as_structure(sheet_label: str) -> bool:
    """Whether the structural detectors should run on a sheet: yes unless its
    name says it is an installations/finishes sheet. Unknown names count
    as structure — a bare 'Plano 1.dwg' is the common case."""
    return guess_discipline(sheet_label) not in NON_STRUCTURAL


def _area(entity: NormalizedEntity) -> float:
    pts = entity.points or []
    if len(pts) < 3:
        return 0.0
    return abs(
        sum(
            pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
            for i in range(len(pts))
        )
    ) / 2.0


def _length(entity: NormalizedEntity) -> float:
    pts = entity.points or []
    if len(pts) < 2:
        return 0.0
    total = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    if entity.entity_type == EntityType.polyline and entity.is_closed:
        total += math.dist(pts[-1], pts[0])
    return total


def build_inventory(
    entities: list[NormalizedEntity],
    units: DrawingUnits | None = None,
    frames: list[SheetFrame] | None = None,
    min_run_m: float = 1.0,
    sheet_names: dict[str, str] | None = None,
    min_area_m2: float = 0.25,
) -> Inventory:
    to_m = units.to_meters() if units is not None else None
    plan_boxes: list[tuple[str, BBox]] = [
        (f"{f.code} · {f.title}".strip(" ·") or f.code, f.bbox)
        for f in (frames or []) if f.kind == "plan"
    ]

    def view_of(entity: NormalizedEntity) -> str | None:
        if not plan_boxes:
            return None
        center = bbox_center(entity.bbox)
        for title, box in plan_boxes:
            if bbox_contains_point(box, center):
                return title
        return None

    by_sheet: dict[str, list[NormalizedEntity]] = defaultdict(list)
    for entity in entities:
        by_sheet[entity.source_file].append(entity)

    inventory = Inventory(unit=units.unit if units is not None else None)
    for sheet, sheet_entities in by_sheet.items():
        blocks: dict[tuple[str, str], InventoryBlock] = {}
        runs: dict[str, InventoryRun] = {}
        tags: dict[str, InventoryTag] = {}
        attribute_tags: set[str] = set()
        areas: dict[str, InventoryArea] = {}
        specs: set[str] = set()
        for entity in sheet_entities:
            if entity.entity_type == EntityType.insert and entity.block_name:
                if _ANNOTATION_BLOCK_RE.search(entity.block_name) or _ANNOTATION_LAYER_RE.search(
                    entity.layer
                ):
                    continue
                key = (entity.block_name, entity.layer)
                block = blocks.get(key)
                if block is None:
                    block = blocks[key] = InventoryBlock(
                        block_name=entity.block_name, layer=entity.layer, count=0
                    )
                block.count += 1
                view = view_of(entity)
                if view:
                    block.by_view[view] = block.by_view.get(view, 0) + 1
                # A bubble's attribute is the element tag (CANC_ALUM → "V-3").
                for value in ((entity.properties or {}).get("attributes") or {}).values():
                    upper = " ".join(str(value).split()).upper()
                    if _TAG_RE.match(upper) and not _NOT_A_TAG_RE.match(upper):
                        tag = tags.get(upper)
                        if tag is None:
                            tag = tags[upper] = InventoryTag(tag=upper, count=0)
                        tag.count += 1
                        attribute_tags.add(upper)
                        if view:
                            tag.by_view[view] = tag.by_view.get(view, 0) + 1
            elif entity.entity_type in (EntityType.line, EntityType.polyline, EntityType.arc):
                if _ANNOTATION_LAYER_RE.search(entity.layer):
                    continue
                if entity.entity_type == EntityType.polyline and entity.is_closed:
                    region = _area(entity)
                    if region > 0:
                        area = areas.get(entity.layer)
                        if area is None:
                            area = areas[entity.layer] = InventoryArea(
                                layer=entity.layer, area_m2=None, area_du2=0.0, count=0
                            )
                        area.area_du2 += region
                        area.count += 1
                        view = view_of(entity)
                        if view:
                            area.by_view[view] = area.by_view.get(view, 0.0) + region
                length = _length(entity)
                if length <= 0:
                    continue
                run = runs.get(entity.layer)
                if run is None:
                    run = runs[entity.layer] = InventoryRun(
                        layer=entity.layer, length_m=None, length_du=0.0, segments=0
                    )
                run.length_du += length
                run.segments += 1
                view = view_of(entity)
                if view:
                    run.by_view[view] = run.by_view.get(view, 0.0) + length
            elif entity.entity_type == EntityType.hatch and not _ANNOTATION_LAYER_RE.search(
                entity.layer
            ):
                region = _area(entity)
                if region > 0:
                    area = areas.get(entity.layer)
                    if area is None:
                        area = areas[entity.layer] = InventoryArea(
                            layer=entity.layer, area_m2=None, area_du2=0.0, count=0
                        )
                    area.area_du2 += region
                    area.count += 1
                    view = view_of(entity)
                    if view:
                        area.by_view[view] = area.by_view.get(view, 0.0) + region
            elif entity.is_textual and entity.text:
                # AutoCAD control codes: %%C is Ø, %%D is °, %%P is ±.
                content = " ".join(
                    entity.text.replace("%%C", "Ø").replace("%%c", "Ø")
                    .replace("%%D", "°").replace("%%d", "°").replace("%%P", "±").split()
                )
                if _SPEC_RE.search(content) and 4 <= len(content) <= 80:
                    specs.add(content)
                upper = content.upper()
                if (
                    _TAG_RE.match(upper) and not _NOT_A_TAG_RE.match(upper)
                    and not _TAG_SKIP_LAYER_RE.search(entity.layer)
                ):
                    tag = tags.get(upper)
                    if tag is None:
                        tag = tags[upper] = InventoryTag(tag=upper, count=0)
                    tag.count += 1
                    view = view_of(entity)
                    if view:
                        tag.by_view[view] = tag.by_view.get(view, 0) + 1

        kept_runs: list[InventoryRun] = []
        for run in runs.values():
            if to_m is not None:
                run.length_m = round(run.length_du * to_m, 2)
                run.by_view = {k: round(v * to_m, 2) for k, v in run.by_view.items()}
                if run.length_m < min_run_m:
                    continue
            run.length_du = round(run.length_du, 3)
            kept_runs.append(run)
        kept_runs.sort(key=lambda r: -(r.length_m if r.length_m is not None else r.length_du))
        kept_areas: list[InventoryArea] = []
        for area in areas.values():
            if to_m is not None:
                area.area_m2 = round(area.area_du2 * to_m * to_m, 2)
                area.by_view = {k: round(v * to_m * to_m, 2) for k, v in area.by_view.items()}
                if area.area_m2 < min_area_m2:
                    continue
            area.area_du2 = round(area.area_du2, 3)
            kept_areas.append(area)
        kept_areas.sort(key=lambda a: -(a.area_m2 if a.area_m2 is not None else a.area_du2))
        block_list = sorted(blocks.values(), key=lambda b: (-b.count, b.block_name))
        content_words = " ".join(
            [r.layer for r in kept_runs[:6]] + [b.block_name for b in block_list[:6]]
        )
        label = (sheet_names or {}).get(sheet) or sheet.rsplit("/", 1)[-1]
        discipline = guess_discipline(label) or guess_discipline(content_words)
        # A free text tag seen once is a detail title; a bubble's attribute is
        # an element even when its type appears once on the sheet.
        tag_list = sorted(
            (t for t in tags.values() if t.count >= 2 or t.tag in attribute_tags),
            key=lambda t: (-t.count, t.tag),
        )
        entry = SheetInventory(
            sheet=sheet, label=label, discipline=discipline, blocks=block_list, runs=kept_runs,
            tags=tag_list, areas=kept_areas, specs=sorted(specs)[:40],
        )
        if to_m is None:
            entry.notes.append(
                "Unidad del dibujo desconocida: las longitudes se reportan en unidades de dibujo."
            )
        if not block_list and not kept_runs:
            entry.notes.append("La hoja no contiene símbolos ni trazos fuera de la anotación.")
        inventory.sheets.append(entry)
    inventory.sheets.sort(key=lambda s: s.sheet)
    total_blocks = sum(b.count for s in inventory.sheets for b in s.blocks)
    total_runs = sum(len(s.runs) for s in inventory.sheets)
    total_tags = sum(len(s.tags) for s in inventory.sheets)
    inventory.notes.append(
        f"{total_blocks} símbolos, {total_runs} capas con trazo y {total_tags} etiquetas "
        f"contados en {len(inventory.sheets)} hoja(s). Un conteo no es una cantidad hasta "
        "que se asigna a un concepto del catálogo."
    )
    return inventory
