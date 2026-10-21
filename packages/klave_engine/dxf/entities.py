"""Normalized entity schema: the common shape every DXF entity is mapped into."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from klave_engine.geometry.bbox import BBox, Point
from klave_engine.graph.evidence import EvidencePacket


class EntityType(StrEnum):
    line = "line"
    polyline = "polyline"
    arc = "arc"
    circle = "circle"
    hatch = "hatch"
    text = "text"
    mtext = "mtext"
    insert = "insert"
    dimension = "dimension"
    unknown = "unknown"


# What a leader draws (R133 brings them in): lines that point at things, never obra (R135).
ANNOTATION_SOURCES = frozenset({"LEADER", "MULTILEADER"})


class NormalizedEntity(BaseModel):
    entity_id: str
    entity_type: EntityType
    source_file: str
    layer: str
    bbox: BBox
    raw_handle: str
    properties: dict[str, Any] = Field(default_factory=dict)
    evidence: EvidencePacket

    text: str | None = None
    points: list[Point] | None = None
    block_name: str | None = None
    rotation: float | None = None
    color: int | None = None
    line_type: str | None = None
    confidence: float = 1.0

    @property
    def is_textual(self) -> bool:
        return self.entity_type in (EntityType.text, EntityType.mtext)

    @property
    def is_closed(self) -> bool:
        return bool(self.properties.get("closed", False))

    @property
    def is_annotation(self) -> bool:
        """The lines of a LEADER or a MULTILEADER: annotation, never a trabe, a wall, a slab edge
        or a marker (R135). A MULTILEADER's text is still a text."""
        return not self.is_textual and self.properties.get("derived_from") in ANNOTATION_SOURCES


class ParseWarning(BaseModel):
    warning_type: str
    message: str
    entity_type: str | None = None
    handle: str | None = None
    layer: str | None = None
    source_file: str | None = None
