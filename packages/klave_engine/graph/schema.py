"""Typed drawing graph schema: nodes, edges, and the export contract."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from klave_engine.geometry.bbox import BBox
from klave_engine.graph.evidence import EvidencePacket


class NodeType(StrEnum):
    sheet = "sheet"
    layer = "layer"
    block = "block"
    line = "line"
    polyline = "polyline"
    arc = "arc"
    circle = "circle"
    hatch = "hatch"
    text = "text"
    grid_line = "grid_line"
    grid_intersection = "grid_intersection"
    column_tag = "column_tag"
    beam_tag = "beam_tag"
    footing = "footing"
    slab_region = "slab_region"
    wall = "wall"
    detail_reference = "detail_reference"


class EdgeType(StrEnum):
    contains = "CONTAINS"
    near = "NEAR"
    intersects = "INTERSECTS"
    aligned_with = "ALIGNED_WITH"
    labels = "LABELS"
    references = "REFERENCES"
    belongs_to_grid = "BELONGS_TO_GRID"
    possible_structural_element = "POSSIBLE_STRUCTURAL_ELEMENT"
    conflicts_with = "CONFLICTS_WITH"


class GraphNode(BaseModel):
    node_id: str
    node_type: NodeType
    label: str
    bbox: BBox | None = None
    source_entities: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    evidence: EvidencePacket


class GraphEdge(BaseModel):
    edge_id: str
    edge_type: EdgeType
    source_node_id: str
    target_node_id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    evidence: EvidencePacket


class DrawingGraphExport(BaseModel):
    project_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    node_count_by_type: dict[str, int]
    edge_count_by_type: dict[str, int]
