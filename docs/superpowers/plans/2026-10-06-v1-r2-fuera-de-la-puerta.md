# V1 · R2 — Fuera de la puerta: generadores con referencia, OPUS/Neodata por variante, lo que el plano no dio, liga para compartir — implementation plan

> **For agentic workers:** superpowers:executing-plans, inline. Steps `- [ ]`.

**Goal:** what leaves Klave is something a cuantificador takes as-is: every generador line says which element, on which sheet and planta, near which ejes (when the drawing names them), with a link to see it; the OPUS/Neodata workbook carries one row per variant in the office's claves, never the engine's rule codes; a «Lo que el plano no dio» list travels with every set; a read-only link lets a supervisor or partner click any line without an account.

**Spec:** [producto v1 §2.3, §2.4, §2.5](../specs/2026-09-16-producto-v1-cuantificacion-design.md).

## Global constraints
Fences as R1 (ruff, mypy, pytest, gold, tsc, eslint, build). No confidence percentage on any export or screen. No rule code as the visible clave of an exported row. The share link is read-only, unguessable (`secrets.token_urlsafe(24)`), expiring (default 14 days, max 90), revocable, scoped to one project, and serves only geometry and the generadores — never the presupuesto money unless the project's money state allows it.

### Task 1 · References per element
`costing/referencias.py`: `element_id(detection, meters_factor)` (sha1 of sheet basename, type, mark, centroid quantized to 5 cm), `ejes_cercanos(detection, grid_lines, meters_factor)` (only grid lines whose label came from the drawing), `planta(detection, segmentation)`, `referencia(...) -> Referencia` with a visor URL (`/proyecto/{id}/plano?bbox=…`). Generadores sheet rewritten: grouped by variant with the office's clave, columns Elemento · Marca · Hoja · Planta · Ejes · Medida · Ver en el plano; confidence column removed. Tests.

### Task 2 · OPUS / Neodata by variant
`_flat_workbook` writes one row per variant: clave = mapped clave, else the line's taller alias, else a neutral sequential `PL-0001`; columns add Partida; a second sheet «Lo que el plano no dio». Round-trip test (export → openpyxl read → same claves/quantities, Σ = presupuesto). Real-install verification is Diego's.

### Task 3 · Lo que el plano no dio
`costing/captura.py`: (a) elements the engine saw that no line consumed, by family; (b) lines without price; (c) levantamiento symbols with no mapping. `GET /projects/{id}/captura`; a sheet in every workbook; a collapsible callout on Presupuesto. Tests.

### Task 4 · Liga para compartir
Store `data_dir/share_links.json` (token → project, expiry, creator); `POST/GET/DELETE /projects/{id}/compartir` (behind the project middleware); public `GET /compartido/{token}` (meta), `/compartido/{token}/geometry`, `/compartido/{token}/generadores.xlsx` under a new OPEN prefix; web page `/compartido/[token]` with the visor read-only; «Compartir» lives in the existing Exportar menu. Tests: expired/revoked/unknown → 404, no other project reachable.

### Task 5 · Docs, bitácora, memory, artifact, fences, finishing menu.
