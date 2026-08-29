# Motor Espine S1–S5 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the multidiscipline spine: a discipline registry that owns routing (S1), the prefab index as a first-class artifact (S2), declared per-file conversion coverage (S3), pluggable cuadro readers (S4), and the first multidiscipline gold fixture (S5) — all behavior-preserving except where declared.

**Architecture:** Refactor-with-fences: the registry *reproduces* today's routing exactly (gold + Marina counts are the fence); content voting ships as warnings only — actual rerouting waits for suites with their own gold (per the spec's own rule). The prefab index is a new read-only artifact consumed by the Lectura. Deep DWG recovery (ELECTRICO `READ ERROR 0x940`) is explicitly out: S3 here means *coverage is declared, never silent* — recovery is its own spike when a suite needs that file.

**Tech Stack:** Python via `uv`, pydantic, ezdxf fixtures, pytest, `make eval-gold`, Marina scratch at the session scratchpad (`marina-acc`).

**Spec:** [2026-08-28-motor-multidisciplina-design.md](../specs/2026-08-28-motor-multidisciplina-design.md) §1 (S1–S5) · suites contract in [2026-08-28-suites-por-disciplina-design.md](../specs/2026-08-28-suites-por-disciplina-design.md) §0.

## Global Constraints

- Same fences as P0/P1: `make eval-gold` green after every task (no recaptures expected in this plan — any moved count is a bug); never `pytest | tail`; Spanish product copy; no new dependencies.
- Marina stability: the Task 8 acceptance re-runs `marina-acc` and every count from the P1 close (593 ejes estructural, ≥175 ancladas, 0 fantasma, sparse 0) must hold within noise (±2) — the registry refactor may not move detection behavior.
- `make eval-gold` total runtime stays under ~30 s after Task 7's new fixture.
- Branch: `git checkout -b motor-espine`. Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: S1a — El registro de disciplinas existe y reproduce el ruteo de hoy

`reads_as_structure`/`NON_STRUCTURAL`/`_DISCIPLINE_HINTS` (`inventory.py:36-141`) become a registry. v1 scope: routing + vocabulary + the structural flag. The `detect` callable slot exists but defaults to `None` (suite.py keeps its wiring; hidrosanitaria fills the slot in its own plan). `reads_as_structure` and `guess_discipline` survive as thin wrappers so their ~6 call sites (pipeline, views, inventory) don't churn.

**Files:**
- Create: `packages/klave_engine/detection/disciplines/__init__.py` (registry + `route_sheet`)
- Create: `packages/klave_engine/detection/disciplines/vocab.py` (per-discipline name/layer/block patterns — no detector imports, so no cycles)
- Modify: `packages/klave_engine/detection/inventory.py` (`guess_discipline`/`reads_as_structure` delegate; `_DISCIPLINE_HINTS`/`NON_STRUCTURAL` move out)
- Test: `tests/test_disciplinas.py` (extend)

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class DisciplineSuite:
    key: str                      # "estructural" | "hidraulica" | … | "levantamiento"
    name_hint: re.Pattern[str]    # matches slugified sheet names (ñ dropped)
    layer_hints: tuple[str, ...] = ()
    block_hints: tuple[str, ...] = ()
    structural: bool = False      # today's reads_as_structure semantics
    detect: Callable[..., list] | None = None  # filled by real suites later

REGISTRY: dict[str, DisciplineSuite]
def route_sheet(sheet_label: str) -> DisciplineSuite  # unknown → estructural (today's rule)
```

- `guess_discipline(text)` ≡ first registry suite whose `name_hint` matches (same order as today's `_DISCIPLINE_HINTS`); `reads_as_structure(label)` ≡ `route_sheet(label).structural`.

- [x] **Step 1: Failing test** — append to `tests/test_disciplinas.py`:

```python
from klave_engine.detection.disciplines import REGISTRY, route_sheet


