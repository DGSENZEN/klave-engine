# V1 · R1 — Variantes del plano y mapeo a tu catálogo — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline, Diego's standing preference). Steps use `- [ ]`.

**Goal:** the generadores stop speaking in rule codes. Each BoQ line splits into variants by what the drawing says about its elements (sección, armado, tipo, espesor, diámetro, material), each variant maps onto the office's own catálogo with its reason, and a correction is remembered for the next project.

**Architecture:** variants live **inside** `BoqLine.variants` (≈15 modules index lines by `concept_code`; splitting lines would break them). `costing/sintesis.py` computes a signature per detection and splits a line by recomputing the same rule on each signature group, scaled so Σ variants == line quantity exactly. `costing/mapeo.py` proposes a target for each variant from the office base (taller concepts without a rule + reference rows of imported matrices sources) with the existing matcher; the store keeps `variant_mappings` (memory). The report applies the memory: clave, description and price per variant; the line's amount becomes Σ variant amounts. A `labels.jsonl` per project records each Revisión and mapping decision (flywheel F1 hook).

**Spec:** [producto v1 §2.2, §2.6](../specs/2026-09-16-producto-v1-cuantificacion-design.md), [lector §6](../specs/2026-10-04-lector-que-aprende-design.md).

## Global constraints
Fences: ruff, pytest, `make eval-gold`, mypy (now must be clean), tsc, eslint, web build. Gold quantities per concept unchanged; new gold assertion Σ variants == line. No new header buttons. No rule code as the visible identity of a mapped variant. Explicit `git add` paths (other session's deploy files stay out).

### Task 0 · Cleanup the audit found
mypy's 6 errors; the "Se puede deshacer desde Importaciones" notice has no UI → the Importaciones section lists price adjustments with «Deshacer»; docs claiming catalog migrations v2→v14 corrected to the real chain (v27).

### Task 1 · Signatures and variants in the BoQ
`costing/sintesis.py` (`firma`, `slug`, `descripcion_variante`, `repartir`), `models.BoqVariant` + `BoqLine.variants`, `boq.py` loop body extracted into a per-subset compute; the multi-diameter warning becomes a note that the line splits. Tests `tests/test_sintesis.py`; gold Σ check in `evals/gold.py`.

### Task 2 · Mapping memory and proposals
Store v28 `variant_mappings`; `costing/mapeo.py` (`candidatos_del_taller`, `proponer`, `aplicar_mapeo`); report applies memory after adjustments, recomputes totals. Tests `tests/test_mapeo.py`.

### Task 3 · API + labels
`GET /projects/{id}/variantes`, `POST /projects/{id}/variantes/mapear`, `PUT /catalog/variantes/{key}` (confirm / change / sin equivalente), `DELETE /catalog/variantes/{key}`; `costing/etiquetas.py` appends to `labels.jsonl` from review and mapping endpoints. Tests.

### Task 4 · Web
Revisión gains the «Tu catálogo» tab: variants grouped by partida with the mapped clave and its status, row actions (confirmar, cambiar via ConceptPicker, sin equivalente); presupuesto lines unfold their variants; ⌘K entry.

### Task 5 · Docs, bitácora, memory, fences, finishing menu.
