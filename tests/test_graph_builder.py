"""Drawing graph derivation tests (sheet/layer/entity + semantic nodes)."""

import pytest
from klave_engine.common.errors import GraphBuildError
from klave_engine.detection.results import Detection, DetectionType, make_detection
from klave_engine.graph.builder import DrawingGraph, build_drawing_graph
from klave_engine.graph.evidence import EvidencePacket
from klave_engine.graph.schema import EdgeType, GraphEdge, NodeType


def _build(demo_drawing, detections: list[Detection] | None = None) -> DrawingGraph:
    return build_drawing_graph("demo_project_001", [demo_drawing], detections or [])


def test_sheet_and_layer_nodes(demo_drawing) -> None:
    graph = _build(demo_drawing)
    sheets = graph.nodes_by_type(NodeType.sheet)
    assert len(sheets) == 1
    assert sheets[0].label == "S-101.dxf"
    layers = {n.label for n in graph.nodes_by_type(NodeType.layer)}
    assert {"S-GRID", "S-COL", "S-COL-TAG", "S-FOOTING", "S-BEAM", "S-SLAB",
            "S-WALL", "S-ANNO"} == layers


def test_entity_nodes_and_containment(demo_drawing) -> None:
    graph = _build(demo_drawing)
    entity_node_count = sum(
        len(graph.nodes_by_type(t))
        for t in (NodeType.line, NodeType.circle, NodeType.polyline, NodeType.text)
    )
    assert entity_node_count == len(demo_drawing.entities)
    contains = graph.edges_by_type(EdgeType.contains)
    # sheet->layer (8) + layer->entity (one per entity)
    assert len(contains) == 8 + len(demo_drawing.entities)


def test_semantic_nodes_derived_from_detections(demo_drawing) -> None:
    detections = [
        make_detection(
            "det_1", DetectionType.column_tag, "C1", (0, 0, 1, 1), 0.9,
            ["ent_1"], "test", [], {"k": "v"},
        ),
        make_detection(
            "det_2", DetectionType.footing, "F1", (2, 2, 3, 3), 0.8, ["ent_2"], "test", [],
        ),
    ]
    graph = _build(demo_drawing, detections)
    assert len(graph.nodes_by_type(NodeType.column_tag)) == 1
    assert len(graph.nodes_by_type(NodeType.footing)) == 1
    column = graph.nodes_by_type(NodeType.column_tag)[0]
    assert column.node_id == "det_1" and column.confidence == 0.9
    assert column.properties == {"k": "v"}


def test_edge_to_missing_node_raises(demo_drawing) -> None:
    graph = _build(demo_drawing)
    with pytest.raises(GraphBuildError):
        graph.add_edge(
            GraphEdge(
                edge_id="edge_bad",
                edge_type=EdgeType.contains,
                source_node_id="missing_a",
                target_node_id="missing_b",
                evidence=EvidencePacket(source="test", method="test"),
            )
        )
