# Piloto listo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** the pilot's gate («horas ahorradas, generadores aceptados, export importado») can be measured from the product itself, and the whole path a stranger walks — DWG in, generadores and OPUS/Neodata out — works without snags.

**Spec:** `docs/superpowers/specs/2026-09-16-producto-v1-cuantificacion-design.md` §8 (Pilot), `2026-10-04-lector-que-aprende-design.md` §8 (minutes of review per sheet).

## Global constraints

- Measuring never blocks a request or a run; a failed write is dropped silently.
- Times are estimates and say so: active time counts gaps of up to 10 minutes between a person's actions; longer gaps are idle and start a new session.
- Nothing leaves the project; the activity log holds event types, actors, times and short details — never drawings.
- The comparison uses the hours the office declares for its old way; Klave never invents a baseline.

### Task 1: the activity log
- `apps/api/actividad.py`: `registrar(control_dir, tipo, actor, datos)` appends to `processed/actividad.jsonl`; `EventBus.escuchar(fn)` listeners called after publish; a listener in `main.py` persists project events (not presence/collaborator activity; job updates only when terminal).
- Exports (`_mark_exported`) record the format.
- Labels already carry `at` (no change needed).

### Task 2: the measurement
- `costing/piloto.py`: `medir(control_dir, artifacts_dir, labels, actividad, jobs, piloto) -> dict` — inicio, procesamiento (último y total), revisión activa (minutos, sesiones, decisiones), entrega (primera exportación, formatos), por hoja (decisiones and estimated minutes by share of decisions), método anterior and ahorro.
- `GET/PUT /projects/{id}/piloto` (`horas_metodo_anterior`, `notas`, `generadores_aceptados`, `export_importado`).

### Task 3: the page
- `/proyecto/[id]/piloto` «Medición del piloto» under the Presupuesto node: the four stages, minutes per sheet, the declared old-way hours and the three gate answers; a copyable summary.

### Task 4: dry run
- A fresh project from a real DWG through Revisión, catálogo mapping, generadores, OPUS and Neodata exports, and the export read back by our own OPUS/Neodata readers; fix every snag found.

### Task 5: docs, bitácora, memory, fences, finishing menu.
