# Motor P0 — Reconexión del plano · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the four P0 detection/costing defects from the engine audit — grid detected per frame, unpriced plantilla emitted (restoring the fill subtraction), gold money fence recaptured, non-structural sheets excluded, and symbol-block linework no longer double-counted.

**Architecture:** Surgical fixes inside the existing per-file detector pipeline (`packages/klave_engine/`). No new modules except one helper function; no new dependencies. Every task that can move a quantity ends by running the gold set, and any *intentional* quantity/money change recaptures gold **declaring it in the commit message** (house rule).

**Tech Stack:** Python 3 via `uv`, pydantic models, ezdxf (tests build real DXF files in `tmp_path`), pytest, `make eval-gold`.

**Spec:** [docs/auditoria-motor.md](../../auditoria-motor.md) — findings E1–E9 with evidence and the "prueba de corrección" each fix must pass. Shareable version: https://claude.ai/code/artifact/156ad330-7f91-4299-80db-1d8313605f9b

## Global Constraints

- Run tests as `uv run pytest tests/<file>.py -q`; **never** pipe pytest through `tail` (it hides the exit code — check `$?` or grep for `FAILED`).
- Gold eval: `make eval-gold` (exit 0 = green). Recapture money only: `uv run python -m klave_engine.evals.gold money` (optionally `--only <id>`).
- Product language is Spanish: warnings, descriptions, and user-facing copy in Spanish; follow the surrounding file's comment style (sparse, states constraints, not narration).
- Do not touch thresholds unrelated to the task; the gold set is the fence. If a task's gold run shows an **unintended** diff, stop and investigate — never recapture to make a run pass.
- No new pip dependencies.
- Commit after each task with the repo's Spanish conventional style (`fix(detección): …`, `feat(costing): …`), ending with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: La plantilla sin matriz se emite sin precio (y el relleno vuelve a restarla)

Fixes E4. `apply_formwork` currently **drops** a computed plantilla/cimbra line when the concept has no APU (`formwork.py:320–329`), violating the A9 doctrine ("unpriced lines stay visible and say so"). Since seed prices were removed (`49bd10f`), CIM-003 always lacks an APU → the line vanishes → `apply_cimentacion_earthmoving` (which runs **after** `apply_formwork`: `report.py:301` then `:305`) cannot subtract the plantilla from the fill, so CIM-004 overshoots by exactly plantilla-area × 0.05 m.

**Files:**
- Modify: `packages/klave_engine/costing/formwork.py:314-349` (`apply_formwork`)
- Test: `tests/test_formwork.py`

**Interfaces:**
- Consumes: `Concept` (`costing/models.py:119`), `BoqLine`, `QuantityKind` (`costing/models.py`), `FormworkLine`/`FormworkReport` (`formwork.py:52,60`), `build_default_catalog(a)` (`costing/catalog.py:67`), `apply_cimentacion_earthmoving(boq, catalog, apus, assumptions)` (`costing/cimentacion.py:27`).
- Produces: `apply_formwork(boq, catalog, apus, formwork)` now appends a `BoqLine` with `unpriced=True, unit_price=0.0, amount=0.0` when the concept exists but has no APU. Signature unchanged. Task 2 relies on this line existing.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_formwork.py` (reuse the module's existing imports of `BillOfQuantities`, `BoqLine`, `CostingAssumptions`, `QuantityKind`):

```python
from klave_engine.costing.formwork import FormworkLine, FormworkReport, apply_formwork
from klave_engine.costing.catalog import build_default_catalog
from klave_engine.costing.cimentacion import apply_cimentacion_earthmoving


def test_plantilla_sin_matriz_sale_sin_precio():
    # A9: la línea sin precio queda visible y lo dice — nunca se descarta.
    a = CostingAssumptions()
    catalog = build_default_catalog(a)
    boq = BillOfQuantities(project_id="p", lines=[])
    report = FormworkReport(
        lines=[FormworkLine(concept_code="CIM-003", quantity=12.03,
                            source_detections=["f1"], notes=["área en planta"])]
    )
    added = apply_formwork(boq, catalog, apus={}, formwork=report)
    assert added == 1
    line = next(l for l in boq.lines if l.concept_code == "CIM-003")
    assert line.unpriced is True
    assert line.unit_price == 0.0 and line.amount == 0.0
    assert line.quantity == 12.03


