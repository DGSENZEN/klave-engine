"""Detection result contracts shared by all detectors.

Detectors are the product's value path: they emit ``Detection`` records that
costing, takeoff and the UI consume. The drawing graph is derived from these
detections in one place (``graph.builder``), so detectors never build graph
nodes/edges themselves.
"""

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


def layer_matches(layer: str, hints: list[str]) -> bool:
    upper = layer.upper()
    return any(hint.upper() in upper for hint in hints)
