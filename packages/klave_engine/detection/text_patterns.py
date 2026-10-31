"""Reusable, configurable regex patterns for drawing text classification."""

import re
from functools import lru_cache

from pydantic import BaseModel, Field

# The marks the foundation detectors place (R94): one source for the detectors, for
# the mark grammar (``estructura.marcas``), which reads every mark a detector can
# place, and for the family of a mark (``schedules.family_of_mark``, R95). Z-1,
# ZC-2, ZA-3, ZCM-100, Z-100A: zapatas; P-4: pilotes.
FOOTING_MARK_PREFIXES = ("ZCM", "ZC", "ZA", "Z")
PILE_MARK_PREFIXES = ("P",)
FOOTING_MARK_PATTERN = rf"^(?:{'|'.join(FOOTING_MARK_PREFIXES)})-?\d{{1,3}}[A-Z]?$"
PILE_MARK_PATTERN = rf"^(?:{'|'.join(PILE_MARK_PREFIXES)})-?\d{{1,2}}[A-Z]?$"
# R152: the type tags of a dala (Marina, on EST-CADENAS Y DALAS: «CI» cadena intermedia ×83,
# «DA-2» ×2, «DC» ×1): a placement of its type, defined by its type detail («CADENAS
# INTERMEDIAS», a «CI» per wall thickness) — never a grid label. Only on a cadenas/dalas layer
# is one a placement (``es_tipo_de_dala``); on a detail it is the type's title.
DALA_TYPE_TAG_PATTERN = r"^(?:CI|DC|DA-?\d{1,2}[A-Z]?)$"
DALA_LAYER_HINTS = ("CADENA", "DALA")
# Tarea 15b: the D-n tag of a dado (Marina, on EST-DADOS: D-1, D-4B, D-X). «D-» alone never says
# dado or dala (R159): only on a layer whose name says DADO is it the dado's placement tag.
DADO_MARK_PATTERN = r"^D-?(?:\d{1,2}[A-Z]?|[A-Z])$"
DADO_LAYER_HINTS = ("DADO",)


class TextPatternConfig(BaseModel):
    """Default patterns cover both English and Spanish (Mexican) conventions:
    C-1/COL-1 columns, K-5 castillos, B1/TB-1 beams, T-3/T2-7/TL-1 trabes,
    CTA-3 contratrabes, X'/Y' grid axes."""

    column_tag: list[str] = Field(
        default_factory=lambda: [
            r"^C-?\d{1,3}[A-Z]?$",
            r"^COL-?\d{1,3}$",
            r"^K-?\d{1,2}[A-Z]?$",
            r"^K-X$",
        ]
    )
    beam_tag: list[str] = Field(
        default_factory=lambda: [
            r"^B-?\d{1,3}$",
            r"^G-?\d{1,3}$",
            r"^TB-?\d{1,3}$",
            r"^T\d{1,2}-\d{1,2}[A-Z]?$",
            r"^CTA?-?\d{1,2}[A-Z]?$",
            r"^TE-[A-Z]$",
            r"^V-?\d{1,3}$",
            r"^T-?\d{1,3}[A-Z]?$",  # T-1 … T-11: the plain Mexican trabe mark
            r"^T[LRPS]-?\d{1,2}[A-Z]?$",  # TL-1 trabe de liga, TR/TP/TS variants
            r"^TRABE-?\d{1,2}$",
            r"^CE-?\d{1,2}[A-Z]?$",  # cadena de enrase / dala (Marina: CE-1 on EST-CADENAS Y DALAS)
            r"^CR-?\d{1,2}[A-Z]?$",  # cerramiento
            r"^(DL|DAL)-?\d{1,2}[A-Z]?$",  # dala DL-1 / DAL-1 (a bare D-4 is a dado)
            DALA_TYPE_TAG_PATTERN,  # R152: CI, DC, DA-2
        ]
    )
    detail_reference: list[str] = Field(
        default_factory=lambda: [
            r"^(?P<detail>\d{1,3}|[A-Z])\s*/\s*(?P<sheet>[A-Z]{1,2}-?\d{2,4})$"
        ]
    )
    grid_label: list[str] = Field(
        default_factory=lambda: [r"^[A-Z]{1,2}'?$", r"^\d{1,2}'?$"]
    )
    sheet_reference: list[str] = Field(default_factory=lambda: [r"^[A-Z]{1,2}-?\d{2,4}$"])
    section_marker: list[str] = Field(default_factory=lambda: [r"^[A-Z]-[A-Z]$"])


class TextMatch(BaseModel):
    category: str
    pattern: str
    text: str
    groups: dict[str, str] = Field(default_factory=dict)


@lru_cache(maxsize=512)
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


def classify_text(text: str, config: TextPatternConfig) -> list[TextMatch]:
    """All pattern categories the given text matches."""
    stripped = text.strip()
    matches: list[TextMatch] = []
    for category, patterns in config.model_dump().items():
        for pattern in patterns:
            match = _compiled(pattern).match(stripped)
            if match:
                matches.append(
                    TextMatch(
                        category=category,
                        pattern=pattern,
                        text=stripped,
                        groups={k: v for k, v in match.groupdict().items() if v is not None},
                    )
                )
                break  # first matching pattern per category is enough
    return matches


def match_category(text: str, config: TextPatternConfig, category: str) -> TextMatch | None:
    for match in classify_text(text, config):
        if match.category == category:
            return match
    return None


def es_tipo_de_dala(texto: str, capa: str) -> bool:
    """R152: whether a text is a dala's type tag (CI, DC, DA-2) on a cadenas/dalas layer: a
    placement of that type, never a grid label."""
    if _compiled(DALA_TYPE_TAG_PATTERN).match(texto.strip()) is None:
        return False
    capa = capa.upper()
    return any(pista in capa for pista in DALA_LAYER_HINTS)


def es_tipo_sin_capa(texto: str) -> bool:
    """R152: a dala type tag (CI, DC, DA-2) whatever its layer."""
    return _compiled(DALA_TYPE_TAG_PATTERN).match(texto.strip()) is not None
