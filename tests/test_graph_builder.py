"""Drawing graph construction tests."""

import pytest
from klave_engine.common.errors import GraphBuildError
from klave_engine.graph.builder import DrawingGraph, DrawingGraphBuilder
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.graph.schema import EdgeType, GraphEdge, GraphNode, NodeType


def _build(demo_drawing, demo_index) -> DrawingGraph:
    return DrawingGraphBuilder("demo_project_001").build([demo_drawing], demo_index)


def test_sheet_and_layer_nodes(demo_drawing, demo_index) -> None:
    graph = _build(demo_drawing, demo_index)
    sheets = graph.nodes_by_type(NodeType.sheet)
    assert len(sheets) == 1
    assert sheets[0].label == "S-101.dxf"
    layers = {n.label for n in graph.nodes_by_type(NodeType.layer)}
    assert {"S-GRID", "S-COL", "S-COL-TAG", "S-FOOTING", "S-BEAM", "S-SLAB",
            "S-WALL", "S-ANNO"} == layers


def test_entity_nodes_and_containment(demo_drawing, demo_index) -> None:
    graph = _build(demo_drawing, demo_index)
    entity_node_count = sum(
        len(graph.nodes_by_type(t))
        for t in (NodeType.line, NodeType.circle, NodeType.polyline, NodeType.text)
    )
    assert entity_node_count == len(demo_drawing.entities)
    contains = graph.edges_by_type(EdgeType.contains)
    # sheet->layer (8) + layer->entity (22)
    assert len(contains) == 8 + len(demo_drawing.entities)


def test_near_edges_from_text(demo_drawing, demo_index) -> None:
    graph = _build(demo_drawing, demo_index)
    near = graph.edges_by_type(EdgeType.near)
    assert near, "expected NEAR edges from text entities to nearby geometry"
    for edge in near:
        assert "distance" in edge.properties


def test_edge_to_missing_node_raises(demo_drawing, demo_index) -> None:
    graph = _build(demo_drawing, demo_index)
    with pytest.raises(GraphBuildError):
        graph.add_edge(
            GraphEdge(
                edge_id="edge_bad",
                edge_type=EdgeType.near,
                source_node_id="missing_a",
                target_node_id="missing_b",
                evidence=EvidencePacket(source="test", method="test"),
            )
        )


def test_merge_detector_output_skips_dangling_edges(demo_drawing, demo_index) -> None:
    builder = DrawingGraphBuilder("demo_project_001")
    graph = builder.build([demo_drawing], demo_index)
    node = GraphNode(
        node_id="det_test",
        node_type=NodeType.column_tag,
        label="C9",
        evidence=EvidencePacket(source="test", method="test"),
    )
    dangling = GraphEdge(
        edge_id="dedge_test",
        edge_type=EdgeType.labels,
        source_node_id="det_test",
        target_node_id="not_a_node",
        evidence=EvidencePacket(source="test", method="test"),
    )
    warnings = builder.merge_detector_output(graph, [node], [dangling])
    assert "det_test" in graph.nodes
    assert len(warnings) == 1
