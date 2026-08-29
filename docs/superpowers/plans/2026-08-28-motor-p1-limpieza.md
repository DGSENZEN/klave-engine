# Motor P1 — Limpieza estructural · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the audit's P1 findings (E5–E9) plus the eje-fragmentation residual, leaving the structural suite honest and stable before the multidiscipline spine lands.

**Architecture:** Surgical fixes in `packages/klave_engine/` following the P0 pattern: test-first, gold as the fence, any intentional quantity change recaptures gold declaring it in the commit. Two tasks are measure-first (E6 fallback, fragmentation) — they characterize real behavior before changing it.

**Tech Stack:** Python via `uv`, pydantic, ezdxf test fixtures in `tmp_path`, pytest, `make eval-gold`, Marina scratch artifacts at the session scratchpad (`marina-acc`).

**Spec:** [docs/auditoria-motor.md](../../auditoria-motor.md) (E5–E9, §4 residual) · sequence position 1 of [2026-08-28-motor-multidisciplina-design.md](../specs/2026-08-28-motor-multidisciplina-design.md) §3.

## Global Constraints

- `uv run pytest tests/<file>.py -q`; never pipe pytest through `tail` — check `$?`.
- `make eval-gold` green at the end of every task; recapture ONLY for declared intentional changes (Task 4 is the only one expected to).
- Spanish product copy; house comment style; no new dependencies.
- Work on a feature branch off `main` (same in-place branch pattern as P0 — `data/uploads/` is needed for verification): `git checkout -b motor-p1-limpieza`.
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Minas de configuración — el config externo escala, y `detections.json` se escribe una vez (E9)

`load_detector_config` (`suite.py:140-148`) returns an external JSON verbatim, silently skipping all unit scaling — `slab_detector.py:25` (`min_area = 10000.0`) shows how far raw defaults sit from the metre presets. And `pipeline.py` writes `detections.json` before view segmentation (~line 396) and again after roof-pretil tagging (~line 431): a reader between the two sees pre-`on_roof` data.

**Files:**
- Modify: `packages/klave_engine/detection/suite.py:140-148`
- Modify: `packages/klave_engine/pipeline.py` (the two `write_json(processed / "detections.json", ...)` sites)
- Test: `tests/test_detector_config.py` (create), plus one pipeline-artifact assertion in whichever existing test drives `run_full_pipeline` on the demo fixture (find it: `grep -rln "run_full_pipeline" tests/`)

**Interfaces:**
- Consumes: `DetectorSuiteConfig.preset_for_units(units, extent)` (`suite.py:74`), `read_json`.
- Produces: `load_detector_config(path, units, extent)` — same signature; an external file now OVERLAYS the unit-scaled preset (file fields win, unset fields keep the scaled preset). `detections.json` written exactly once per run.

- [x] **Step 1: Write the failing test**

```python
"""Un config externo ajusta umbrales; no apaga el escalado por unidades."""

from klave_engine.common.io import write_json
from klave_engine.detection.suite import DetectorSuiteConfig, load_detector_config
from klave_engine.dxf.units import DrawingUnits


def test_config_externo_overlaya_el_preset_escalado(tmp_path):
    path = tmp_path / "detectors.json"
    write_json(path, {"wall": {"min_length": 9.99}})
    units = DrawingUnits(unit="m", source="test", confidence=0.9)
    preset = DetectorSuiteConfig.preset_for_units(units, None)
    loaded = load_detector_config(path, units, None)
    # El campo del archivo manda…
    assert loaded.wall.min_length == 9.99
    # …y todo lo demás conserva el preset escalado, no el default crudo.
    assert loaded.slab.min_area == preset.slab.min_area
    assert loaded.grid.min_relative_length == preset.grid.min_relative_length
```

If `DrawingUnits` has a different constructor (check `dxf/units.py`), mirror how `tests/test_grid.py` or the suite tests build one; if `write_json` lives elsewhere, use `json.dump`.

- [x] **Step 2: Run it, expect failure**

`uv run pytest tests/test_detector_config.py -q` — FAIL: `loaded.slab.min_area == 10000.0` (raw default), not the preset value.

- [x] **Step 3: Implement**

```python
def load_detector_config(
    path: Path | None, units: DrawingUnits | None = None, extent: BBox | None = None
) -> DetectorSuiteConfig:
    base = (
        DetectorSuiteConfig.preset_for_units(units, extent)
        if units is not None
        else DetectorSuiteConfig()
    )
    if path is not None and path.exists():
        # El archivo ajusta campos sueltos; el escalado por unidades del
        # resto sigue vivo — un config externo nunca apaga los presets.
        overrides = read_json(path)
        data = base.model_dump()
        for section, fields in overrides.items():
            if isinstance(fields, dict) and section in data:
                data[section].update(fields)
            else:
                data[section] = fields
        return DetectorSuiteConfig.model_validate(data)
    return base
```

