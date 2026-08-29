# Suite Hidrosanitaria · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the real gaps of spec §2 (hidrosanitaria): corridas segmented by diameter where the plano labels more than one, vertical bajada runs derived from level-linked symbol stacks, grouped hallazgos for what can't be read, and the registry's `detect` slot getting its first tenant.

**Architecture:** Much of §2 already exists and stays untouched: `run_detector.py` reads one run per (layer, marco) with spec/diameter/material and system disambiguation; fixture families feed HID/SAN/MUE/GAS/AIR concepts via `_MUEBLES_POR_CONCEPTO`; corridas feed HID-003…GAS-001 via `_CORRIDAS_POR_CONCEPTO`; SAN-004 registros already derive. This plan is **measure-first**: Task 1 characterizes the mini fixture and the full instalaciones set, and Tasks 2–3 implement only what the measurement shows is real. One prior decision is deliberately revised: «bajada» sin concepto assumed its meters were already in the corrida — true in plan view, false for the **vertical** drop between levels, which plan linework never draws. The vertical derivation counts ONLY `(levels−1) × story height` per stack, never re-adding plan meters, and the comment's reasoning is updated in place.

**Tech Stack:** Python via `uv`, pydantic, ezdxf fixtures, pytest, `make eval-gold` (instalaciones-mini is the fence and is EXPECTED to be recaptured, declared, when Tasks 2–3 land), Marina instalaciones scratch copy.

**Spec:** [2026-08-28-motor-multidisciplina-design.md](../specs/2026-08-28-motor-multidisciplina-design.md) §2 · contract [2026-08-28-suites-por-disciplina-design.md](../specs/2026-08-28-suites-por-disciplina-design.md) §0.

## Global Constraints

- Fences: `make eval-gold` after every task — structural fixtures must never move; `instalaciones-mini` recaptures are expected ONLY in Tasks 2/3/5 and each is declared in its commit. Full suite + lint at closure. Never `pytest | tail`.
- Doctrine: HID-002 stays underived (network decision, not mueble); the taller's inventory mappings always win; nothing prices itself — new lines are unpriced (A9).
- Branch `git checkout -b suite-hidrosanitaria`; commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Medir antes de construir

Copy the full instalaciones project to scratch and reprocess (`data/uploads/marina_lote_04_instalaciones_596e05ed` → `$SCRATCH/marina-inst`), then measure on BOTH it and `data/uploads/gold_instalaciones_mini/processed`:

- [ ] **Step 1: Reprocess** the scratch copy with the current engine (house rule: never reprocess the user's project in place).
- [ ] **Step 2: Corridas** — per `pipe_run` detection: how many spec labels with **distinct nominal diameters** sit within `_SPEC_REACH_M` of its segments (reuse `_etiquetas_de_especificacion` + `normaliza_diametro` in an ad-hoc script)? Report: groups with 0 / 1 / ≥2 distinct diameters, and the meters in the ≥2 bucket. **Gate:** Task 2 is built only if the ≥2 bucket holds real meters (> 10 m somewhere); otherwise it is descoped with the measurement in the plan outcome.
- [ ] **Step 3: Bajadas** — for `fixture` detections with `fixture_family == "bajada"`: positions relative to their containing plan frame (center − frame bbox origin); cluster across frames of the same file at tolerance 0.5 m; report stack count, sizes, and whether the instalaciones frames carry NPT levels (`frames.json` `level_key`/`npt_level`, `views.json` story heights). **Gate:** vertical ML derivation needs levels; without them Task 3 stamps stacks + emits the grouped hallazgo only.
- [ ] **Step 4: Registros/coladeras** — count `registro`/`coladera` fixtures (SAN-004/SAN-005 feeds) so the «bajada sin registro» hallazgo has an honest denominator, or is descoped if the symbols simply aren't drawn.
- [ ] **Step 5:** Record all numbers in the task's commit message (docs-only commit if no code changed).

---

### Task 2: Corridas por tramo de diámetro (gated by Task 1)

When a (layer, marco) group's nearby labels declare ≥2 distinct nominal diameters, split it: assign each accumulated segment to its nearest own-system label (the `_sistemas_nombrados`/`_pedazo_de` disambiguation already exists), sum meters per diameter, and emit one `pipe_run` per (layer, marco, diámetro) whose notes state the split arithmetic. Groups with 0–1 diameters stay **byte-identical**.

**Files:**
- Modify: `packages/klave_engine/detection/run_detector.py` (`_spec_de` call site → a `_specs_por_tramo` that returns `[(spec, meters_du, entity_ids)]`)
- Test: `tests/test_instalaciones_detectors.py` (extend — it already exercises `detect_runs`)

- [ ] **Step 1: Failing test** — ezdxf fixture: one layer `00-SANITARIA` polyline network in one frame, a `2"` label hugging the first 10 m and a `4"` label hugging the last 20 m → two `pipe_run` detections, ~10 m at 51 mm and ~20 m at 102 mm, notes naming both labels; control: same network with one label → one detection, properties identical to today's.
- [ ] **Step 2–3:** red → implement (nearest-label-per-segment; a segment farther than `_SPEC_REACH_M` from every label joins the largest-meters tramo with the «sin rótulo cerca» note).
- [ ] **Step 4: Fences** — detector tests PASS; `make eval-gold`: structural fixtures identical; if `instalaciones-mini` moved, verify the new rows by hand against Step 1's measurement, recapture with `gold capture … --id instalaciones-mini --fresh`, and declare the before/after counts in the commit.
- [ ] **Step 5: Commit** — `feat(detección): la corrida se parte donde el plano cambia de diámetro — ML por diámetro nominal (hidrosanitaria)`.

---

### Task 3: Bajadas ligadas entre niveles (gated by Task 1)

**Files:**
- Create: `packages/klave_engine/detection/bajadas.py` — `stamp_bajada_stacks(detections, frames, segmentation) -> int`: clusters bajada-family fixtures by frame-relative position across plan frames of one file; stamps `properties["stack_id"]`, `properties["stack_levels"]`; when story heights are known, stamps `properties["vertical_length_m"] = (levels−1) × height` on ONE representative per stack (the lowest level), zero on the rest — one stack is one riser, never N.
- Modify: `packages/klave_engine/pipeline.py` — call after `segment_views` (frames + segmentation in scope), before the final `detections.json` write.
- Modify: `packages/klave_engine/costing/instalaciones.py` — revise the «bajada sin concepto» comment with the vertical/plan distinction, and add `SAN-006 («Tramo vertical de bajada, medido de los niveles del plano», M, FASE_SANITARIA)` fed by `QuantityRule(detection_type=fixture, kind=LENGTH, source_property="vertical_length_m", property_filter={"fixture_family": ["bajada"]})` — confirm `QuantityKind.LENGTH` + `source_property` semantics against an existing LENGTH rule before writing it.
- Test: `tests/test_bajadas.py` (create)

- [ ] **Step 1: Failing test** — synthetic: two plan frames (SheetFrame) of one file with `npt_level` 0.0 and 2.7, two bajada fixtures at the same frame-relative position + one unpaired; `stamp_bajada_stacks` → paired stack has `stack_levels == 2`, representative carries `vertical_length_m == 2.7`, unpaired has no stack; a boq built over the stamped detections shows SAN-006 == 2.7 m unpriced.
- [ ] **Step 2–3:** red → implement. If Task 1 found no levels on instalaciones frames, the stamps still land (stack_id/levels) but `vertical_length_m` stays absent and SAN-006 emits nothing — the hallazgo of Task 4 says why.
- [ ] **Step 4: Fences** — tests PASS; gold: structural identical; instalaciones-mini recapture declared if fixture properties changed its captured rows.
- [ ] **Step 5: Commit** — `feat(detección): las bajadas se ligan entre niveles — el tramo vertical que la corrida en planta nunca dibujó (hidrosanitaria; revisa la decisión «bajada sin concepto»)`.

---

### Task 4: Hallazgos hidrosanitarios, agrupados

In `costing/hallazgos.py` (the compliant findings system — NOT `risks/rules.py`), add two grouped rules following the existing `Rule` pattern (`group=`, plural headline, denominator, physical exposure, `momento`, `verificar`):

1. `corridas_sin_diametro`: n of N pipe_runs with `spec == ""` — exposure = their summed `length_m` («X m de tubería sin diámetro legible»), momento `cotizar`.
2. `bajadas_sin_nivel`: stacks stamped without `vertical_length_m` when bajadas exist — exposure = stack count, momento `entregar`, verificar pointing at declaring NPT levels on the plano.

**Test:** `tests/test_hallazgos.py` exists (`grep -l hallazgos tests/`) — mirror an existing rule's test: build detections, assert ONE card per rule with the denominator in its headline, never one card per element.

- [ ] **Steps:** failing test → implement → PASS → gold untouched (hallazgos are computed on demand, never persisted) → commit `feat(diagnóstico): corridas sin diámetro y bajadas sin nivel, agrupadas con denominador (hidrosanitaria)`.

---

### Task 5: La suite ocupa su hueco `detect`

**Files:**
- Create: `packages/klave_engine/detection/disciplines/hidrosanitaria.py` — `detect(entities, index, manifest, config, frames, ids, units)` returning the instalaciones trio (fixtures/runs/openings) exactly as `run_detectors` builds it today for `structural=False`.
- Modify: `packages/klave_engine/detection/disciplines/vocab.py` — `hidraulica` and `sanitaria` suites get `detect=` wired (import inside the field default is a cycle risk: assign in `disciplines/__init__.py` after both modules import instead).
- Modify: `packages/klave_engine/detection/suite.py` — in the `structural=False` branch: if the routed suite has `detect`, call it; else the default trio. Thread the routed suite (or its key) into `run_detectors` — today it only receives `structural: bool`; add `suite: DisciplineSuite | None = None` keeping the bool for compatibility.
- Test: `tests/test_disciplinas.py` — a sanitaria-named sheet routed through `run_detectors` produces the same outputs via the suite path (compare detection counts against a direct trio call on the same entities).

- [ ] **Steps:** failing test → implement → PASS → `make eval-gold` **identical everywhere** (the tenant changes wiring, not behavior — bajada stamping stays in the pipeline, shared by every discipline) → commit `feat(detección): hidrosanitaria ocupa el hueco detect del registro — el primer inquilino real (S1 cerrado de verdad)`.

---

### Task 6: Cierre

- [ ] Full suite (`uv run pytest -q; echo $?` → 0), `make lint` clean, `make eval-gold` PASS.
- [ ] Marina completo stability (P1 numbers hold) + full instalaciones scratch: report bajada stacks, corridas per diameter, SAN-006 meters, and the two new hallazgos with their denominators.
- [ ] «Suite hidrosanitaria cerrada» note in `docs/auditoria-motor.md` §4 with the measured numbers; tick this plan; note in the suites spec which §2 items were already built pre-plan (corridas con diámetro, muebles→salidas, registros) so the next suite's plan starts from reality.
- [ ] Docs commit → finishing-a-development-branch (merge menu).

## Out of scope

- HID-002 derivation (network decision — doctrine).
- Isométricos, pendientes as slope validation, cisterna/tinaco equipment sizing (later rounds, need real drawings that draw them).
- Rerouting by content vote (unchanged: needs more per-discipline gold).
