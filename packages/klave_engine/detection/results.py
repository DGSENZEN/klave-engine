"""Detection result contracts shared by all detectors.

Detectors are the product's value path: they emit ``Detection`` records that
costing, takeoff and the UI consume. The drawing graph is derived from these
detections in one place (``graph.builder``), so detectors never build graph
nodes/edges themselves.
"""

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from klave_engine.geometry.bbox import BBox
from klave_engine.graph.evidence import EvidencePacket


class DetectionType(StrEnum):
    grid_line = "grid_line"
    grid_intersection = "grid_intersection"
    column_tag = "column_tag"
    beam_tag = "beam_tag"
    footing = "footing"
    slab_region = "slab_region"
    wall = "wall"
    detail_reference = "detail_reference"
    pile = "pile"  # pilote / pila: a mark with its circle in the cimentación
    room = "room"  # local: a bounded face of the architectural wall network
    terrain = "terrain"  # terreno natural: curvas y puntos de nivel of one file
    stair = "stair"  # escalera/rampa: the ESCALERA text on its tread pattern


class Detection(BaseModel):
    detection_id: str
    detection_type: DetectionType
    label: str
    bbox: BBox
    source_entities: list[str] = Field(default_factory=list)
    confidence: float
    evidence: EvidencePacket
    properties: dict[str, Any] = Field(default_factory=dict)
    # Taxonomy fields, filled by detection.taxonomy.enrich_detections after
    # the detectors run (defaults keep older artifacts readable).
    mark: str = ""
    family: str = ""
    family_label: str = ""
    display_label: str = ""
    description: str = ""


class DetectorOutput(BaseModel):
    detector_name: str
    detections: list[Detection] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def make_detection(
    detection_id: str,
    detection_type: DetectionType,
    label: str,
    bbox: BBox,
    confidence: float,
    source_entities: list[str],
    method: str,
    notes: list[str],
    properties: dict[str, Any] | None = None,
    source_file: str = "",
) -> Detection:
    """Build a Detection with its evidence packet in one call."""
    evidence = EvidencePacket(
        source=source_file,
        method=method,
        entity_ids=source_entities,
        bbox=bbox,
        confidence=confidence,
        notes=notes,
    )
    return Detection(
        detection_id=detection_id,
        detection_type=detection_type,
        label=label,
        bbox=bbox,
        source_entities=source_entities,
        confidence=confidence,
        evidence=evidence,
        properties=properties or {},
    )


_TOKEN_SPLIT = re.compile(r"[^A-Z0-9]+")


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_SPLIT.split(text.upper()) if t]


def layer_matches(layer: str, hints: list[str]) -> bool:
    """Whether a layer name carries one of the hints, by tokens, never by
    raw substring: ``MC`` is the token ``MC`` (``E-MC-01``), not the start of
    ``MCOBILIARIO``. A hint of four letters or more may be the beginning of
    a token (``MURO`` → ``MUROS``); a shorter one must be the whole token.
    Multi-word hints (``MURO CONC``) match consecutive tokens."""
    layer_tokens = _tokens(layer)
    if not layer_tokens:
        return False
    for hint in hints:
        parts = _tokens(hint)
        if not parts or len(parts) > len(layer_tokens):
            continue
        for start in range(len(layer_tokens) - len(parts) + 1):
            if all(
                layer_tokens[start + i] == part
                or (len(part) >= 4 and layer_tokens[start + i].startswith(part))
                for i, part in enumerate(parts)
            ):
                return True
    return False
