"""Graph evaluation: semantic node counts and detail reference resolution."""

from pydantic import BaseModel

from klave_engine.graph.builder import DrawingGraph
from klave_engine.graph.queries import find_unresolved_detail_references
from klave_engine.graph.schema import NodeType


class GraphEvalResult(BaseModel):
    node_type: str
    expected_count: int
    actual_count: int
    passed: bool


def evaluate_graph(
    graph: DrawingGraph, expected_node_counts: dict[str, int]
) -> list[GraphEvalResult]:
    results = []
    for node_type_name, expected in sorted(expected_node_counts.items()):
        actual = len(graph.nodes_by_type(NodeType(node_type_name)))
        results.append(
            GraphEvalResult(
                node_type=node_type_name,
                expected_count=expected,
                actual_count=actual,
                passed=actual == expected,
            )
        )
    return results


def detail_resolution_summary(graph: DrawingGraph) -> dict:
    detail_nodes = graph.nodes_by_type(NodeType.detail_reference)
    unresolved = find_unresolved_detail_references(graph)
    return {
        "detail_reference_count": len(detail_nodes),
        "unresolved_count": len(unresolved),
        "unresolved_labels": sorted(n.label for n in unresolved),
    }
