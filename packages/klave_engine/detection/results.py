"""Detection result contracts shared by all detectors."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from klave_engine.geometry.bbox import BBox
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.graph.schema import GraphEdge, GraphNode


class DetectionType(StrEnum):
    grid_line = "grid_line"
    grid_intersection = "grid_intersection"
    column_tag = "column_tag"
    beam_tag = "beam_tag"
    footing = "footing"
    slab_region = "slab_region"
    wall = "wall"
    detail_reference = "detail_reference"


class Detection(BaseModel):
    detection_id: str
    detection_type: DetectionType
    label: str
    bbox: BBox
    source_entities: list[str] = Field(default_factory=list)
    graph_nodes: list[str] = Field(default_factory=list)
    confidence: float
    evidence: EvidencePacket
    properties: dict[str, Any] = Field(default_factory=dict)


class DetectorOutput(BaseModel):
    detector_name: str
    detections: list[Detection] = Field(default_factory=list)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def layer_matches(layer: str, hints: list[str]) -> bool:
    upper = layer.upper()
    return any(hint.upper() in upper for hint in hints)