- [x] **Step 4: Single write of `detections.json`** — in `pipeline.py`, delete the first `write_json(processed / "detections.json", ...)` (pre-segmentation) and make the post-roof-tagging site unconditional (write whether or not `tagged`), keeping write order before anything that reads the file. Verify with `grep -n 'detections.json' packages/klave_engine/pipeline.py` → exactly one write site.

- [x] **Step 5: Tests + gold**

`uv run pytest tests/test_detector_config.py tests/ -q -k "pipeline or demo"` → PASS. `make eval-gold` → PASS unchanged.

- [x] **Step 6: Commit**

```bash
git add -A packages/klave_engine tests/test_detector_config.py
git commit -m "fix(detección): el config externo overlaya el preset escalado, y detections.json se escribe una sola vez (E9)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: El parser deja de perder identidad en silencio (E7)

Three parser losses: depth-2 nesting cut with no warning (`parser.py:167` — `if depth >= 2 ... return`), nested INSERTs recursed but never normalized so their block name/ATTRIBs vanish (`parser.py:191-193`), and ATTDEF never read anywhere. The multidiscipline prefab index (S2) needs all three.

**Files:**
- Modify: `packages/klave_engine/dxf/parser.py` (`_explode_insert`)
- Test: `tests/test_explosion_descripciones.py` (append)

**Interfaces:**
- Consumes: `normalize_entity`, `ParseWarning`, existing `_ExplosionBudget`.
- Produces: (a) one `ParseWarning(warning_type="block_nesting_truncated")` per file when depth ≥ 2 cuts geometry; (b) nested INSERTs are normalized before recursion (they appear as `insert` entities with `block_name`, `from_block`, `parent_insert` — so `block_summary.json` counts nested symbols); (c) `ParsedDrawing.block_attdefs: dict[str, list[str]]` — block name → ATTDEF tags, read from `doc.blocks` in `parse_file`, persisted into `parse_summary.json` for S2.

- [x] **Step 1: Write the failing tests**

```python
def test_insert_anidado_conserva_su_identidad(tmp_path):
    doc = ezdxf.new("R2010")
    inner = doc.blocks.new(name="SIMBOLO-WC")
    inner.add_line((0, 0), (1, 0))
    outer = doc.blocks.new(name="BANO-TIPO")
    outer.add_blockref("SIMBOLO-WC", (2, 2))
    doc.modelspace().add_blockref("BANO-TIPO", (10, 10))
    path = tmp_path / "anidado.dxf"
    doc.saveas(path)

    drawing = DxfParser().parse_file(path)
    inserts = [e for e in drawing.entities if e.entity_type.value == "insert"]
    names = sorted(e.block_name for e in inserts if e.block_name)
    # El INSERT anidado existe como entidad con su nombre — antes se perdía.
    assert names == ["BANO-TIPO", "SIMBOLO-WC"]
    nested = next(e for e in inserts if e.block_name == "SIMBOLO-WC")
    assert (nested.properties or {}).get("parent_insert")


def test_corte_de_profundidad_avisa(tmp_path):
    doc = ezdxf.new("R2010")
    n3 = doc.blocks.new(name="NIVEL3")
    n3.add_line((0, 0), (1, 0))
    n2 = doc.blocks.new(name="NIVEL2")
    n2.add_blockref("NIVEL3", (0, 0))
    n1 = doc.blocks.new(name="NIVEL1")
    n1.add_blockref("NIVEL2", (0, 0))
    doc.modelspace().add_blockref("NIVEL1", (0, 0))
    path = tmp_path / "profundo.dxf"
    doc.saveas(path)

    drawing = DxfParser().parse_file(path)
    assert any(w.warning_type == "block_nesting_truncated" for w in drawing.warnings)


def test_attdef_se_lee_del_bloque(tmp_path):
    doc = ezdxf.new("R2010")
    block = doc.blocks.new(name="NOMENCLATURA-V")
    block.add_attdef("CLAVE", (0, 0), dxfattribs={"height": 0.2})
    doc.modelspace().add_blockref("NOMENCLATURA-V", (0, 0))
    path = tmp_path / "attdef.dxf"
    doc.saveas(path)

    drawing = DxfParser().parse_file(path)
    assert drawing.block_attdefs.get("NOMENCLATURA-V") == ["CLAVE"]
