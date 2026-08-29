# Ronda Acabados y Plafones · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acabados deep on real data: rooms from the embedded arch base, finish claves from the PI/PL marker attributes, m² per clave per local — plus honest, documented verdicts for the two sub-rounds the scout killed (albañilería: xref-blocked; cancelería r2: no clave anchor near the alzado cotas).

**Architecture (scout-driven):** Marina's acabados sheet embeds its arch xref (444 `A-MUROS` lines) and marks every local with `PI` (piso) and `PL` (plafón) inserts whose attributes carry the clave; `QRF` ×312 marks wall finishes (deferred — point-per-wall aggregation unclear); `CAMBIO-ACABADOS` has no attributes (boundaries). Plafones' own sheet carries 21 «H LIBRE: N» texts (already read as specs). Albañilería's sheets are 988 cotas over a NON-embedded xref → nothing to derive; cancelería's alzado cotas (119) have no clave text/globe in their frames → dims-per-clave has no anchor on Marina. Both verdicts get recorded, not coded around.

**Fences:** existing gold untouched; new `acabados-mini` captured at the end; full suite + lint; Marina completo stability. Branch `git checkout -b ronda-acabados`.

**Spec:** [2026-08-28-suites-por-disciplina-design.md](../specs/2026-08-28-suites-por-disciplina-design.md) §6 (acabados y plafones), revised by measurement.

---

### Task 1: `detect_acabado_marks` — la clave del local

- Create `packages/klave_engine/detection/acabado_marks.py`: inserts named `PI`/`PL` (exact) with an attribute value matching `^[A-Z0-9]{1,3}$` → `DetectionType.fixture` detections: `fixture_family` `acabado_piso`/`acabado_plafon`, mark = clave, properties `{"clave": …, "acabado_tipo": "piso"|"plafon"}`. Attribute tag names vary (`P1`, `PL1`) — take the first plausible value. No attribute → counted in a warning «n marcas de acabado sin clave» (grouped later).
- Test `tests/test_acabados.py`: ezdxf fixture with PI(clave "4"), PL(clave "A"), PI without attribute → 2 detections with families/claves + the warning.

- [x] failing test → implement → PASS → gold untouched → commit `feat(detección): la marca de acabado se lee de su clave — PI y PL saben qué acabado lleva el local`.

### Task 2: La suite de acabados — áreas por clave por local

- Create `packages/klave_engine/detection/disciplines/acabados.py`: `detect()` = trio + `detect_rooms(entities, config.room, ids, frame_boxes)` + `detect_acabado_marks`, then a stamping pass: for each `room` detection, the PI/PL marks whose bbox center falls inside the room's bbox (rooms carry polygon? use bbox containment v1) stamp `room.properties["piso_clave"]`/`["plafon_clave"]`; marks outside any room stay loose (counted, noted).
- Wire `_DETECTORS["acabados"] = acabados.detect`; vocab `acabados` gets `block_hints=("QRF", "CAMBIO-ACABADOS")`.
- Test: parse a synthetic planta (wall rectangle grid making 2 rooms, the house `tests/test_rooms.py` fixture style) + PI/PL markers inside → rooms stamped with claves; suite path via `run_detectors(..., suite=…)` returns rooms+marks once each.

- [x] failing test → implement → PASS → gold untouched (no acabados-named sheet in fixtures) → commit `feat(detección): acabados ocupa su hueco — el local sabe su piso y su plafón`.

### Task 3: `acabados.json` — el resumen que el taller puede mapear

- In `pipeline.py`, after the detections write: aggregate rooms with claves → `acabados.json`: `[{tipo, clave, area_m2|None, area_du2, locales, vista}]` (meters only when units known — the A6 rule). One grouped detector-warning «n locales sin clave de acabado» (promotable rule added in hallazgos with severity `revisar`, group `locales_sin_acabado`).
- Lectura route serves it as `acabados` (same `_optional` pattern).
- Tests: pipeline fixture assertion (artifact exists, aggregates the stamped rooms); `_classify` for the new rule.

- [x] failing tests → implement → PASS → gold untouched → commit `feat(lectura): áreas de acabado por clave y por local — listas para que el taller las mapee (A6: sin unidad, sin m²)`.

### Task 4: Gold, veredictos y cierre

- [x] `data/uploads/gold_acabados_mini/drawings/` ← converted acabados + plafones DXFs; pipeline; inspect (expect: rooms with claves; PI 55/PL 43 marks; H LIBRE specs); `gold capture --id acabados-mini --fresh`; eval < 30 s PASS.
- [x] Full suite + lint; Marina completo stability (P1 numbers + suites intactas).
- [x] Audit note «Ronda acabados cerrada» INCLUDING the two verdicts: albañilería deep = xref-blocked (its sheets are cotas over a base that doesn't embed — same blocker class as eléctrica; unblocks with the conversion workstream), cancelería r2 dims = no anchor on Marina (cotas frames carry no claves; revisit with a plano that labels its alzados). Spec rows updated; tick plan; docs commit; finishing-a-development-branch.

## Out of scope (recorded)

- QRF wall-finish aggregation (312 point marks; semantics need the legend table) and the simbología/legend reader.
- Albañilería deep, cancelería m² — blocked as measured; no code faked.
- Concept binding for acabado claves: claves are per-plano, so pricing goes through the taller's mapping flow; a mapping kind for «acabado» lands with the tablero/lectura UX round.