def test_relleno_resta_la_plantilla_aunque_no_tenga_precio():
    # CIM-004 = excavación − enterrado; la plantilla enterrada (área × 0.05 m)
    # debe restarse aun cuando la línea de plantilla salga sin precio.
    a = CostingAssumptions()
    catalog = build_default_catalog(a)
    boq = BillOfQuantities(
        project_id="p",
        lines=[_line("CIM-001", 10.0, 10.0, ["e1"], description="Excavación")],
    )
    report = FormworkReport(
        lines=[FormworkLine(concept_code="CIM-003", quantity=12.0,
                            source_detections=["f1"], notes=[])]
    )
    apply_formwork(boq, catalog, apus={}, formwork=report)
    apply_cimentacion_earthmoving(boq, catalog, apus={}, assumptions=a)
    fill = next(l for l in boq.lines if l.concept_code == "CIM-004")
    # 10.0 excavados − 12.0 m² × 0.05 m de plantilla = 9.4 m³
    assert fill.quantity == 9.4
```

Note: `_line` is the existing helper at the top of `tests/test_formwork.py`; `CostingAssumptions()` constructs with defaults (verified: `costing/models.py:294`).

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_formwork.py -q`
Expected: both new tests FAIL — the first because no CIM-003 line is appended (warning path taken), the second because `fill.quantity == 10.0` (nothing subtracted).

- [x] **Step 3: Implement the minimal fix**

In `apply_formwork` (`formwork.py`), split the guard so a missing **concept** still warns and skips, but a missing **APU** emits the line unpriced. Replace the block:

```python
        concept = concepts.get(item.concept_code)
        apu = apus.get(item.concept_code)
        if concept is None or apu is None:
            what = "Plantilla" if item.concept_code == CODE_PLANTILLA else "Cimbra"
            boq.warnings.append(
                f"{what} calculada ({item.quantity:,.0f} m²) pero el catálogo no tiene el "
                f"concepto {item.concept_code} con matriz."
            )
            continue
        if item.concept_code in existing or item.quantity <= 0:
            continue
```

with:

```python
        concept = concepts.get(item.concept_code)
        apu = apus.get(item.concept_code)
        if concept is None:
            what = "Plantilla" if item.concept_code == CODE_PLANTILLA else "Cimbra"
            boq.warnings.append(
                f"{what} calculada ({item.quantity:,.0f} m²) pero el catálogo no tiene "
                f"el concepto {item.concept_code}."
            )
            continue
        if item.concept_code in existing or item.quantity <= 0:
            continue
        unit_price = apu.direct_unit_cost if apu is not None else 0.0
```

and in the `BoqLine(...)` construction just below, change
`unit_price=apu.direct_unit_cost` → `unit_price=unit_price`,
`amount=round(item.quantity * apu.direct_unit_cost, 2)` → `amount=round(item.quantity * unit_price, 2)`,
and add `unpriced=apu is None,` (mirroring `cimentacion.py:58`).

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_formwork.py tests/test_cimentacion_earthmoving.py -q`
Expected: PASS (all, including the file's pre-existing tests).

- [x] **Step 5: Gold check — quantities recover, money fence still red**

Run: `make eval-gold`
Expected: CIM-003 rows now show the engine quantity and pass; CIM-004 rows pass. The run may still FAIL overall on `Costo directo` ($0.00 vs captured money) and the unknown concepts AIR-004/CAR-001 — that is Task 2's job. Confirm no **other** row changed.

- [x] **Step 6: Commit**

```bash
git add packages/klave_engine/costing/formwork.py tests/test_formwork.py
git commit -m "fix(costing): la plantilla sin matriz se emite sin precio, y el relleno vuelve a restarla (A9)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Recapturar el fence de dinero del gold

Fixes E4b. The gold money expectations were captured when seed prices existed; since `49bd10f` the pure-engine run is deliberately unpriced, so `direct_cost` $689,042.75 / $83,098.87 can never reproduce. Decision (approved): recapture declaring the change; per-concept quantities remain the fence. This also folds AIR-004/CAR-001 into the known-concept rows.

**Files:**
- Modify: `evals/gold/*.json` (via the capture tool only — never hand-edit)

