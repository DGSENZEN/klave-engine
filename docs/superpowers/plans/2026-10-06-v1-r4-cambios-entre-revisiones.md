# V1 · R4 — Qué cambió entre revisiones — implementation plan

> superpowers:executing-plans, inline. Steps `- [ ]`.

**Goal:** when a new revisión of the plano arrives, the engineer sees what changed — per concept in cantidades and pesos, per element (agregado · eliminado · movido · modificado), painted on the plano — and exports aditivas y deductivas in the generador format.

**Spec:** [producto v1 §3.1](../specs/2026-09-16-producto-v1-cuantificacion-design.md).

**Facts found (2026-10-06):** every reprocess keeps its run under `processed/runs/run_*` with its own `detections.json` and `cost_report.json`; `run_diff.json` already exists but only counts families and compares labels (labels are renumbered between runs: «MUE-01» vs «MUE-001» reads as 40 added + 5 removed); `engine.json` carries the engine fingerprint per run but no run records which drawings it read.

## Constraints
Fences as before. Element identity never guessed: unmatched means agregado/eliminado. A diff between runs of the same drawings says so («mismo plano, lectura distinta») — it must not pass an engine change off as a design change. Gold unchanged.

### Task 1 · `costing/cambios.py`
Element matching per (sheet, type): exact `element_id` (same mark, position within 5 cm) → igual/modificado; then same mark nearest centroid within 2 m → movido/modificado; leftovers agregado/eliminado. «Modificado» = a dimension property differs (sección, armado, longitud, área, espesor, diámetro, claro) by > 1 % or as text. Per concept: cantidad antes/después/delta, importe delta at the current P.U., the elements behind it. Tests with synthetic runs.

### Task 2 · Revisiones and API
Pipeline writes `inputs.json` per run (sha256 per source drawing). `GET /projects/{id}/revisiones` (runs, date, label, engine fingerprint, whether drawings changed vs the previous one), `PUT /projects/{id}/revisiones/{run_id}` (label), `GET /projects/{id}/cambios?antes=&despues=` (defaults: previous vs active). Tests.

### Task 3 · Aditivas y deductivas XLSX
`GET /projects/{id}/cambios.xlsx`: per concept (clave visible, descripción, unidad, antes, después, aditiva, deductiva, P.U., importe) and per element (con su referencia y liga al visor).

### Task 4 · Web
New entry «Cambios» in the Planos node (`/proyecto/[id]/cambios`): selector antes/después, concept table with deltas and pesos, element list by kind, honesty banner when the drawings didn't change, export; the visor paints the diff (`?cambios=<run>`: agregado/modificado/movido highlighted, eliminado as dashed ghosts); ⌘K.

### Task 5 · Docs, bitácora, memory, fences, finishing menu.
