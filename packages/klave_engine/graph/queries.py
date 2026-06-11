"""Practical query helpers over a DrawingGraph. No query language, just functions."""

from klave_engine.geometry.bbox import BBox, bbox_distance
from klave_engine.graph.builder import DrawingGraph
from klave_engine.graph.schema import EdgeType, GraphEdge, GraphNode, NodeType


def find_nodes_by_type(graph: DrawingGraph, node_type: NodeType) -> list[GraphNode]:
    return graph.nodes_by_type(node_type)


def find_edges_by_type(graph: DrawingGraph, edge_type: EdgeType) -> list[GraphEdge]:
    return graph.edges_by_type(edge_type)


def find_nearby_text(graph: DrawingGraph, bounds: BBox, radius: float) -> list[GraphNode]:
    return [
        node
        for node in graph.nodes_by_type(NodeType.text)
        if node.bbox is not None and bbox_distance(node.bbox, bounds) <= radius
    ]


def find_grid_intersections(graph: DrawingGraph) -> list[GraphNode]:
    return graph.nodes_by_type(NodeType.grid_intersection)


def find_column_tags(graph: DrawingGraph) -> list[GraphNode]:
    return graph.nodes_by_type(NodeType.column_tag)


def find_footings(graph: DrawingGraph) -> list[GraphNode]:
    return graph.nodes_by_type(NodeType.footing)


def find_unresolved_detail_references(graph: DrawingGraph) -> list[GraphNode]:
    return [
        node
        for node in graph.nodes_by_type(NodeType.detail_reference)
        if not node.properties.get("resolved", False)
    ]
