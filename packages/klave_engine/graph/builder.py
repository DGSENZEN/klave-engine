"""DrawingGraph container and builder.

The builder creates sheet, layer, and entity nodes with containment edges,
plus NEAR edges from text entities to nearby geometry. Detectors later add
semantic nodes (grid lines, column tags, ...) through ``merge_detector_output``.
"""

from collections import Counter

from klave_engine.common.errors import GraphBuildError
from klave_engine.common.ids import IdGenerator, slugify
from klave_engine.common.logging import get_logger, log_stage
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.dxf.parser import ParsedDrawing
from klave_engine.geometry.spatial_index import SpatialIndex
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

    def neighbors(self, node_id: str) -> list[GraphNode]:
        ids = set()
        for edge in self.edges.values():
            if edge.source_node_id == node_id:
                ids.add(edge.target_node_id)
            elif edge.target_node_id == node_id:
                ids.add(edge.source_node_id)
        return [self.nodes[i] for i in sorted(ids)]

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


class DrawingGraphBuilder:
    def __init__(self, project_id: str, near_radius: float = 25.0) -> None:
        self.project_id = project_id
        self.near_radius = near_radius
        self._edge_ids = IdGenerator("edge")

    def _structural_evidence(self, method: str, entity: NormalizedEntity | None = None
                             ) -> EvidencePacket:
        return EvidencePacket(
            source=entity.source_file if entity else self.project_id,
            method=method,
            entity_ids=[entity.entity_id] if entity else [],
            bbox=entity.bbox if entity else None,
        )

    def build(
        self,
        drawings: list[ParsedDrawing],
        index: SpatialIndex | None = None,
    ) -> DrawingGraph:
        graph = DrawingGraph()

        for drawing in drawings:
            sheet_node_id = f"sheet_{slugify(drawing.source_file)}"
            graph.add_node(
                GraphNode(
                    node_id=sheet_node_id,
                    node_type=NodeType.sheet,
                    label=drawing.source_file,
                    evidence=EvidencePacket(
                        source=drawing.source_file, method="manifest_sheet_node"
                    ),
                )
            )

            layer_node_ids: dict[str, str] = {}
            for entity in drawing.entities:
                if entity.layer not in layer_node_ids:
                    layer_node_id = f"layer_{slugify(drawing.source_file)}_{slugify(entity.layer)}"
                    layer_node_ids[entity.layer] = layer_node_id
                    graph.add_node(
                        GraphNode(
                            node_id=layer_node_id,
                            node_type=NodeType.layer,
                            label=entity.layer,
                            properties={"source_file": drawing.source_file},
                            evidence=EvidencePacket(
                                source=drawing.source_file, method="dxf_layer_node"
                            ),
                        )
                    )
                    graph.add_edge(
                        GraphEdge(
                            edge_id=self._edge_ids.next(),
                            edge_type=EdgeType.contains,
                            source_node_id=sheet_node_id,
                            target_node_id=layer_node_id,
                            evidence=EvidencePacket(
                                source=drawing.source_file, method="sheet_contains_layer"
                            ),
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
                        evidence=self._structural_evidence("entity_node", entity),
                    )
                )
                graph.add_edge(
                    GraphEdge(
                        edge_id=self._edge_ids.next(),
                        edge_type=EdgeType.contains,
                        source_node_id=layer_node_ids[entity.layer],
                        target_node_id=entity.entity_id,
                        evidence=self._structural_evidence("layer_contains_entity", entity),
                    )
                )

        if index is not None:
            self._add_near_edges(graph, index)

        log_stage(
            logger,
            "graph_build_completed",
            project_id=self.project_id,
            node_count=len(graph.nodes),
            edge_count=len(graph.edges),
        )
        return graph

    def _add_near_edges(self, graph: DrawingGraph, index: SpatialIndex) -> None:
        """NEAR edges from each text entity to nearby non-text geometry (max 5)."""
        for node in graph.nodes_by_type(NodeType.text):
            hits = index.entities_near_entity(node.node_id, self.near_radius)
            count = 0
            for hit in hits:
                other = index.get(hit.entity_id)
                if other.is_textual or hit.entity_id not in graph.nodes:
                    continue
                graph.add_edge(
                    GraphEdge(
                        edge_id=self._edge_ids.next(),
                        edge_type=EdgeType.near,
                        source_node_id=node.node_id,
                        target_node_id=hit.entity_id,
                        properties={"distance": round(hit.distance, 3)},
                        evidence=EvidencePacket(
                            source=other.source_file,
                            method="spatial_index_near_query",
                            entity_ids=[node.node_id, hit.entity_id],
                            notes=[f"distance={hit.distance:.3f}"],
                        ),
                    )
                )
                count += 1
                if count >= 5:
                    break

    def merge_detector_output(
        self,
        graph: DrawingGraph,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
    ) -> list[str]:
        """Add detector-created nodes/edges; returns warnings for dangling edges."""
        warnings: list[str] = []
        for node in nodes:
            graph.add_node(node)
        for edge in edges:
            if edge.source_node_id not in graph.nodes or edge.target_node_id not in graph.nodes:
                warnings.append(
                    f"Skipped edge {edge.edge_id} ({edge.edge_type.value}): "
                    "endpoint node not in graph"
                )
                continue
            graph.add_edge(edge)
        return warnings
