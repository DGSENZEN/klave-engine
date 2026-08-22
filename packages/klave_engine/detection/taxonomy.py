"""Detection taxonomy: element families, stable display labels, Spanish descriptions.

Raw detections carry whatever the sheet says ("K-5", "CTA-3") or a bare
counter ("W447"). After the detectors run, this module normalizes each
detection:

- ``mark``: the tag read from the plano, preserved verbatim (empty when the
  element has no text tag). Source-of-truth fidelity: never rewritten.
- ``family``: canonical element family in Mexican structural convention
  (K → castillo, C/COL → columna, T/TB/B/G/V → trabe, CTA/CT → contratrabe…).
- ``display_label``: stable system identifier ("CAS-05"). Assigned by sorting
  each family by (mark, geometry), so the same element keeps the same name
  across re-runs — budgets, tooltips and collaboration can all cite it.
- ``description``: one Spanish sentence explaining what was detected, from
  which evidence, with measured dimensions when available.
"""

import math
import re
from enum import StrEnum
from typing import NamedTuple

from klave_engine.detection.results import Detection, DetectionType


class Family(StrEnum):
    castillo = "castillo"
    columna = "columna"
    trabe = "trabe"
    contratrabe = "contratrabe"
    zapata = "zapata"
    losa = "losa"
    muro = "muro"
    eje = "eje"
    interseccion_ejes = "interseccion_ejes"
    referencia_detalle = "referencia_detalle"


class FamilyInfo(NamedTuple):
    code: str
    label: str  # singular, for one detection
    label_plural: str  # for legend/grouping


FAMILY_INFO: dict[Family, FamilyInfo] = {
    Family.castillo: FamilyInfo("CAS", "Castillo", "Castillos"),
    Family.columna: FamilyInfo("COL", "Columna", "Columnas"),
    Family.trabe: FamilyInfo("TRB", "Trabe", "Trabes"),
    Family.contratrabe: FamilyInfo("CTR", "Contratrabe", "Contratrabes"),
    Family.zapata: FamilyInfo("ZAP", "Zapata", "Zapatas"),
    Family.losa: FamilyInfo("LOS", "Losa", "Losas"),
    Family.muro: FamilyInfo("MUR", "Muro", "Muros"),
    Family.eje: FamilyInfo("EJE", "Eje", "Ejes"),
    Family.interseccion_ejes: FamilyInfo("INT", "Intersección de ejes", "Intersecciones"),
    Family.referencia_detalle: FamilyInfo("REF", "Referencia a detalle", "Referencias"),
}

# Human phrasing of each detector method, for descriptions.
_METHOD_PHRASES: dict[str, str] = {
    "column_tag_regex_near_grid": "etiqueta de texto validada contra la retícula de ejes",
    "beam_tag_regex_near_linework": "etiqueta de texto sobre línea de trabe",
    "footing_closed_rectangular_polyline": "polilínea rectangular cerrada con proporción de zapata",
    "wall_paired_parallel_lines": "par de líneas paralelas con separación de muro",
    "slab_region_from_hatch": "achurado de losa sobre región cerrada",
    "slab_region_from_large_closed_polyline": "polilínea cerrada con área de losa",
    "grid_line_axis_aligned_long_line": "línea larga alineada a la retícula",
    "grid_intersection_of_grid_lines": "cruce de ejes de trazo",
    "detail_reference_regex_manifest_lookup": "referencia de detalle ligada a hoja del proyecto",
}

# Detection types whose label is text read from the plano (a real mark).
_TEXT_MARK_TYPES = frozenset(
    {DetectionType.column_tag, DetectionType.beam_tag, DetectionType.detail_reference}
)

_AXIS_ES = {"horizontal": "horizontal", "vertical": "vertical"}


def classify_family(detection: Detection) -> Family:
    """Canonical family from detection type + mark prefix (Mexican convention)."""
    mark = detection.label.strip().upper()
    dtype = detection.detection_type
    if dtype == DetectionType.column_tag:
        return Family.castillo if mark.startswith("K") else Family.columna
    if dtype == DetectionType.beam_tag:
        return Family.contratrabe if re.match(r"^CTA?-?\d", mark) else Family.trabe
    if dtype == DetectionType.footing:
        return Family.zapata
    if dtype == DetectionType.slab_region:
        return Family.losa
    if dtype == DetectionType.wall:
        return Family.muro
    if dtype == DetectionType.grid_line:
        return Family.eje
    if dtype == DetectionType.grid_intersection:
        return Family.interseccion_ejes
    return Family.referencia_detalle


def _extract_mark(detection: Detection) -> str:
    """The tag as drawn on the sheet; empty for synthetic/auto labels."""
    if detection.detection_type in _TEXT_MARK_TYPES:
        return detection.label.strip()
    if detection.detection_type == DetectionType.grid_line:
        # Unlabeled axes get auto names (H1/V2); the detector notes it.
        auto = any(
            note.startswith("No grid label found") for note in detection.evidence.notes
        )
        return "" if auto else detection.label.strip()
    if detection.detection_type == DetectionType.grid_intersection:
        # Derived location like "B/3"; keep it when both axes had real labels.
        return "" if re.search(r"[HV]\d|\?", detection.label) else detection.label.strip()
    return ""


def _fmt_len(value_du: float, unit_to_m: float | None) -> str:
    if unit_to_m is None:
        return f"{value_du:g} u. dib."
    meters = value_du * unit_to_m
    if meters < 1.0:
        return f"{meters * 100:.0f} cm"
    return f"{meters:.1f} m"


