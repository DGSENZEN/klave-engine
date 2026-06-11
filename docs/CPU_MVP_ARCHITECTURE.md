# CPU MVP Architecture

## Pipeline

```text
Project folder
→ DWG-to-DXF conversion (external converter, subprocess adapter)
→ DXF parsing (ezdxf)
→ normalized entities (pydantic, one shared schema)
→ geometry primitives (shapely)
→ spatial index (shapely STRtree)
→ drawing graph (typed nodes/edges with evidence)
→ structural detectors (deterministic, rule-based)
→ quantity takeoff
→ risk engine
→ API / dashboard / report exports
```

Every stage writes an inspectable JSON artifact under `<project>/processed/`
and logs a `*_completed` event with counts and durations.

## Package responsibilities

| Package | Responsibility |
|---|---|
| `common` | config (pydantic-settings), logging, IDs, JSON IO, exceptions |
| `ingestion` | project manifest schema + folder scanning |
| `conversion` | `DwgToDxfConverter` adapter around the external converter |
| `dxf` | ezdxf parsing, entity normalization, layer/block summaries |
| `geometry` | bbox helpers, measurements, shapely conversions, `SpatialIndex` |
| `graph` | `DrawingGraph`, builder, queries, `EvidencePacket` |
| `detection` | grid/column/footing/beam/slab/wall/detail-reference detectors |
| `takeoff` | quantity report with provenance and unit assumptions |
| `risks` | deterministic risk rules and report |
| `evals` | synthetic fixtures, detection/graph/takeoff evals, regression suite |
| `pipeline` | explicit stage orchestration (`run_full_pipeline`) |

## Design rules

- Typed pydantic schemas at every boundary; dataclasses internally.
- Detectors are pure functions: entities + index in, `DetectorOutput` out.
- No detection without an `EvidencePacket` (source, method, entity IDs, confidence).
- The API reads artifacts; it never recomputes per request (except explicit `/process`).
- Streamlit pages contain no business logic.
- Prefer false negatives over hallucinated detections.

## Out of scope (future phases)

Raw DWG parsing, GPU kernels, deep learning, RAG/LLM reasoning, cloud
deployment, multi-user auth, IFC export, code-compliance approval.
