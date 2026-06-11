# Data Contracts

All contracts are pydantic models; JSON artifacts are their `model_dump(mode="json")`.

## Project manifest (`processed/project_manifest.json`)

`klave_engine.ingestion.manifest.ProjectManifest`:
`project_id`, `project_name`, `root_path`, `created_at`, `source_files[]`,
`converted_files[]`, `processing_status`, `warnings[]`, `errors[]`.

## Normalized entity (`processed/normalized_entities.json`)

`klave_engine.dxf.entities.NormalizedEntity`:
required `entity_id`, `entity_type`, `source_file`, `layer`, `bbox`,
`raw_handle`, `properties`, `evidence`; optional `text`, `points`,
`block_name`, `rotation`, `color`, `line_type`, `confidence`.

Bboxes are `(min_x, min_y, max_x, max_y)` in drawing units. Text bboxes are
conservative approximations (noted in evidence).

## Evidence packet

`klave_engine.graph.evidence.EvidencePacket`:
`source`, `method`, `entity_ids[]`, `bbox`, `confidence`, `notes[]`.
Attached to every entity, node, edge, detection, and risk finding.

## Graph (`processed/drawing_graph.json`)

`DrawingGraphExport`: `nodes[]` (`GraphNode`: `node_id`, `node_type`, `label`,
`bbox`, `source_entities`, `properties`, `confidence`, `evidence`),
`edges[]` (`GraphEdge`: `edge_id`, `edge_type`, `source_node_id`,
`target_node_id`, `properties`, `confidence`, `evidence`), plus count maps.

Node types: sheet, layer, block, line, polyline, arc, circle, hatch, text,
grid_line, grid_intersection, column_tag, beam_tag, footing, slab_region,
wall, detail_reference.

Edge types: CONTAINS, NEAR, INTERSECTS, ALIGNED_WITH, LABELS, REFERENCES,
BELONGS_TO_GRID, POSSIBLE_STRUCTURAL_ELEMENT, CONFLICTS_WITH.

## Detection (`processed/detections.json`)

`klave_engine.detection.results.Detection`:
`detection_id`, `detection_type`, `label`, `bbox`, `source_entities[]`,
`graph_nodes[]`, `confidence`, `evidence`, `properties`.

## Quantity report (`processed/quantity_report.json`)

`QuantityReport` with `assumed_unit` and `items[]` of `QuantityItem`:
`name`, `value`, `unit`, `confidence`, `source_detections[]`, `warnings[]`,
`assumptions[]`. No naked numbers.

## Risk report (`processed/risk_report.json`)

`RiskReport` with `findings[]` of `RiskFinding`: `risk_id`, `risk_type`,
`severity` (low|medium|high), `message`, `source_entities[]`,
`related_detections[]`, `bbox`, `evidence`, `recommended_human_action`.