def test_el_registro_reproduce_el_ruteo_de_hoy():
    # La tabla de la casa: nombre → disciplina → ¿detectores estructurales?
    tabla = [
        ("02-02_estructural_l_04.dwg", "estructural", True),
        ("Plano 1.dwg", "estructural", True),          # desconocido = estructura
        ("02-05_sanitario_l_04.dwg", "sanitaria", False),
        ("03-09_gas_l_04.dwg", "gas", False),
        ("03-03_alba_iler_a.dwg", "albanileria", False),
        ("01-00_indice_l_04.dwg", "indice", False),
        ("04-08_aa_l_04.dwg", "aire", False),
    ]
    for nombre, key, estructural in tabla:
        suite = route_sheet(nombre)
        assert suite.key == key, nombre
        assert suite.structural is estructural, nombre
    assert "estructural" in REGISTRY and REGISTRY["estructural"].structural
```

- [x] **Step 2: Run, expect `ModuleNotFoundError`.**
- [x] **Step 3: Implement** — move the hint patterns verbatim into `vocab.py` (one `DisciplineSuite` per current hint entry, `structural=True` only for `estructural` and the unknown default; keep the exact ordering — sanitaria's `ALBA[ÑN]AL` before albanileria etc. as today). `route_sheet` normalizes separators exactly like `guess_discipline` does today, walks the registry in order, falls back to `REGISTRY["estructural"]`. Rewrite `inventory.guess_discipline`/`reads_as_structure` as delegates; delete `_DISCIPLINE_HINTS`/`NON_STRUCTURAL` (grep first: `grep -rn "NON_STRUCTURAL\|_DISCIPLINE_HINTS" packages apps tests` — update any direct consumer).
- [x] **Step 4: Fences** — `uv run pytest tests/test_disciplinas.py tests/ -q -k "inventory or levantamiento or frames or vista"` PASS; `make eval-gold` PASS identical.
- [x] **Step 5: Commit** — `feat(detección): el registro de disciplinas existe y reproduce el ruteo de hoy (S1a)`.

---

### Task 2: S1b — El contenido vota, con aviso (sin rerutear)

Filenames lie; content votes. v1 emits a pipeline warning when the content winner disagrees with the filename route — rerouting waits for per-discipline gold (spec rule: nothing moves quantities without its own fence).

**Files:**
- Modify: `packages/klave_engine/detection/disciplines/__init__.py` (add `vote_content`)
- Modify: `packages/klave_engine/pipeline.py` (emit the warning next to the existing «Hoja leída como instalaciones» block)
- Test: `tests/test_disciplinas.py`

**Interfaces:**
- Produces: `vote_content(entities) -> tuple[str, int] | None` — counts entities whose `layer` (or `block_name`) matches each suite's `layer_hints`/`block_hints` via `layer_matches`; returns the winning `(key, hits)` when the winner has ≥ 20 hits and ≥ 3× the runner-up, else `None`. Seed vocabularies only where we know them from Marina (vocab.py): sanitaria `("SANITARIA", "PLUV")`, gas `("GAS",)`, aire blocks `("COND", "COMPUERTA")`, estructural `("EST", "EJES", "TRABE", "ZAPATA")` — deliberately conservative.

- [x] **Step 1: Failing test** — build 30 `NormalizedEntity`-bearing lines on layer `00-SANITARIA` (parse a tiny ezdxf file, the house pattern), assert `vote_content(entities) == ("sanitaria", 30)`; assert `None` for mixed content below margin.
- [x] **Step 2–3:** run/red, implement (pipeline: when `vote_content` disagrees with `route_sheet(label).key`, warn `«La hoja {sheet} se lee como {ruta} por su nombre; su contenido vota {ganador} ({hits} trazos). Revisa el nombre del archivo.»` — warning only, routing unchanged).
- [x] **Step 4: Fences** — tests PASS, gold PASS identical; re-run Marina scratch and **report** how many voting warnings appear (expected: 0–2; if a structural sheet votes elsewhere, investigate before shipping).
- [x] **Step 5: Commit** — `feat(detección): el contenido de la hoja vota su disciplina — aviso cuando contradice al nombre (S1b)`.

---

### Task 3: S2a — `prefab_index.json`: detectar una vez por definición

**Files:**
- Create: `packages/klave_engine/detection/prefabs.py`
- Modify: `packages/klave_engine/pipeline.py` (build + `write_json` after parse, near `block_summary.json`)
- Test: `tests/test_prefabs.py` (create)

**Interfaces:**
- Produces:

```python
class PrefabInstance(BaseModel):
    entity_id: str
    source_file: str
    bbox: BBox