```

- [x] **Step 2: Run, expect three failures** (`names == ["BANO-TIPO"]`; no warning; `AttributeError: block_attdefs`).

- [x] **Step 3: Implement**

In `_explode_insert`: at the depth cut, set a flag on the budget (`budget.nesting_truncated = True`) instead of bare `return`; after the modelspace loop in `parse_file`, append the warning once if set (mirror the existing `block_explosion_capped` warning block). At the child-INSERT branch (`parser.py:191-193`), normalize the child before recursing — reuse the exact normalization block used for non-INSERT children (`normalize_entity` → layer-0 adoption → `raw_handle`/`block_name`/`from_block`/`parent_insert`/evidence note → append + budget count), then recurse. For ATTDEF: add `block_attdefs: dict[str, list[str]] = Field(default_factory=dict)` to `ParsedDrawing` (`dxf/entities.py` or wherever it's declared — `grep -n "class ParsedDrawing"`), and in `parse_file`'s BLOCKS walk (`parser.py:74`) collect `[a.dxf.tag for a in block.query("ATTDEF")]` per non-anonymous block; write it into `parse_summary.json` where the parser summary is assembled (`pipeline.py:152-153` area).

- [x] **Step 4: Tests + gold** — `uv run pytest tests/test_explosion_descripciones.py -q` PASS; `make eval-gold` PASS with **identical counts** (gold fixtures have no nested inserts; if any count moves, stop and investigate). Also `uv run pytest tests/test_levantamiento.py tests/test_simbolos_no_suman.py -q` — the nested-insert change adds insert entities that inventory counts; if a levantamiento test moves, the new count is the *correct* one — verify by hand, adjust the test's expectation only with the reasoning written in the test.

- [x] **Step 5: Commit**

```bash
git add packages/klave_engine/dxf tests/test_explosion_descripciones.py
git commit -m "fix(dxf): el INSERT anidado conserva nombre y atributos, el corte de profundidad avisa, y ATTDEF se lee (E7)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: La asignación por título tiene tope de distancia (E8)

`views.py:405-415` assigns every detection to the nearest title anchor with no cap — a detection far from every title still lands in some view. Give the Voronoi a radius: beyond it, the detection goes to a synthetic excluded region (the frames path already has `outside_frames`; the anchor path gets `far_from_titles`).

**Files:**
- Modify: `packages/klave_engine/detection/views.py` (anchor assignment loop, ~line 405; region construction above it)
- Test: `tests/test_view_assignment.py` (create; if a views test file already exists — `grep -rln "segment_views" tests/` — append there instead)