**Interfaces:**
- Consumes: Task 1 merged (quantities correct); `uv run python -m klave_engine.evals.gold money`.
- Produces: a green `make eval-gold` baseline every later task must keep green.

- [x] **Step 1: Verify the only remaining failures are money/unknown-concept rows**

Run: `make eval-gold`
Expected: every detection row and every quantity row passes; failures limited to `Costo directo` on prueba-1/torre and «Conceptos nuevos que el gold no conoce: AIR-004, CAR-001». If any quantity row fails, STOP — that is a bug, not a recapture.

- [x] **Step 2: Recapture money**

Run: `uv run python -m klave_engine.evals.gold money`
Expected: one `money → <path>` line per gold entry.

- [x] **Step 3: Verify green**

Run: `make eval-gold`
Expected: exit 0, `Overall: PASS`. Inspect the diff (`git diff evals/gold/`): `direct_cost` expectations now $0.00 (or absent), quantity rows unchanged except AIR-004/CAR-001 now present with engine quantities.

- [x] **Step 4: Commit, declaring the money change**

```bash
git add evals/gold/
git commit -m "test(gold): recaptura del fence de dinero — el motor puro sale sin precios desde 49bd10f; las cantidades siguen fenceadas por concepto (AIR-004 y CAR-001 entran al fence)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: La malla se detecta por marco, no por archivo

Fixes E1 — the dominant cause of the disconnection. `detect_grid` measures candidate lines against the **file** extent (`grid_detector.py:273`: `length < min_relative_length * extent_dim`), so on a multi-frame model-space set (Marina: 22 tiled frames) no real eje passes. Frames already exist before detectors run and `run_detectors` already receives them (`suite.py:179`); they just aren't passed one level deeper.

**Files:**
- Modify: `packages/klave_engine/detection/grid_detector.py` (config lines 50–62, `_Fragment` ~line 64, `detect_grid` lines 236–340)
- Modify: `packages/klave_engine/detection/suite.py:179` (the `detect_grid(...)` call)
- Test: `tests/test_grid.py`

**Interfaces:**
- Consumes: `SheetFrame` (`detection/frames.py:59` — fields `frame_id`, `bbox`, `source_file`, `code`, `title`, `kind`, `level_key`, `text_count`, `notes`; method `contains(point)`), `bbox_width/bbox_height/bbox_diagonal` (already imported).
- Produces: `detect_grid(entities, index, config=None, text_config=None, detection_ids=None, frames: list[SheetFrame] | None = None)` — new optional keyword-only-compatible parameter, default `None` preserves today's behavior exactly. `_Fragment` gains `frame_id: str | None = None`.

- [x] **Step 1: Write the failing characterization test**

Append to `tests/test_grid.py`:

```python
from klave_engine.detection.frames import SheetFrame