class PrefabDefinition(BaseModel):
    name: str
    familia: str | None = None       # familia_de_bloque hit (symbol table)
    que_es: str | None = None
    clase: str | None = None         # parse_block_name (Revit-style) class
    es_anotacion: bool = False       # cajetines, north arrows (_ANOTACION)
    attdefs: list[str] = []
    instances: list[PrefabInstance] = []

def build_prefab_index(
    entities: list[NormalizedEntity], block_attdefs: dict[str, dict[str, list[str]]]
) -> list[PrefabDefinition]
```

built from `entity_type == insert` entities grouped by `block_name` (top-level AND nested — P1's parser work makes nested inserts visible), classification via `familia_de_bloque(name, layer)` and `parse_block_name` (`dimensions.py:63`), `_ANOTACION` from `opening_detector`/`inventory` (import the existing regex, don't duplicate it). `block_attdefs` comes per file from `parse_summary` — pass `{source_file: {name: tags}}` and union tags per name.

- [x] **Step 1: Failing test** — reuse the P1 nested-block fixture shape: block `INODORO` (2 instances) + nested `SIMBOLO-WC` inside `BANO-TIPO`; parse, `build_prefab_index`, assert: `INODORO` definition has 2 instances and `familia == "wc"`; `SIMBOLO-WC` exists (nested identity); a `*`-anonymous block never appears.
- [x] **Step 2–3:** red, implement, and wire into `run_full_pipeline` writing `processed/prefab_index.json` (drawing-level `block_attdefs` are already on each `ParsedDrawing`).
- [x] **Step 4: Fences + Marina probe** — tests PASS, gold PASS (new artifact, no behavior change); on the Marina scratch re-run assert `prefab_index.json` exists and contains `DESCSAN1` with ≥ 1 instance and a non-null classification. Report the index size (definitions / instances).
- [x] **Step 5: Commit** — `feat(detección): el índice de prefabricados — cada definición se clasifica una vez y estampa sus instancias (S2a)`.

---

### Task 4: S2b — La Lectura sirve el índice

**Files:**
- Modify: `apps/api/routes/lectura.py` (read `prefab_index.json` via the existing `_optional(store, project_id, …)` pattern at `lectura.py:115-123`; add a `prefabs` field: name, familia, que_es, instance count, attdef tags — summary only, not instances)
- Modify: `apps/web/lib/api.ts` (extend the `Lectura` type with `prefabs`)
- Test: mirror the nearest API test that exercises a `/projects/{id}/…` GET (find with `grep -rln "lectura\|/projects/" tests/test_*api*.py tests/test_auth.py | head`) — assert the field appears and is `[]` when the artifact is missing.

- [x] **Step 1–4:** failing test → implement → PASS → gold PASS. (No UI rendering here — the tablero/lectura frontend track consumes the field later; the type lands now so the payload is stable.)
- [x] **Step 5: Commit** — `feat(api): la lectura sirve el índice de prefabricados (S2b)`.

---

### Task 5: S4 — Lectores de cuadros enchufables

**Files:**
- Modify: `packages/klave_engine/detection/schedules.py:667` (`build_schedule_inventory(..., extra_readers: list[Callable[[list[NormalizedEntity]], list[SectionSpec]]] | None = None)` — read the actual entry model name in `schedules.py` first and use it; append reader outputs to `specs` with the same source rank as `tabla`)
- Test: `tests/test_schedules.py` if it exists (`ls tests/ | grep -i sched`), else create `tests/test_cuadros_enchufables.py`

- [x] **Step 1: Failing test** — a fake reader returning one entry for mark `CA-1`; assert it lands in the inventory (`by_mark`) and that with `extra_readers=None` behavior is byte-identical (compare against a no-reader call on the same entities).
- [x] **Step 2–4:** red → implement → PASS; gold PASS identical (nothing passes readers yet).
- [x] **Step 5: Commit** — `feat(detección): la cadena de cuadros acepta lectores por disciplina (S4)`.

---

### Task 6: S3 — Cobertura declarada por archivo

Conversion already records per-file `status`/`error_message` (`conversion_results.json`); parse warns per file. What's missing is one **verdict** the UI and the suites can trust: every source file gets `coverage: ok | parcial | ilegible` with its reasons, in `parse_summary.json` and surfaced by the Lectura.

**Files:**
- Modify: `packages/klave_engine/pipeline.py` (`_summarize_parse` gains `coverage` + `coverage_reasons`, derived from: conversion status failed → `ilegible`; recovered/sanitized load, minimal-mode conversion, `block_explosion_capped`, `block_nesting_truncated`, or 0 model-space entities → `parcial` with the reason strings; else `ok`) — the conversion record must be passed in; thread `conversion_results` into `_summarize_parse` (both call sites).
- Modify: `apps/api/routes/lectura.py` (expose per-sheet `coverage`)
- Test: `tests/test_parser.py` or `tests/test_labels_and_units.py` (whichever already asserts on `parse_summary.json` — check both; else extend the pipeline test)

- [x] **Step 1: Failing test** — a DXF project where one file parses clean (`coverage == "ok"`) and one is a deliberately truncated/garbage `.dxf` (write bytes) → its summary row says `ilegible` with a reason, and the pipeline still completes (one broken sheet never costs the project — existing doctrine).
- [x] **Step 2–4:** red → implement → PASS; gold PASS; on Marina scratch report the coverage table (expect: ELECTRICO absent-or-ilegible — it never converted; CARPINTERÍA `parcial` if present with 0 entities).
- [x] **Step 5: Commit** — `feat(dxf): cobertura declarada por archivo — ok, parcial o ilegible, con sus razones (S3)`.

---

### Task 7: S5 — El primer gold multidisciplina

A small, fast fixture: two of Marina instalaciones' already-converted DXFs (sanitaria + AA — symbol- and run-rich, both readable), as their own project. DXF input ⇒ no conversion at eval time ⇒ gold stays fast.

**Files:**
- Create: `data/uploads/gold_instalaciones_mini/drawings/` (copy the `.dxf` from `data/uploads/marina_lote_04_instalaciones_596e05ed/converted/02-05_sanitario_*/` and `04-08_aa_*/`)
- Create (via tool): `evals/gold/instalaciones-mini.json`

- [x] **Step 1:** copy the two DXFs, `uv run python -c "…run_full_pipeline(Path('data/uploads/gold_instalaciones_mini'))"`.
- [x] **Step 2:** inspect `processed/detections.json` by hand — fixtures/runs counts must look sane against memory's Marina facts (subida-bajada/DESCSAN1 symbols, compuertas) before freezing them. Record the numbers in the commit message.
- [x] **Step 3:** `uv run python -m klave_engine.evals.gold capture data/uploads/gold_instalaciones_mini --id instalaciones-mini --fresh`
- [x] **Step 4:** `make eval-gold` → PASS including the new entry; time it (`time make eval-gold`) — must stay < 30 s total.
- [x] **Step 5: Commit** — `test(gold): primer fixture multidisciplina — sanitaria y AA de Marina, congeladas antes de que las suites las muevan (S5)`.

---

### Task 8: Cierre — estabilidad de Marina, suite completa, docs

- [x] **Step 1:** `uv run pytest -q; echo $?` → 0. `make eval-gold` → PASS.
- [x] **Step 2:** Marina scratch re-run + the P1 acceptance assertions unchanged (593±2 ejes, ≥175 ancladas, 0 fantasma, sparse 0, col_sin_eje ≤ 2) **plus** the new artifacts present (`prefab_index.json`, coverage table) and the voting-warning count from Task 2 reported.
- [x] **Step 3:** append «Espine cerrado» to `docs/auditoria-motor.md` §4 with the measured numbers; tick this plan's checkboxes; note in the multidiscipline spec that S1–S5 v1 landed and what `detect`-slot work moved to the hidrosanitaria plan.
- [x] **Step 4:** docs commit; then finishing-a-development-branch (suite on the exact tree, merge menu, cleanup).

---

## Out of scope

- Rerouting by content vote (needs per-discipline gold — hidrosanitaria plan).
- Deep DWG recovery (ELECTRICO 0x940, carpintería blocks) — its own spike; S3 here only guarantees the loss is *declared*.
- Any detector consuming the prefab index (hidrosanitaria is its first real consumer).
- UI rendering of prefabs/coverage (frontend track).
