"""Reusable, configurable regex patterns for drawing text classification."""

import re
from functools import lru_cache

from pydantic import BaseModel, Field


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