def test_ejes_por_marco_en_hoja_mosaicada(tmp_path):
    # Dos marcos de 40×30 mosaicados en model space (como el estructural de
    # Marina): los ejes miden ~26 m — la mitad del marco, pero una fracción
    # del extent del archivo. Sin marcos no pasan el umbral; con marcos, sí.
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for ox in (0.0, 60.0):  # dos plantas lado a lado
        for i in range(3):
            x = ox + 5 + i * 12
            msp.add_line((x, 2), (x, 28), dxfattribs={"layer": "EJES"})
            msp.add_text(str(i + 1), height=1.0).set_placement((x, -1 + 0))
        for j in range(2):
            y = 5 + j * 18
            msp.add_line((ox + 2, y), (ox + 38, y), dxfattribs={"layer": "EJES"})
            msp.add_text(chr(65 + j), height=1.0).set_placement((ox - 2, y))
    path = tmp_path / "mosaico.dxf"
    doc.saveas(path)

    drawing = DxfParser().parse_file(path)
    index = SpatialIndex(drawing.entities)
    frames = [
        SheetFrame(frame_id="frame_00", bbox=(0.0, 0.0, 40.0, 30.0),
                   source_file=drawing.entities[0].source_file, code="ES-000"),
        SheetFrame(frame_id="frame_01", bbox=(60.0, 0.0, 100.0, 30.0),
                   source_file=drawing.entities[0].source_file, code="ES-100"),
    ]
    config = GridDetectorConfig()  # el default 0.5 relativo: el caso real

    sin_marcos = detect_grid(drawing.entities, index, config)
    con_marcos = detect_grid(drawing.entities, index, config, frames=frames)

    def ejes(output):
        return [d for d in output.detections if d.detection_type.value == "grid_line"]

    # La caracterización del bug: contra el extent del archivo (~100 m de
    # ancho) ningún eje vertical de 26 m pasa; contra el marco, todos.
    assert len(ejes(sin_marcos)) < len(ejes(con_marcos))
    assert len(ejes(con_marcos)) == 10  # 3 verticales + 2 horizontales × 2 marcos
    # Los ejes de marcos distintos nunca se funden en uno.
    for det in ejes(con_marcos):
        x0, _, x1, _ = det.bbox
        assert x1 <= 40.5 or x0 >= 59.5
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_grid.py::test_ejes_por_marco_en_hoja_mosaicada -q`
Expected: FAIL with `TypeError: detect_grid() got an unexpected keyword argument 'frames'`.

- [x] **Step 3: Implement per-frame extents**

In `grid_detector.py`:

1. Import `SheetFrame`: `from klave_engine.detection.frames import SheetFrame` — **check for an import cycle first** (`frames.py` must not import `grid_detector`; it doesn't today). If a cycle appears, use `typing.TYPE_CHECKING` for the annotation and duck-type at runtime.
2. Add `frame_id: str | None = None` to `_Fragment`.
3. Change the signature: `def detect_grid(entities, index, config=None, text_config=None, detection_ids=None, frames: list[SheetFrame] | None = None) -> DetectorOutput:`
4. After `extent = index.extent()` (line ~247), add:

```python
    frame_list = list(frames or [])

    def _local_extent(frame_id: str | None) -> BBox:
        for f in frame_list:
            if f.frame_id == frame_id:
                return f.bbox
        return extent

    def _frame_of(start: tuple[float, float], end: tuple[float, float]) -> str | None:
        mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        for f in frame_list:
            if f.contains(mid):
                return f.frame_id
        return None
```

5. In the candidate loop (lines ~260–285): compute `frame_id = _frame_of(start, end)` and `local = _local_extent(frame_id)`; replace `bbox_width(extent)` / `bbox_height(extent)` with `bbox_width(local)` / `bbox_height(local)` for `extent_dim`; pass `frame_id=frame_id` into the `_Fragment(...)`.
6. Label radius becomes local: replace the single `label_radius = bbox_diagonal(extent) * config.label_search_radius_factor` with a helper `def _radius(frame_id): return bbox_diagonal(_local_extent(frame_id)) * config.label_search_radius_factor`, and pass `_radius(fragment.frame_id)` at the two `_nearest_label(...)` call sites (claims loop, and the post-merge axis labeling — an axis's frame is `axis.fragments[0].frame_id`).
7. Grouping (line ~320): change the key to `(fragment.source_file, fragment.axis, fragment.frame_id)` so axes never merge across frames, and inside the loop compute `extent_dim` from `_local_extent(frame_id)` of the group's key instead of the file extent.

Grid **intersections** need no change: they require an actual geometric crossing, and frames are disjoint.

In `suite.py:179`, change:
`grid = detect_grid(entities, index, config.grid, config.text_patterns, ids)` →
`grid = detect_grid(entities, index, config.grid, config.text_patterns, ids, frames=frames)`.

- [x] **Step 4: Run the grid tests**

Run: `uv run pytest tests/test_grid.py -q`
Expected: PASS — the new test and **every pre-existing test unchanged** (frameless files take the `frame_id=None` path, byte-identical behavior).

- [x] **Step 5: Gold must be untouched**

Run: `make eval-gold`
Expected: `Overall: PASS` with identical detection counts (demo/prueba-1/torre produce no frames, so nothing may move). If any count moves, the fallback path leaked — fix before committing; do NOT recapture.

- [x] **Step 6: Commit**

```bash
git add packages/klave_engine/detection/grid_detector.py packages/klave_engine/detection/suite.py tests/test_grid.py
git commit -m "fix(detección): la malla se mide contra su marco, no contra el archivo — el mosaico de hojas dejaba 6 ejes de 383 líneas (E1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Albañilería y el índice dejan de correr detectores estructurales

