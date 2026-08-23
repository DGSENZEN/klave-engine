# Klave Engine

CPU-only construction drawing intelligence + automated cost engineering MVP.

Klave Engine ingests project drawing folders, converts DWG files to DXF through an
external converter, parses DXF entities with ezdxf, normalizes geometry and text
into typed records, builds a drawing graph, runs deterministic structural
detectors (grids, column tags, footings, beams, slabs, walls, detail references)
— and then runs a full cost engineering workflow on top: catálogo de conceptos,
análisis de precios unitarios (APU), costo directo, indirectos / financiamiento /
utilidad / cargos adicionales, contingencia, programa de obra, flujo financiero
con anticipo y retenciones, and an operating-cost projection.

Spanish (Mexican) drawing conventions are first-class: layer hints and tag
patterns cover EJES/TRABES/LOSA/MURO/CASTILLO conventions out of the box, and
drawing units are auto-detected from the DXF header (`$INSUNITS`) with a
text-height heuristic fallback — detector thresholds scale to the real unit
automatically.

This is **not** a structural approval system and the insumo prices are editable
reference data, not market quotes. Every quantity carries evidence, confidence,
and explicit assumptions so a human cost engineer can inspect and correct it.

## Pipeline

```text
Project folder
→ DWG-to-DXF conversion (external converter)
→ DXF parsing (ezdxf, with malformed-file recovery)
→ normalized entities + drawing unit detection
→ geometry primitives + spatial index (shapely STRtree)
→ drawing graph
→ structural detectors (bilingual ES/EN, unit-scaled thresholds)
→ quantity takeoff + risk engine
→ cost engineering: BoQ → APU → integración → programa → flujo financiero
→ API / dashboard / report exports
```

Each stage writes an inspectable JSON artifact under `<project>/processed/` and
human-readable reports under `<project>/reports/`.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
make install          # uv sync
cp .env.example .env  # optional: configure converter path etc.
```

To convert DWG files you need an external converter (the engine never parses DWG
directly). Set `KLAVE_CONVERTER_EXECUTABLE_PATH` in `.env` to e.g. the ODA File
Converter binary. Projects that already contain DXF files work without it.

## Quick start (demo project)

```bash
make demo-data        # generate the synthetic demo DXF project
make process-demo     # run the full pipeline on it
make eval-demo        # run the regression/eval suite
make api              # FastAPI on :8000
make dashboard        # Streamlit dashboard
```

Or stage by stage with the CLI:

```bash
uv run klave ingest  data/demo/demo_project_001
uv run klave convert data/demo/demo_project_001
uv run klave parse   data/demo/demo_project_001
uv run klave process data/demo/demo_project_001
uv run klave report  data/demo/demo_project_001
```

## API

```http
GET  /health
GET  /projects
POST /projects                         {"project_name": ..., "root_path": ...}
GET  /projects/{project_id}
POST /projects/{project_id}/ingest
POST /projects/{project_id}/process
GET  /projects/{project_id}/entities?layer=&entity_type=&limit=&offset=
GET  /projects/{project_id}/graph
GET  /projects/{project_id}/detections?detection_type=&min_confidence=
GET  /projects/{project_id}/quantities
GET  /projects/{project_id}/risks
GET  /projects/{project_id}/report
```

The API reads generated artifacts; it does not recompute the pipeline per request
(except `POST .../process`, which runs it explicitly).

## Repository layout

```text
apps/api          FastAPI app (thin routes, no business logic)
apps/dashboard    Streamlit inspection dashboard
packages/klave_engine
  conversion/     DWG→DXF adapter around the external converter
  ingestion/      project manifest + folder scanning
  dxf/            ezdxf parsing + entity normalization
  geometry/       bbox/measurement helpers, shapely STRtree index
  graph/          typed drawing graph (nodes, edges, evidence)
  detection/      deterministic structural detectors
  takeoff/        quantity takeoff
  costing/        catálogo, APU, presupuesto, integración, programa, finanzas
  risks/          risk rules + report
  evals/          fixtures, detection/graph/takeoff evals, regression suite
  common/         config, logging, ids, io, errors
docs/             primeros pasos (guía del taller), despliegue en producción,
                  architecture, data contracts, detection rules, evaluation,
                  levantamiento, lectura IA, acabados, terracerías, intercambio OPUS/Neodata
tests/            pytest suite (unit, fixture-based, API contracts)
```

## Development

```bash
make test         # pytest
make lint         # ruff
make typecheck    # mypy
```

All units are raw drawing units unless a scale is configured; quantity reports
state this assumption explicitly. Detector thresholds are configurable via a
JSON file pointed to by `KLAVE_DETECTOR_CONFIG_PATH` (see
`klave_engine.pipeline.DetectorSuiteConfig`).
