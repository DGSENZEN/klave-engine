"""Dimension-text parsing: extract the drawing's own dimensions and specs.

Structural sheets state real dimensions in text — element sections (``15x30``),
masonry blocks (``15x20x40``), wall thickness (``MURO DE CARGA 15 CM``), slab
peralte (``H=20``), vigueta systems (``12-5``) and reinforcement (``E#3@20``).
On many sheets these live in schedules/details rather than next to each element,
so this module builds a sheet-level inventory of what dimensions appear and
derives typical values that calibrate the cost assumptions, with provenance.
"""

import re
from collections import Counter
from enum import StrEnum

from pydantic import BaseModel, Field

from klave_engine.dxf.entities import NormalizedEntity

# Section "NxM" in centimetres, e.g. 15x30, 30 X 40 (excludes the 3-number
# block specs, which are matched separately first).
_SECTION_RE = re.compile(r"(?<![\dxX×])(\d{1,3})\s*[xX×]\s*(\d{1,3})(?![\dxX×])")
_BLOCK_RE = re.compile(r"(\d{1,3})\s*[xX×]\s*(\d{1,3})\s*[xX×]\s*(\d{1,3})")
_WALL_CM_RE = re.compile(
    r"(?:MURO|MURETE|ESPESOR|CARGA|BLOCK|BLOQUE)\D{0,24}?(\d{1,2})\s*(?:CM|CMS)\b", re.I
)
_PERALTE_RE = re.compile(r"\bH\s*=\s*(\d{1,3})\b", re.I)
_VIGUETA_RE = re.compile(r"\b(1\d\s*-\s*\d)\b")
_REBAR_RE = re.compile(r"(?:E\s*)?#\s*(\d)\s*(?:@\s*(\d{1,3}))?")

# Block-name semantics (Revit/AutoCAD family names encode type + dimension).
_BLOCK_CM_RE = re.compile(r"-\s*(\d{1,3})\s*cm\b", re.I)
_BLOCK_CLASS_KEYWORDS: list[tuple[str, str]] = [
    ("muro", r"\bMURO\b"),
    ("columna", r"\bCOLUMNA|CASTILLO\b"),
    ("trabe", r"\bTRABE|VIGA\b"),
    ("zapata", r"\bZAPATA|DADO|CIMENTACI"),
    ("losa", r"\bLOSA\b"),
    ("montante", r"\bMONTANTE\b"),
    ("nivel", r"\bNIVEL\b"),
    ("alzado", r"\bALZADO|FLECHA\b"),
    ("rejilla", r"\bREJILLA\b"),
]

# Plausible structural element section bounds in cm (per side).
_MIN_SIDE_CM = 8
_MAX_SIDE_CM = 120


class DimensionSource(StrEnum):
    measured_dimension = "medido (acotación)"
    block_name = "nombre de bloque"
    text = "texto del plano"
    assumed = "supuesto"


class BlockSemantics(BaseModel):
    element_class: str | None = None
    thickness_cm: int | None = None
    section_cm: tuple[int, int] | None = None
    is_level_marker: bool = False


def parse_block_name(name: str) -> BlockSemantics:
    """Parse an INSERT block name into element class + dimensions.

    Revit exports name families descriptively, e.g.
    ``Muro básico _ Hormigón con cimentación - 30 cm`` → wall, 30 cm.
    """
    spec = BlockSemantics()
    for element_class, pattern in _BLOCK_CLASS_KEYWORDS:
        if re.search(pattern, name, re.I):
            spec.element_class = element_class
            spec.is_level_marker = element_class == "nivel"
            break
    block_match = _BLOCK_RE.search(name)
    section_match = _SECTION_RE.search(name)
    if section_match:
        # Block names are authoritative, so accept a looser size range than the
        # noisy free-text path (this keeps small members like 5x10 mullions).
        a, b = int(section_match.group(1)), int(section_match.group(2))
        if 2 <= a <= 300 and 2 <= b <= 300:
            spec.section_cm = (min(a, b), max(a, b))
    cm = _BLOCK_CM_RE.search(name)
    if cm and not block_match:
        spec.thickness_cm = int(cm.group(1))
    return spec


class DimensionInventory(BaseModel):
    """What the drawing states about dimensions, plus derived typical values."""

    sections_cm: dict[str, int] = Field(default_factory=dict)  # "15x30" -> count
    block_specs: dict[str, int] = Field(default_factory=dict)  # "15x20x40" -> count
    wall_thickness_cm: dict[int, int] = Field(default_factory=dict)  # 15 -> count
    peralte_cm: dict[int, int] = Field(default_factory=dict)
    vigueta_systems: dict[str, int] = Field(default_factory=dict)
    rebar_calls: dict[str, int] = Field(default_factory=dict)
    # Higher-authority sources read from the file itself:
    measured_dimensions_cm: dict[int, int] = Field(default_factory=dict)  # DIMENSION values
    block_classes: dict[str, int] = Field(default_factory=dict)  # parsed block element classes
    block_thickness_cm: dict[int, int] = Field(default_factory=dict)  # from block names
    level_marker_count: int = 0

    typical_section_cm: tuple[int, int] | None = None
    typical_wall_thickness_cm: int | None = None
    typical_wall_thickness_source: str | None = None
    typical_peralte_cm: int | None = None
    vigueta_system: str | None = None
    dimension_count: int = 0
    notes: list[str] = Field(default_factory=list)

    @property
    def typical_section_m2(self) -> float | None:
        if self.typical_section_cm is None:
            return None
        a, b = self.typical_section_cm
        return round(a * b / 10000.0, 4)