Fixes E3. `reads_as_structure` (`inventory.py:135`) already routes sheets, but `_DISCIPLINE_HINTS` (`inventory.py:36`) has no entry for albañilería or índice sheets, so both fall through to "unknown = structure". Measured on Marina: 26 of 64 zapatas (40%) are phantoms from `03-03_alba_iler_a…`, `04-03_2_alba_iler_a…` and `01-00_indice…`. Gotcha: uploads are slugified and the ñ is **dropped** — «albañilería» arrives as `alba_iler_a`, so the pattern must match both spellings.

**Files:**
- Modify: `packages/klave_engine/detection/inventory.py:36-47` (`_DISCIPLINE_HINTS`), `:129-132` (`NON_STRUCTURAL`)
- Test: `tests/test_levantamiento.py` if it exists (check with `ls tests/ | grep -i "levantamiento\|inventory"`), else create `tests/test_disciplinas.py`

**Interfaces:**
- Consumes: `guess_discipline(text)`, `reads_as_structure(sheet_label)` (`inventory.py:116,135`) — signatures unchanged.
- Produces: `guess_discipline` returns `"albanileria"` / `"indice"` for the new patterns; both keys added to `NON_STRUCTURAL`.

- [x] **Step 1: Write the failing test**

```python
from klave_engine.detection.inventory import guess_discipline, reads_as_structure


def test_albanileria_y_el_indice_no_son_estructura():
    # Los nombres llegan slugificados y la ñ se pierde: «albañilería» es
    # "alba_iler_a" en disco. Ambas grafías deben leerse como albañilería.
    assert guess_discipline("03-03_alba_iler_a_-_26_01_15.dwg") == "albanileria"
    assert guess_discipline("03 ALBAÑILERÍA.dwg") == "albanileria"
    assert guess_discipline("01-00_indice_l_04.dwg") == "indice"
    assert reads_as_structure("03-03_alba_iler_a_-_26_01_15.dwg") is False
    assert reads_as_structure("01-00_indice_l_04.dwg") is False
    # Lo que ya funcionaba no se mueve: estructura sigue siendo estructura y
    # un nombre desconocido sigue contando como estructura.
    assert reads_as_structure("02-02_estructural_l_04_-_26_01_15.dwg") is True
    assert reads_as_structure("Plano 1.dwg") is True
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_disciplinas.py -q` (or the chosen file)
Expected: FAIL — `guess_discipline` returns `None` for the albañilería/índice names.

- [x] **Step 3: Implement**

In `_DISCIPLINE_HINTS`, insert **before** the `("estructural", …)` entry (order matters — that pattern greedily matches `EST`):

```python
    ("albanileria", re.compile(r"ALBA[ÑN]ILER|ALBA\W?ILER", re.I)),
    ("indice", re.compile(r"\bINDICE\b|ÍNDICE|PORTADA|CAR[ÁA]TULA", re.I)),
]
```

