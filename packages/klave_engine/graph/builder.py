"""DrawingGraph container and a single derive step.

The graph is an inspection artifact (the `/graph` endpoint and evals), not part
of the costing value path. It is derived in one place from the parsed entities
(sheet/layer/entity nodes with containment edges) plus the detections (semantic
nodes) — detectors do not build graph objects themselves.
"""

from collections import Counter

from klave_engine.common.errors import GraphBuildError
from klave_engine.common.ids import IdGenerator, slugify
from klave_engine.common.logging import get_logger, log_stage
from klave_engine.detection.results import Detection
from klave_engine.dxf.entities import EntityType
from klave_engine.dxf.parser import ParsedDrawing
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.graph.schema import (
    DrawingGraphExport,
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
)

logger = get_logger(__name__)

ENTITY_NODE_TYPES: dict[EntityType, NodeType] = {
    EntityType.line: NodeType.line,
    EntityType.polyline: NodeType.polyline,
    EntityType.arc: NodeType.arc,
    EntityType.circle: NodeType.circle,
    EntityType.hatch: NodeType.hatch,
    EntityType.text: NodeType.text,
    EntityType.mtext: NodeType.text,
    EntityType.insert: NodeType.block,
}


class DrawingGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.source_node_id not in self.nodes:
            raise GraphBuildError(f"Edge source node missing: {edge.source_node_id}")
        if edge.target_node_id not in self.nodes:
            raise GraphBuildError(f"Edge target node missing: {edge.target_node_id}")
        self.edges[edge.edge_id] = edge

    def nodes_by_type(self, node_type: NodeType) -> list[GraphNode]:
        return [n for n in self.nodes.values() if n.node_type == node_type]

    def edges_by_type(self, edge_type: EdgeType) -> list[GraphEdge]:
        return [e for e in self.edges.values() if e.edge_type == edge_type]

    def to_export(self, project_id: str) -> DrawingGraphExport:
        node_counts = Counter(n.node_type.value for n in self.nodes.values())
        edge_counts = Counter(e.edge_type.value for e in self.edges.values())
        return DrawingGraphExport(
            project_id=project_id,
            nodes=sorted(self.nodes.values(), key=lambda n: n.node_id),
            edges=sorted(self.edges.values(), key=lambda e: e.edge_id),
            node_count_by_type=dict(sorted(node_counts.items())),
            edge_count_by_type=dict(sorted(edge_counts.items())),
        )


def build_drawing_graph(
    project_id: str,
    drawings: list[ParsedDrawing],
    detections: list[Detection],
) -> DrawingGraph:
    """Derive the graph from parsed entities + detections in one pass."""
    graph = DrawingGraph()
    edge_ids = IdGenerator("edge")

    for drawing in drawings:
        sheet_id = f"sheet_{slugify(drawing.source_file)}"
        graph.add_node(
            GraphNode(
                node_id=sheet_id,
                node_type=NodeType.sheet,
                label=drawing.source_file,
                evidence=EvidencePacket(source=drawing.source_file, method="sheet_node"),
            )
        )
        layer_ids: dict[str, str] = {}
        for entity in drawing.entities:
            if entity.layer not in layer_ids:
                layer_id = f"layer_{slugify(drawing.source_file)}_{slugify(entity.layer)}"
                layer_ids[entity.layer] = layer_id
                graph.add_node(
                    GraphNode(
                        node_id=layer_id,
                        node_type=NodeType.layer,
                        label=entity.layer,
                        properties={"source_file": drawing.source_file},
                        evidence=EvidencePacket(source=drawing.source_file, method="layer_node"),
                    )
                )
                graph.add_edge(
                    GraphEdge(
                        edge_id=edge_ids.next(),
                        edge_type=EdgeType.contains,
                        source_node_id=sheet_id,
                        target_node_id=layer_id,
                        evidence=EvidencePacket(source=drawing.source_file, method="contains"),
                    )
                )
            node_type = ENTITY_NODE_TYPES.get(entity.entity_type)
            if node_type is None:
                continue
            graph.add_node(
                GraphNode(
                    node_id=entity.entity_id,
                    node_type=node_type,
                    label=entity.text or entity.block_name or entity.entity_type.value,
                    bbox=entity.bbox,
                    source_entities=[entity.entity_id],
                    properties={"layer": entity.layer},
                    evidence=EvidencePacket(
                        source=entity.source_file, method="entity_node",
                        entity_ids=[entity.entity_id], bbox=entity.bbox,
                    ),
                )
            )
            graph.add_edge(
                GraphEdge(
                    edge_id=edge_ids.next(),
                    edge_type=EdgeType.contains,
                    source_node_id=layer_ids[entity.layer],
                    target_node_id=entity.entity_id,
                    evidence=EvidencePacket(source=entity.source_file, method="contains"),
                )
            )

    # Semantic nodes derived directly from detections.
    for detection in detections:
        try:
            node_type = NodeType(detection.detection_type.value)
        except ValueError:
            continue
        graph.add_node(
            GraphNode(
                node_id=detection.detection_id,
                node_type=node_type,
                label=detection.label,
                bbox=detection.bbox,
                source_entities=detection.source_entities,
                properties=detection.properties,
                confidence=detection.confidence,
                evidence=detection.evidence,
            )
        )

    log_stage(
        logger,
        "graph_built",
        project_id=project_id,
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
    )
    return graph
