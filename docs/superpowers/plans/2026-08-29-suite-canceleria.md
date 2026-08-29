# Suite Cancelería · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cancelería reads its pieces from the plano's own nomenclatura: every `CANC_ALUM`-style insert carries its `CLAVE` attribute (CA-01, PA-02…) — one placed piece per insert, family from the clave prefix, feeding the existing CAN-001/CAN-002/CAR-001 concepts with zero costing changes.

**Architecture:** The scout on Marina completo overturned spec §1's cuadro assumption: there is **no text-table cuadro** (309 texts, zero N×M) — types are drawn as dimensioned alzados (119 cotas, next round's reader). What IS there: 35 `CANC_ALUM` inserts with `CLAVE` attributes and 22 tag types. So this round: `detect_cancel_pieces` (insert + clave attribute → `opening` detection with `opening_family` by prefix and the clave as mark), a claim filter so `detect_openings` never double-counts the same inserts, the canceleria suite occupying its `detect` slot, one grouped hallazgo for pieces without a legible clave, and a gold fixture freezing it. Dimensions-per-clave from the alzado cotas: deliberately next round, recorded.

**Tech Stack:** as the hidrosanitaria round. Gold: new `gold_canceleria_mini` from the already-converted cancelería DXF (coverage «parcial» is fine — the 35 inserts read).

**Spec:** [2026-08-28-suites-por-disciplina-design.md](../specs/2026-08-28-suites-por-disciplina-design.md) §1, revised by measurement.

## Global Constraints

- Fences: structural + instalaciones gold must never move; the new cancelería fixture is captured at the END (Task 4), so no recaptures at all this round. Full suite + lint at closure; never `pytest | tail`.
- Prefix→family: `CA|CB|C` → cancel · `PA|PTA|P` → puerta · `V|PV` → ventana (matches `_VANOS_POR_CONCEPTO`'s families: cancel/puerta/ventana). Unknown prefix → cancel with a note, never dropped.
- Branch `git checkout -b suite-canceleria`; commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: `detect_cancel_pieces` — la pieza que sabe su clave

**Files:**
- Create: `packages/klave_engine/detection/cancel_pieces.py` — `detect_cancel_pieces(entities, ids) -> DetectorOutput`: inserts whose `block_name` matches `CANC|CANCEL|PTALOUVER|PTA` (vocab) **and** whose `properties["attributes"]` carry a clave matching `^[A-Z]{1,4}-?\d{1,3}[A-Z]?$` → one `DetectionType.opening` detection per insert: label/mark = clave, `opening_family` by prefix table, `properties["clave"]`, confidence 0.85 (block + attribute, two declared facts), evidence noting both.
- Test: `tests/test_cancel_pieces.py` (create)

- [ ] **Step 1: Failing test** — ezdxf: block `CANC_ALUM` with an ATTDEF `CLAVE`; three inserts with attribute values `CA-01`, `PA-02`, `CA-01`; one insert with no attribute. Assert: 3 detections, families `{cancel: 2, puerta: 1}`, marks carry the claves, the attribute-less insert is NOT detected (it has no clave to declare), and `output.warnings` says «1 pieza de cancelería sin clave legible».
- [ ] **Step 2–3:** red → implement (attribute value = first attribute whose value matches the clave regex — the tag key varies by plano, `CLAVE` on Marina).
- [ ] **Step 4:** tests PASS; `make eval-gold` untouched (no wiring yet).
- [ ] **Step 5: Commit** — `feat(detección): la pieza de cancelería se lee de su clave — el bloque de nomenclatura ya sabe qué es`.

---

### Task 2: La suite ocupa su hueco, sin contar dos veces

**Files:**
- Create: `packages/klave_engine/detection/disciplines/canceleria.py` — `detect(entities, config, ids, meters_factor, frames)`: pieces first; then the default trio, with `detect_openings`' output **post-filtered**: any opening whose `source_entities` intersect the pieces' claimed entity ids is dropped (the same insert must not be a pieza and a vano).
- Modify: `packages/klave_engine/detection/disciplines/__init__.py` — `_DETECTORS["canceleria"] = canceleria.detect`.
- Modify: `packages/klave_engine/detection/disciplines/vocab.py` — canceleria gets `block_hints=("CANC", "PTALOUVER")` (content voting sees it).
- Test: `tests/test_disciplinas.py` (extend)

- [ ] **Step 1: Failing test** — parse a small DXF with one attributed `CANC_ALUM` insert on a canceleria-named sheet; route + `run_detectors(..., suite=route_sheet(...))` → exactly ONE opening detection for that insert (the piece), never two.
- [ ] **Step 2–3:** red → implement.
- [ ] **Step 4:** `make eval-gold` — instalaciones-mini and structural fixtures identical (no canceleria-named sheet among them).
- [ ] **Step 5: Commit** — `feat(detección): cancelería ocupa su hueco detect — la pieza manda y el vano genérico no la recuenta`.

---

### Task 3: El hallazgo agrupado

**Files:**
- Modify: `packages/klave_engine/costing/boq.py` (next to the hidrosanitaria block): ONE warning when opening detections on canceleria discipline carry no clave — «n de N piezas de cancelería sin clave legible: el cuadro no las puede nombrar». Emitted from the detector warning path instead if simpler — decide by where the denominator lives; the detector already warns per sheet (Task 1), so boq may only need the classification rule.
- Modify: `packages/klave_engine/costing/hallazgos.py` — `Rule(pattern=r"piezas? de cancelería sin clave", severity="revisar", group="canceleria_sin_clave", momento="cotizar", …)`.
- Test: `tests/test_hallazgos.py` — `_classify` returns the rule; denominator survives in the headline.

- [ ] **Steps:** failing test → implement → PASS → gold untouched → commit `feat(diagnóstico): piezas de cancelería sin clave legible, agrupadas (cancelería)`.

---

### Task 4: Gold, aceptación y cierre

- [ ] **Step 1:** `data/uploads/gold_canceleria_mini/drawings/` ← the converted cancelería DXF from the completo project (`data/uploads/marina_lote_04_completo_887d5624/converted/…canceleria…/*.dxf`); pipeline; inspect: expect ~35 pieces, families cancel/puerta, marks CA-*/PA-*; compare against the scout (22 claves, CA-15×6).
- [ ] **Step 2:** `gold capture … --id canceleria-mini --fresh`; `time make eval-gold` < 30 s, PASS.
- [ ] **Step 3:** Full suite + lint; Marina completo stability (P1 numbers).
- [ ] **Step 4:** Audit note «Suite cancelería cerrada» (measured numbers + the descoped cuadro-de-cotas reader recorded for the next round); tick plan; suites-spec row updated; docs commit; finishing-a-development-branch.

## Out of scope (recorded, not forgotten)

- **Dimensions per clave from the alzado cotas** (119 cotas on the sheet) → the m² of cancel and the S4 reader's first real tenant, next cancelería round.
- Tag↔vano matching against walls: Marina's walls carry 1 stamped vano today — data-poor; revisit when albañilería's suite lands.
- CAN-00x m² concepts: PZA flows now; m² needs the dimensions round.