(The slugified form becomes `"alba iler a"` after `guess_discipline`'s separator substitution, hence `ALBA\W?ILER`. `ALBA[ÑN]AL` in the sanitaria entry matches albañal, not albañilería — no conflict.)

In `NON_STRUCTURAL`, add both keys:

```python
NON_STRUCTURAL = frozenset(
    {"hidraulica", "sanitaria", "electrica", "gas", "aire", "cctv", "canceleria",
     "carpinteria", "acabados", "albanileria", "indice"}
)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_disciplinas.py tests/ -q -k "disciplin or inventory or levantamiento"`
Expected: PASS.

- [x] **Step 5: Gold check**

Run: `make eval-gold`
Expected: `Overall: PASS` unchanged — no gold fixture is named albañilería/índice.

- [x] **Step 6: Commit**

```bash
git add packages/klave_engine/detection/inventory.py tests/
git commit -m "fix(detección): albañilería y el índice se leen como levantamiento, no como estructura — el 40% de las zapatas de Marina era fantasma (E3)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: El trazo de un símbolo no suma metros ni pares de muro

Fixes E2 (scoped). The parser emits every INSERT **and** its exploded children (`parser.py:114-117, 205-207`; children carry `properties["parent_insert"]` = the insert's handle and `block_name`). Only `opening_detector.py:127-130` guards against counting both. Blanket-filtering all children would lose real content (xref-embedded arch bases and container blocks become blocks too), so the rule is: **skip a child only when its parent block is one the symbol table recognizes as a counted piece** (`familia_de_bloque`, `instalaciones_symbols.py:148` — searches block name, then layer). Applied to wall pairing, slab outlines, footing candidates, and the levantamiento run/area accumulators.

**Files:**
- Modify: `packages/klave_engine/detection/instalaciones_symbols.py` (new helper after `familia_de_bloque`, line ~160)
- Modify: `packages/klave_engine/detection/wall_detector.py:187-196` (candidates comprehension)
- Modify: `packages/klave_engine/detection/slab_detector.py` (candidate loop inside `detect_slabs`, after line ~72)
- Modify: `packages/klave_engine/detection/footing_detector.py` (candidate gate, lines ~64-123)
- Modify: `packages/klave_engine/detection/inventory.py:226-268` (line/polyline/arc and hatch accumulation branches)
- Test: `tests/test_simbolos_no_suman.py` (new)

**Interfaces:**
- Consumes: `familia_de_bloque(block_name, layer)` (`instalaciones_symbols.py:148`), `NormalizedEntity.properties["parent_insert"]` / `.block_name` (`parser.py:205-207`).
- Produces: `es_trazo_de_simbolo(entity: NormalizedEntity) -> bool` in `instalaciones_symbols.py` — True iff the entity is exploded linework of a symbol-table block. All four consumers call it; openings keep their existing broader filter.

- [x] **Step 1: Write the failing test**

Create `tests/test_simbolos_no_suman.py`:

```python
"""El linework interno de un bloque que la tabla reconoce como mueble ya se
contó como pieza: no debe sumar metros de corrida ni parearse como muro."""

import ezdxf
from klave_engine.detection.instalaciones_symbols import es_trazo_de_simbolo
from klave_engine.detection.inventory import build_inventory
from klave_engine.detection.wall_detector import WallDetectorConfig, detect_walls
from klave_engine.dxf.parser import DxfParser
from klave_engine.geometry.spatial_index import SpatialIndex


def _parse(tmp_path, build):
    doc = ezdxf.new("R2010")
    build(doc)
    path = tmp_path / "plano.dxf"
    doc.saveas(path)
    return DxfParser().parse_file(path)


def test_trazo_de_inodoro_no_suma_corrida(tmp_path):
    def build(doc):
        block = doc.blocks.new(name="INODORO")
        # El bloque dibuja 2 m de línea sobre la capa del sistema.
        block.add_line((0, 0), (2, 0), dxfattribs={"layer": "00-SANITARIA"})
        msp = doc.modelspace()
        msp.add_blockref("INODORO", (10, 10), dxfattribs={"layer": "MUEBLES"})
        # La corrida real de la hoja: 5 m directos.
        msp.add_lwpolyline([(0, 0), (5, 0)], dxfattribs={"layer": "00-SANITARIA"})

    drawing = _parse(tmp_path, build)
    child = next(e for e in drawing.entities
                 if (e.properties or {}).get("parent_insert"))
    assert es_trazo_de_simbolo(child) is True
    inventory = build_inventory(drawing.entities, None, [])
    runs = {r.layer: r for s in inventory.sheets for r in s.runs}
    assert abs(runs["00-SANITARIA"].length_du - 5.0) < 1e-6


def test_trazo_de_inodoro_no_parea_como_muro(tmp_path):
    def build(doc):
        block = doc.blocks.new(name="INODORO")
        block.add_line((0, 0), (3, 0), dxfattribs={"layer": "MURO"})
        block.add_line((0, 0.15), (3, 0.15), dxfattribs={"layer": "MURO"})
        msp = doc.modelspace()
        msp.add_blockref("INODORO", (20, 20))
        # Un muro real, directo.
        msp.add_line((0, 0), (4, 0), dxfattribs={"layer": "MURO"})
        msp.add_line((0, 0.15), (4, 0.15), dxfattribs={"layer": "MURO"})

    drawing = _parse(tmp_path, build)
    config = WallDetectorConfig(min_length=1.0, min_thickness=0.05, max_thickness=0.5)
    output = detect_walls(drawing.entities, SpatialIndex(drawing.entities), config)
    walls = [d for d in output.detections if d.detection_type.value == "wall"]
    assert len(walls) == 1
```

Verified signatures: `build_inventory(entities, units=None, frames=None, min_run_m=1.0, sheet_names=None, min_area_m2=0.25)` (`inventory.py:164`) — the `(entities, None, [])` call is valid; `WallDetectorConfig` carries `min_length`, `min_thickness`, `max_thickness` (defaults 0.0 = disabled until units are known, hence setting them explicitly here).

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_simbolos_no_suman.py -q`
Expected: FAIL — `ImportError: cannot import name 'es_trazo_de_simbolo'`.

- [x] **Step 3: Implement the helper**

Append to `instalaciones_symbols.py` (after `familia_de_bloque`):

```python
def es_trazo_de_simbolo(entity) -> bool:
    """Linework que salió de reventar un bloque que la tabla reconoce como
    mueble o salida: la pieza ya se contó por su nombre, así que sus trazos
    no suman metros, áreas ni pares de muro. Un bloque que la tabla no
    reconoce (un xref, un contenedor) conserva su geometría contable."""
    props = getattr(entity, "properties", None) or {}
    if not props.get("parent_insert"):
        return False
    return familia_de_bloque(
        getattr(entity, "block_name", "") or "", getattr(entity, "layer", "") or ""
    ) is not None
```

- [x] **Step 4: Wire the four consumers**

1. `wall_detector.py` candidates comprehension (~line 187): add the clause `and not es_trazo_de_simbolo(e)` after the `layer_matches` exclusion. Import at top: `from klave_engine.detection.instalaciones_symbols import es_trazo_de_simbolo`.
2. `slab_detector.py`: at the top of the per-entity candidate loop in `detect_slabs`, add `if es_trazo_de_simbolo(entity): continue` (same import).
3. `footing_detector.py`: same guard at the top of its candidate gate loop (the one applying `avoid_layer_hints` and the area window, ~lines 64-123).
4. `inventory.py`: in `build_inventory`'s accumulation loop, at the start of the `elif entity.entity_type in (EntityType.line, EntityType.polyline, EntityType.arc):` branch (~line 226) and the hatch branch (~line 255), add `if es_trazo_de_simbolo(entity): continue`. The `insert` branch stays untouched — blocks keep being counted by name.

Check for an import cycle: `inventory.py` already imports from `instalaciones_symbols` — fine. If any detector import cycles, move the helper's import inside the function.

- [x] **Step 5: Run the new tests and the neighboring suites**

Run: `uv run pytest tests/test_simbolos_no_suman.py tests/test_grid.py tests/ -q -k "wall or muro or slab or losa or footing or zapata or inventory or levantamiento"`
Expected: PASS.

- [x] **Step 6: Gold must be untouched**

Run: `make eval-gold`
Expected: `Overall: PASS`, all counts identical (gold fixtures draw walls/slabs/footings as direct entities, and PRUEBA-1's symbol blocks were never legitimate structural sources). Any moved count means the rule over-matched — investigate `familia_de_bloque` hits before committing; do NOT recapture.

- [x] **Step 7: Commit**

```bash
git add packages/klave_engine/detection/instalaciones_symbols.py packages/klave_engine/detection/wall_detector.py packages/klave_engine/detection/slab_detector.py packages/klave_engine/detection/footing_detector.py packages/klave_engine/detection/inventory.py tests/test_simbolos_no_suman.py
git commit -m "fix(detección): el trazo interno de un símbolo reconocido no suma metros, áreas ni muros — la pieza ya se contó por su nombre (E2)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Aceptación sobre Marina y suite completa

The audit's «prueba de corrección», measured on the real drawing set. Never reprocess the user's project in `data/uploads/` — copy to scratch (house rule).

**Files:**
- No source changes. Scratch dir only.

**Interfaces:**
- Consumes: everything merged from Tasks 1–5; `run_full_pipeline` (`packages/klave_engine/pipeline.py:197`).

- [x] **Step 1: Reprocess Marina in scratch**

```bash
SCRATCH=/private/tmp/claude-501/-Users-tinkertailorr-KlaveProjects-klave-engine/56a0d155-14ee-46da-a2d0-a46e441751d4/scratchpad
mkdir -p "$SCRATCH/marina-acc"
cp -R data/uploads/marina_lote_04_completo_887d5624/drawings "$SCRATCH/marina-acc/"
uv run python -c "
from pathlib import Path
from klave_engine.pipeline import run_full_pipeline
run_full_pipeline(Path('$SCRATCH/marina-acc'))
"
```

(Signature verified: `run_full_pipeline(project_root: Path, ...)`, every other parameter optional — `pipeline.py:197`.) Runtime ≈ 1.5 min. Artifacts land in `$SCRATCH/marina-acc/processed/` (no `runs/` subdir on this path).

- [x] **Step 2: Assert the audit's acceptance numbers**

```bash
uv run python - "$SCRATCH/marina-acc/processed" << 'EOF'
import json, sys
from collections import Counter
from pathlib import Path

processed = Path(sys.argv[1])
dets = json.load(open(processed / "detections.json"))
src = lambda d: (d.get("evidence") or {}).get("source", "")

grid_est = [d for d in dets if d["detection_type"] == "grid_line" and "estructural" in src(d)]
cols = [d for d in dets if d["detection_type"] == "column_tag"]
anchored = [c for c in cols if (c.get("properties") or {}).get("has_nearby_grid")]
foot_bad = [d for d in dets if d["detection_type"] == "footing"
            and ("alba" in src(d) or "indice" in src(d))]

print(f"ejes en estructural: {len(grid_est)} (antes 6, meta >= 20)")
print(f"columnas ancladas: {len(anchored)}/{len(cols)} (antes 0/359, meta >= 60%)")
print(f"zapatas en albañilería/índice: {len(foot_bad)} (antes 26, meta 0)")

rr = json.load(open(processed / "risk_report.json"))
sparse = [f for f in rr["findings"] if f["risk_type"] == "sparse_grid"]
print(f"sparse_grid: {len(sparse)} (antes 1, meta 0)")

assert len(grid_est) >= 20
assert len(anchored) >= 0.6 * len(cols)
assert len(foot_bad) == 0
assert not sparse
print("ACEPTACIÓN: OK")
EOF
```

Expected: `ACEPTACIÓN: OK`. If a target narrowly misses (e.g. anchored at 55%), report the measured numbers honestly and investigate which frame's ejes still starve before adjusting anything — the targets come from the audit, not from what the code happens to produce.

- [x] **Step 3: Full test suite**

Run: `uv run pytest -q; echo "exit: $?"`
Expected: `exit: 0`. (Never `pytest | tail`.)

- [x] **Step 4: Final gold run and closing commit (docs only, if anything)**

Run: `make eval-gold`
Expected: `Overall: PASS`.

If the acceptance numbers differ from the audit's predictions in an interesting way, append a dated «Resultado de la corrección» note to `docs/auditoria-motor.md` with the measured before/after and commit:

```bash
git add docs/auditoria-motor.md
git commit -m "docs(auditoria): resultado medido de la reconexión sobre Marina

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Outcome (2026-08-28)

Executed on branch `motor-p0-reconexion`, all tasks complete, gold green, full
suite green. Task 6's blanket "≥60% columns anchored" target proved
mis-calibrated for a muros-y-castillos building (castillos legitimately sit
mid-wall, off the grid crossings); the corrected acceptance — `sparse_grid` 0,
`column_tag_without_grid` ≤ 2, 0 phantom zapatas, risks 163→88 — passes. Full
before/after in `docs/auditoria-motor.md` §4, including the extra grid-span
refinement and the known vertical-fragmentation residual for the P1 plan.

## Out of scope (deliberately)

- **E5–E9** (losa sin tipo → reticular, `max(by_view)`, parser depth warnings, nested-INSERT identity, ATTDEF, frame classification): P1s, next engine plan.
- **Prefab index**: depends on E2/E7 identity work; own plan after this one lands.
- **Tablero de nodos / viewer / upload preview**: frontend track — spec at `docs/superpowers/specs/2026-08-28-tablero-de-nodos-design.md`, planned separately once this plan is merged.
- Generic-block double counting beyond symbol-table hits: unmapped blocks carry no money today; revisit with the prefab index.