**Interfaces:**
- Consumes: `ViewRegion`, `bbox_center`; the anchor spacing already computable from `regions`.
- Produces: unchanged `segment_views` signature; new module constant `ANCHOR_ASSIGN_FACTOR = 1.5` — the cap is `1.5 × the median nearest-neighbor distance between anchors` (with a single anchor pair, the pair distance; with one anchor, no cap — one-view drawings keep today's behavior). Detections beyond the cap join a `far_from_titles` region with `ViewKind.excluded`.

- [x] **Step 1: Failing test** — build (with plain `Detection`/anchor structs the way existing views tests do; read the closest existing test for the construction pattern) two anchors 50 apart, one detection at 10 from anchor A (assigned to A) and one at 400 from both (must land in `far_from_titles`, kind excluded, never in A or B). Assert both.

- [x] **Step 2: Run, expect failure** (far detection assigned to nearest anchor today).

- [x] **Step 3: Implement** — compute the cap once from anchor pairwise nearest distances; in the assignment loop, if `sqrt(best_d2) > cap`, assign to the lazily-created `far_from_titles` region instead. Excluded regions already exist in the model — mirror how `outside_frames` is built in `_segment_by_frames`.

- [x] **Step 4: Tests + gold** — new test PASS; `uv run pytest tests/ -q -k "view or vista"` PASS; `make eval-gold` PASS **unchanged** (prueba-1's detections all sit near their four anchors; if anything moves, the cap is too tight — investigate, don't recapture).

- [x] **Step 5: Commit**

```bash
git add packages/klave_engine/detection/views.py tests/
git commit -m "fix(detección): la asignación por título tiene tope — lo lejano de todo título queda excluido, no adoptado (E8)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: La losa sin tipo se cobra como lo que es (E5) — recaptura declarada

`catalog.py:327-338` routes `family in [None, "sin_tipo", "losa"]` into EST-003 (losa reticular): an undeclared slab gets a reticular concept and phase. Honesty fix: EST-003 keeps only `["reticular"]`; a new manual-less concept **EST-015 «Losa sin sistema declarado»** (M2, no matrix ⇒ unpriced by A9, `SUPERSTRUCTURE_SUM`) takes `[None, "sin_tipo", "losa"]`, with an assumption string telling the user to declare the system or map the concept. Also scope the pipeline's blanket outline-drop (`pipeline.py:340-358`) **per frame** instead of per file: an outline slab is dropped only when its bbox center falls in a frame that produced panels (frameless files keep per-file behavior — gold's prueba-1 produces no frames, so its 6 dropped outlines stay dropped).

**Files:**
- Modify: `packages/klave_engine/costing/catalog.py` (EST-003 filter; new EST-015 Concept after EST-012)
- Modify: `packages/klave_engine/costing/catalog_store.py` (seed row for EST-015, no matrix — mirror how CIM-010 ships unpriced; bump the catalog schema version following the v13/v14 convention: replace only seeds still equal to the previous version, keep edited ones)
- Modify: `packages/klave_engine/pipeline.py:340-358` (per-frame outline drop)
- Test: `tests/test_by_view.py` or `tests/test_derivadas.py` (whichever already builds catalog+detections — check both; append)

**Interfaces:**
- Consumes: `Concept`, `QuantityRule`, `ViewScope`, `rule_matches` (`boq.py:45`).
- Produces: EST-015 in the default catalog; EST-003's `property_filter={"family": ["reticular"]}`.

- [x] **Step 1: Failing test** — a `slab_region` detection with `family=None` and `estimated_area=20.0` runs through boq generation: assert EST-015 line exists with quantity 20.0 and `unpriced=True`, and EST-003 has no line (or quantity 0 → no line). Mirror the construction pattern of the nearest existing boq test.

- [x] **Step 2: Run, expect failure** (area lands in EST-003).

- [x] **Step 3: Implement** the catalog change + EST-015 + per-frame drop. Per-frame drop sketch: build `panel_frames = {(source, frame_id_of(panel_center))}`, drop an outline only when `(source, frame_id_of(outline_center))` is in it; when a file has panels but no frames, keep today's whole-file drop.

- [x] **Step 4: Gold — expected to move, recapture declaring it.** Run `make eval-gold`: demo EST-003 120000 and torre EST-003 36 (family-less regions) migrate to EST-015. Verify prueba-1's declared families stay put and the *totals* migrate 1:1 (nothing lost, only renamed). Then `uv run python -m klave_engine.evals.gold money` if unpriced sets changed, and recapture the detection/quantity entries the documented way (`gold capture … --fresh` per fixture, or the quantity-only path if one exists — read `evals/gold.py` `capture_money`/`capture` before choosing). `make eval-gold` → PASS.

- [x] **Step 5: Full suite** — `uv run pytest -q; echo $?` → 0.

- [x] **Step 6: Commit (declaring the recapture)**

```bash
git add -A packages/klave_engine tests evals/gold
git commit -m "feat(costing): la losa sin sistema declarado se cobra como lo que es — EST-015 sin precio, no reticular por default (E5; gold recapturado: el área migra de EST-003 a EST-015)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: El fallback de columnas suma niveles en vez de quedarse con el más poblado (E6) — medir primero

With declared story heights, `COLUMN_VOLUME` already does per-planta × height (`boq.py:376-391`). Without them, `canonical = max(by_view.values(), key=len)` (`boq.py:391-392`) keeps one planta and **discards** the rest. The correct fallback mirrors the heights path: sum `_column_volume(view_dets, assumed_height)` over **superstructure** plan views (a PB castillo and a PA castillo are different physical storeys). Also E6b: `FOUNDATION_ONLY` falling back to all plan views (`boq.py:394-401`) already carries its honest note — add a boq **warning** so it surfaces in the report, not only in the line note.

**Files:**
- Modify: `packages/klave_engine/costing/boq.py:391-392` (fallback), `:394-401` (warning)
- Test: `tests/test_by_view.py` (append)

**Interfaces:**
- Consumes: `_column_volume`, `segmentation.superstructure_views()`, `per_view`.
- Produces: fallback result = sum over superstructure views, each with the assumed height, notes saying «N plantas × altura supuesta H m (sin niveles declarados)»; `by_view` split kept.

- [x] **Step 1: Characterize** — before changing anything, run `make eval-gold` and confirm which fixtures exercise the fallback: prueba-1 declares npt_levels (heights path), demo/torre are unsegmented (`plan_views 0` → `by_view` empty → `default=[]` path → `segmentation.total_height()`). Determine by adding a temporary print or reading `_column_volume` callers — if NO gold fixture hits the multi-view-no-heights fallback, gold cannot fence this change; say so in the commit and rely on the new test.

- [x] **Step 2: Failing test** — build a segmentation with two superstructure plan views, no heights, 3 column detections in view A and 2 in view B (mirror `tests/test_by_view.py`'s existing construction — it exists for exactly this area). Assert the resulting quantity equals the sum of both views' volumes (5 columns' worth), not `max` (3), and that notes mention both plantas.

- [x] **Step 3: Implement** the summed fallback + the FOUNDATION_ONLY warning (`boq.warnings.append("Sin planta de cimentación identificada: los conceptos de cimentación se calcularon sobre todas las plantas.")` — emitted once).

- [x] **Step 4: Tests + gold** — new test PASS, `make eval-gold` PASS (per Step 1, likely unchanged; if a fixture moves, the change is intentional only if that fixture genuinely has multiple storeys without heights — verify by hand before any recapture).

- [x] **Step 5: Commit**

```bash
git add packages/klave_engine/costing/boq.py tests/test_by_view.py
git commit -m "fix(costing): sin alturas declaradas, las plantas se suman — la vista más poblada ya no descarta a las demás (E6)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: La fragmentación de ejes — medir, luego ajustar

Post-P0 residual (auditoría §4): Marina estructural reports 685 axes (499 V / 186 H) — real axes split by gaps > the per-frame `gap_floor` (`0.02 × frame_extent ≈ 0.88 m`) emerge as several axes. Measure the actual gap distribution before touching factors.

**Files:**
- Modify (likely): `packages/klave_engine/detection/grid_detector.py` (`_merge_fragments` call sites — the per-frame `extent_dim`), maybe `GridDetectorConfig`
- Test: `tests/test_grid.py` (append a fragmented-axis-in-frame case)

- [x] **Step 1: Measure on Marina scratch** — script over `marina-acc/processed/detections.json`: group estructural `grid_line` detections by (frame of center, orientation, coordinate rounded to 0.2 m); report cluster sizes and the gaps between consecutive members' spans. This tells you the real bubble/label gap size (expected ~1–3 m at 1:50).

- [x] **Step 2: Failing test** — in the mosaic fixture, draw one axis as three collinear fragments with 1.5 m gaps inside a frame (mirror the existing `test_fragments_merge_into_labeled_axes` geometry, scaled into the 40×30 frame) and assert it merges into ONE axis with `fragment_count == 3`.

- [x] **Step 3: Implement** guided by Step 1's numbers — the expected fix: inside a frame, the merge `gap_floor` uses the measured bubble scale, e.g. `merge_gap_extent_factor` applied to the frame's grid-span (consistent with the threshold reference from P0) with a floor of the measured gap p95; keep the no-frame path untouched. Do NOT loosen `collinear_tolerance_factor` (cross-axis fusion is the failure mode the mosaic test's last assertion guards).

- [x] **Step 4: Verify all three fences** — `uv run pytest tests/test_grid.py -q` PASS · `make eval-gold` PASS unchanged · re-run the Marina scratch pipeline and assert: estructural axes **drop substantially** (target: ≤ 300 from 685) while `sparse_grid` stays 0, `column_tag_without_grid` stays ≤ 2, and anchored columns do not decrease (≥ 172). Report the measured numbers.

- [x] **Step 5: Commit**

```bash
git add packages/klave_engine/detection/grid_detector.py tests/test_grid.py
git commit -m "fix(detección): los fragmentos de un eje se funden dentro del marco — la fragmentación inflaba el conteo sin mover el anclaje

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Cierre — suite completa, gold, Marina, y la nota en la auditoría

- [x] **Step 1:** `uv run pytest -q; echo "exit: $?"` → 0. `make eval-gold` → PASS.
- [x] **Step 2:** Marina scratch acceptance (the corrected criterion from P0): `sparse_grid == 0`, `column_tag_without_grid ≤ 2`, 0 zapatas fantasma, riesgos < 120, plus Task 6's axis-count target.
- [x] **Step 3:** Append a dated «P1 cerrado» paragraph to `docs/auditoria-motor.md` §4 with the measured axis count and any E5 gold migration numbers; tick this plan's checkboxes.
- [x] **Step 4:** Commit docs, then merge per the finishing-a-development-branch skill (verify suite on the merged result, delete the branch).

---

## Out of scope

- The multidiscipline spine (S1–S5) — next plan, right after this one lands.
- Anything in the per-discipline suites spec.
- Panel-vs-outline dedup beyond the per-frame scoping (full polygon-overlap dedup waits for the registry work, where slab reading gets touched anyway).