def _plausible_section(a: int, b: int) -> bool:
    return _MIN_SIDE_CM <= a <= _MAX_SIDE_CM and _MIN_SIDE_CM <= b <= _MAX_SIDE_CM


def build_dimension_inventory(
    entities: list[NormalizedEntity], meters_factor: float = 1.0
) -> DimensionInventory:
    inv = DimensionInventory()
    sections: Counter[str] = Counter()
    blocks: Counter[str] = Counter()
    walls: Counter[int] = Counter()
    peraltes: Counter[int] = Counter()
    viguetas: Counter[str] = Counter()
    rebars: Counter[str] = Counter()
    measured: Counter[int] = Counter()
    block_classes: Counter[str] = Counter()
    block_thickness: Counter[int] = Counter()
    level_markers = 0

    for entity in entities:
        # DIMENSION entities: the engineer's explicit measured values (highest
        # authority). Keep only member-scale spans (8–120 cm).
        if entity.entity_type.value == "dimension":
            inv.dimension_count += 1
            value = entity.properties.get("measurement")
            if value is not None:
                cm = round(float(value) * meters_factor * 100.0)
                if _MIN_SIDE_CM <= cm <= _MAX_SIDE_CM:
                    measured[cm] += 1
            continue
        # INSERT block names carry element class + dimensions (Revit families).
        if entity.entity_type.value == "insert" and entity.block_name:
            spec = parse_block_name(entity.block_name)
            if spec.element_class:
                block_classes[spec.element_class] += 1
            if spec.is_level_marker:
                level_markers += 1
            if spec.thickness_cm and spec.element_class == "muro":
                block_thickness[spec.thickness_cm] += 1
            continue
        if not entity.is_textual or not entity.text:
            continue
        text = entity.text.strip()

        consumed_spans: list[tuple[int, int]] = []
        for m in _BLOCK_RE.finditer(text):
            blocks[f"{m.group(1)}x{m.group(2)}x{m.group(3)}"] += 1
            consumed_spans.append(m.span())
        for m in _SECTION_RE.finditer(text):
            # Skip the "a x b" that is part of an already-matched "a x b x c".
            if any(s <= m.start() < e for s, e in consumed_spans):
                continue
            a, b = int(m.group(1)), int(m.group(2))
            if _plausible_section(a, b):
                lo, hi = sorted((a, b))
                sections[f"{lo}x{hi}"] += 1
        for m in _WALL_CM_RE.finditer(text):
            walls[int(m.group(1))] += 1
        for m in _PERALTE_RE.finditer(text):
            peraltes[int(m.group(1))] += 1
        for m in _VIGUETA_RE.finditer(text):
            viguetas[m.group(1).replace(" ", "")] += 1
        for m in _REBAR_RE.finditer(text):
            sep = f"#{m.group(1)}" + (f"@{m.group(2)}" if m.group(2) else "")
            rebars[sep] += 1

    inv.sections_cm = dict(sections.most_common())
    inv.block_specs = dict(blocks.most_common())
    inv.wall_thickness_cm = dict(walls.most_common())
    inv.peralte_cm = dict(peraltes.most_common())
    inv.vigueta_systems = dict(viguetas.most_common())
    inv.rebar_calls = dict(rebars.most_common(20))
    inv.measured_dimensions_cm = dict(measured.most_common())
    inv.block_classes = dict(block_classes.most_common())
    inv.block_thickness_cm = dict(block_thickness.most_common())
    inv.level_marker_count = level_markers

    # Typical section: the most frequent plausible NxM (e.g. castillo/dala).
    if sections:
        top = sections.most_common(1)[0][0]
        a, b = (int(x) for x in top.split("x"))
        inv.typical_section_cm = (a, b)
        inv.notes.append(f"Sección típica del plano: {top} cm (la más frecuente)")

    # Typical wall thickness by authority: explicit text 'N CM' > block name >
    # block 3D width.
    if walls:
        inv.typical_wall_thickness_cm = walls.most_common(1)[0][0]
        inv.typical_wall_thickness_source = DimensionSource.text.value
    elif block_thickness:
        inv.typical_wall_thickness_cm = block_thickness.most_common(1)[0][0]
        inv.typical_wall_thickness_source = DimensionSource.block_name.value
    elif blocks:
        inv.typical_wall_thickness_cm = int(blocks.most_common(1)[0][0].split("x")[0])
        inv.typical_wall_thickness_source = DimensionSource.text.value
    if inv.typical_wall_thickness_cm is not None:
        inv.notes.append(
            f"Espesor de muro típico: {inv.typical_wall_thickness_cm} cm "
            f"({inv.typical_wall_thickness_source})"
        )
    if inv.dimension_count:
        inv.notes.append(
            f"{inv.dimension_count} cotas (DIMENSION) leídas del plano; "
            f"{sum(measured.values())} a escala de elemento (8–120 cm)."
        )
    if level_markers:
        inv.notes.append(f"{level_markers} marcadores de nivel (bloques) detectados.")

    if peraltes:
        inv.typical_peralte_cm = peraltes.most_common(1)[0][0]
        inv.notes.append(f"Peralte de losa típico: {inv.typical_peralte_cm} cm (H=)")
    if viguetas:
        inv.vigueta_system = viguetas.most_common(1)[0][0]
        inv.notes.append(f"Sistema de losa: vigueta y bovedilla {inv.vigueta_system}")

    if not inv.notes:
        inv.notes.append("No se encontraron dimensiones explícitas en el texto del plano.")
    return inv