def _fmt_area(value_du2: float, unit_to_m: float | None) -> str:
    if unit_to_m is None:
        return f"{value_du2:g} u. dib.²"
    return f"{value_du2 * unit_to_m * unit_to_m:.1f} m²"


def _measurement_parts(detection: Detection, unit_to_m: float | None) -> list[str]:
    props = detection.properties
    parts: list[str] = []
    section = props.get("section_area_du2")
    if isinstance(section, (int, float)) and section > 0 and unit_to_m is not None:
        side_cm = math.sqrt(section) * unit_to_m * 100
        source_key = str(props.get("section_source") or "")
        source = {
            "cuadro": "según cuadro/detalle del plano",
            "cota": "acotada en el plano",
        }.get(source_key, "medida del marcador" if source_key else "medida")
        declared = props.get("section_cm")
        if isinstance(declared, str) and "x" in declared:
            parts.append(f"sección {declared.replace('x', '×')} cm ({source})")
        else:
            parts.append(f"sección ≈ {side_cm:.0f}×{side_cm:.0f} cm ({source})")
    length = props.get("estimated_length")
    if isinstance(length, (int, float)) and length > 0:
        parts.append(f"longitud ≈ {_fmt_len(length, unit_to_m)}")
    thickness = props.get("estimated_thickness")
    if isinstance(thickness, (int, float)) and thickness > 0:
        acotado = " (acotado)" if props.get("thickness_source") == "cota" else ""
        parts.append(f"espesor ≈ {_fmt_len(thickness, unit_to_m)}{acotado}")
    area = props.get("estimated_area")
    if isinstance(area, (int, float)) and area > 0:
        if props.get("area_source") == "cota":
            parts.append(f"área {_fmt_area(area, unit_to_m)} (acotada en el plano)")
        else:
            parts.append(f"área ≈ {_fmt_area(area, unit_to_m)}")
    axis = props.get("axis")
    if isinstance(axis, str) and axis in _AXIS_ES:
        grid_length = props.get("length")
        suffix = (
            f", longitud {_fmt_len(grid_length, unit_to_m)}"
            if isinstance(grid_length, (int, float)) and grid_length > 0
            else ""
        )
        parts.append(f"eje {_AXIS_ES[axis]}{suffix}")
    target_sheet = props.get("target_sheet")
    if isinstance(target_sheet, str) and target_sheet:
        parts.append(f"hoja destino {target_sheet}")
    return parts


def _location_part(detection: Detection) -> str | None:
    nearest = detection.properties.get("nearest_grid")
    if isinstance(nearest, str) and nearest and "?" not in nearest:
        return f"cerca del eje {nearest}"
    nearby_column = detection.properties.get("nearby_column_tag")
    if isinstance(nearby_column, str) and nearby_column:
        return f"junto a {nearby_column}"
    return None


def describe(detection: Detection, unit_to_m: float | None = None) -> str:
    """One Spanish sentence: what it is, the evidence, dimensions, confidence."""
    info = FAMILY_INFO[classify_family(detection)]
    mark = _extract_mark(detection)
    name = f"{info.label} {mark}" if mark else info.label
    parts = [name]
    if mark:
        parts.append(f"etiqueta «{mark}» leída del plano")
    method_phrase = _METHOD_PHRASES.get(detection.evidence.method)
    if method_phrase:
        parts.append(method_phrase)
    location = _location_part(detection)
    if location:
        parts.append(location)
    parts.extend(_measurement_parts(detection, unit_to_m))
    parts.append(f"confianza {detection.confidence * 100:.0f}%")
    return " · ".join(parts)


def _label_key(mark: str) -> str:
    """A mark as it appears in a key: uppercase, no spaces, '/' kept for B/3."""
    return re.sub(r"[^A-Z0-9/'\-\.]", "", mark.strip().upper().replace(" ", ""))


def enrich_detections(
    detections: list[Detection], unit_to_m: float | None = None
) -> None:
    """Assign mark/family/display_label/description to every detection, in place.

    Display labels are deterministic: within a family, detections are ordered
    by (mark, bbox), so a re-run over the same sheet names the same elements
    the same way.
    """
    by_family: dict[Family, list[Detection]] = {}
    for detection in detections:
        family = classify_family(detection)
        detection.family = family.value
        detection.mark = _extract_mark(detection)
        detection.description = describe(detection, unit_to_m)
        by_family.setdefault(family, []).append(detection)

    for family, members in by_family.items():
        info = FAMILY_INFO[family]
        members.sort(key=lambda d: (d.mark, tuple(d.bbox)))
        # Keys are built from the mark the sheet uses, so a review on
        # "EJE-B" or "CAS-K-1-07" survives a reprocess that adds or drops
        # unrelated elements; only unmarked elements are numbered globally.
        groups: dict[str, list[Detection]] = {}
        for detection in members:
            groups.setdefault(_label_key(detection.mark), []).append(detection)
        unmarked = groups.get("", [])
        unmarked_width = max(2, len(str(len(unmarked))))
        for key, group in groups.items():
            width = max(2, len(str(len(group))))
            for ordinal, detection in enumerate(group, start=1):
                detection.family_label = info.label
                if not key:
                    detection.display_label = f"{info.code}-{ordinal:0{unmarked_width}d}"
                elif len(group) == 1:
                    detection.display_label = f"{info.code}-{key}"
                else:
                    detection.display_label = f"{info.code}-{key}-{ordinal:0{width}d}"
