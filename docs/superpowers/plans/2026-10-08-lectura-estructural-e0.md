# Lectura estructural · E0 (foundation of the model) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the structural model (values with their source, definitions per mark with structured armado, project rules from the drawing, elements = placement + definition + rules), fix the five text-reading faults found on Marina, run the drawing's own checks 1, 2, 7, 8, 10, 11 with a scorecard in Revisión, and make the steel stage compute from the structured armado.

**Architecture:** A new package `packages/klave_engine/estructura/` runs in the pipeline after the final detections are written and before costing, and writes `estructura.json` per run. `detection/schedules.py` keeps producing one `ElementSpec` per reading but parses armado with the new lossless parser and associates texts to marks with the new stack rule. Costing (`costing/steel.py`) reads elements from `estructura.json` when present and falls back to today's path for old runs. Human decisions live in `estructura_decisiones.json` beside the reviews and are re-applied on every pipeline run and recompute.

**Tech Stack:** Python 3.12+, pydantic v2, ezdxf, FastAPI, pytest, ruff, mypy · Next.js + TypeScript + Tailwind (apps/web).

**Spec:** `docs/superpowers/specs/2026-10-08-lectura-estructural-completa-design.md` (round E0, §10). Read §2 (what Marina really writes), §3 (model), §4 (checks), §5.4 (steel), §7 (reference) before starting.

## Global Constraints

- Every value carries its source; precedence `humano > cuadro > detalle > seccion_dibujada > nota > medido > regla > supuesto`, `ia` only fills (spec §3.1).
- Same-rank disagreement is never resolved silently; `ia` never fills a field whose drawing text exists but failed to parse (spec §3.1).
- Lossless parsing: every `#` or `@` in an armado text is consumed into structure or reported (spec §3.3).
- A label that owns an armado stack is a definition label (`role=cuadro`), never a placement (spec §3.5).
- No confidence number is shown or stored on new structures; uncertainty is a finding (doctrine).
- Product copy is Spanish; chat and code comments follow the surrounding file (Spanish in new `estructura/` modules).
- Rule codes never appear on client-facing documents.
- No new header buttons in the web app; new UI goes in a Revisión tab.
- `uv run pytest`, `uv run ruff check .`, `uv run mypy packages/klave_engine` pass after every task. `pytest | tail -1` hides failures: check `$?` or `grep -c FAILED`.
- Never stage the user's uncommitted files (`.env.example`, `docker-compose.prod.yml`, `docs/despliegue.md`, `apps/web/.dockerignore`): `git add` only the files a task names.
- Commit messages in the repo's Spanish style, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Any intentional change to gold quantities is recaptured and the commit says why; never "fix" a baseline to make a run pass.
- Out of E0 (do not build): anchorage/lap/weld rows, waste default change, new families' steel (pilotes, dados, muros, losa cim.) — all E1; leaders (MLEADER) association, drawn-section reading — E3; `continuidad`/`apoyos` on elements — E2; dado vs dala family disambiguation of `D-` marks — E1.

## Review Focus

1. **Old runs without `estructura.json`** — recompute, the steel stage, `GET /estructura` and the web tab must keep working (steel falls back to today's path; the API answers `{"disponible": false}`; the tab says to reprocess). Tests in Tasks 10, 12, 13.
2. **Projects with no structural sheets or no units** (instalaciones-only, unitless demo) — the model is empty or partial, never a crash; steel is skipped with a warning when meters are unknown. Tests in Tasks 9, 12.
3. **Mark normalization collisions** — `K-1` vs `K-1A` vs `K1` vs `K-15A` vs `K-15A.1` must never join each other (no prefix matching). Test in Task 8.
4. **A decision whose mark disappears after a reprocess** — reported as a warning, never applied to another mark, never a crash. Test in Task 12.
5. **Armado text nobody owns** — an armado-shaped text in a frame that no label, cuadro row, numbered note, family note or detection owns must surface as check 11, not vanish. Test in Tasks 6 and 11.

---

## File Structure

| file | responsibility |
|---|---|
| `packages/klave_engine/dxf/normalizer.py` (modify) | keep text alignment (`halign`, `valign`, `align_point`, `attachment_point`) in properties |
| `packages/klave_engine/estructura/__init__.py` | package docstring only |
| `estructura/dato.py` | `Fuente`, `PRECEDENCIA`, `Dato`, `elegir` |
| `estructura/armado.py` | `Armado` models, `parsear_armado`, canonical renders |
| `estructura/tablas.py` | generic grid-of-texts table reader |
| `estructura/notas.py` | numbered notes rejoined by section |
| `estructura/reglas.py` | `Reglas`, `TABLA_ESTANDAR`, `leer_reglas` (table + notes + declared anchorages) |
| `estructura/asociacion.py` | `ancla_texto`, stack association, rejections, unowned texts |
| `detection/schedules.py` (modify) | use the parser and the association; extend `ElementSpec`; IA rule |
| `estructura/definiciones.py` | `normalizar_marca`, `Definicion`, `construir_definiciones`, `asignar_formas` |
| `estructura/elementos.py` | `Elemento`, placements, join, resolution |
| `estructura/acero.py` | hooks, stirrup length by shape, stirrup positions, kg per element |
| `costing/steel.py` (modify) | castillos/columnas and trabes/contratrabes from elements; dalas/zapatas parsed with `parsear_armado` |
| `estructura/verificaciones.py` | checks 1, 2, 7, 8, 10, 11 |
| `estructura/modelo.py` | `Estructura`, `construir_estructura`, decisions, `resumir`, read/write |
| `pipeline.py`, `costing/recompute.py`, `costing/report.py`, `evals/gold.py` (modify) | wire the model in |
| `apps/api/routes/estructura.py` + `apps/api/main.py` | GET estructura, GET elementos, POST decisiones |
| `apps/web/lib/api.ts`, `apps/web/components/EstructuraSection.tsx`, `apps/web/app/proyecto/[id]/revision/page.tsx` | the «Lectura estructural» tab |
| `scripts/transcribir_marcas.py`, `evals/transcripcion/marina_lote_04_estructural.json` | the independent Marina transcription |
| `docs/lectura-estructural.md` | one page for the engineer: sources, checks, deciding |

---

### Task 1: Text alignment kept by the normalizer

**Files:**
- Modify: `packages/klave_engine/dxf/normalizer.py` (TEXT branch ~line 304, MTEXT branch ~line 313)
- Create: `packages/klave_engine/estructura/__init__.py`, `packages/klave_engine/estructura/asociacion.py` (only `ancla_texto` in this task)
- Test: `tests/test_estructura_asociacion.py`

**Interfaces:**
- Produces: TEXT entities carry `properties["halign"]: int`, `properties["valign"]: int`, `properties["align_point"]: tuple[float, float] | None`; MTEXT carries `properties["attachment_point"]: int`. `ancla_texto(e: NormalizedEntity) -> tuple[float, float]` in `estructura/asociacion.py`.
- The text **bbox does not change** in E0 (other detectors depend on it; a bbox change is its own gold-fenced change later).

- [ ] **Step 0: Baseline before any change.** Copy `data/uploads/marina_lote_04_estructural_d1cd5ec8/drawings` to the scratchpad, run `run_full_pipeline` there with `record_history=False, perfil_del_taller=False`, and write down the wall time and the ACE-* quantities; Task 16 compares against these numbers.

- [ ] **Step 1: Write the failing tests**

```python
def test_text_alignment_is_kept(tmp_path):
    def build(msp):
        t = msp.add_text("K-11", height=0.13)
        t.set_placement((213.343, -1.99), align=TextEntityAlignment.BOTTOM_CENTER)
        msp.add_text("8#6", height=0.10).set_placement((213.2, -1.45))
    ents = _entities(tmp_path, build)
    label = next(e for e in ents if e.text == "K-11")
    line = next(e for e in ents if e.text == "8#6")
    assert label.properties["halign"] == 1 and label.properties["align_point"] == (213.343, -1.99)
    assert ancla_texto(label) == (213.343, -1.99)
    assert line.properties["halign"] == 0 and ancla_texto(line) == (213.2, -1.45)
```

(`_entities(tmp_path, build)` = the helper from `tests/test_schedules.py`: build with ezdxf, save, `DxfParser().parse_file(path).entities`; copy it into the new test module.)

- [ ] **Step 2: Run** `uv run pytest tests/test_estructura_asociacion.py -v` → FAIL (`KeyError: 'halign'` / import error).
- [ ] **Step 3: Implement.** In the normalizer TEXT branch add `halign=int(entity.dxf.get("halign", 0))`, `valign=int(entity.dxf.get("valign", 0))`, `align_point=(x, y)` from `entity.dxf.align_point` when the entity has it, else `None`; MTEXT adds `attachment_point=int(entity.dxf.get("attachment_point", 1))`. `ancla_texto`: for TEXT with `halign != 0 or valign != 0` and an `align_point`, return it; otherwise the `insert` property; fall back to the bbox's lower-left.
- [ ] **Step 4: Run** the test → PASS; run `uv run pytest tests/test_parser.py tests/test_schedules.py -q` → still PASS.
- [ ] **Step 5: Commit** `feat(dxf): el texto conserva su alineación (halign/valign/punto de alineación); ancla_texto la usa`.

---

### Task 2: `Dato` and precedence

**Files:**
- Create: `packages/klave_engine/estructura/dato.py`
- Test: `tests/test_estructura_dato.py`

**Interfaces:**
- Produces:
  - `Fuente = Literal["humano","cuadro","detalle","seccion_dibujada","nota","medido","regla","supuesto","ia"]`
  - `PRECEDENCIA: dict[str, int] = {"humano": 8, "cuadro": 7, "detalle": 6, "seccion_dibujada": 5, "nota": 4, "medido": 3, "regla": 2, "supuesto": 1, "ia": 0}`
  - `class Dato(BaseModel)`: `valor: Any = None`, `fuente: Fuente`, `hoja: str = ""`, `texto: str = ""`, `entidades: list[str] = []`, `alternativas: list[Dato] = []`, `en_conflicto: bool = False`, `ilegible: bool = False`, `copias: int = 1`
  - `elegir(datos: list[Dato], *, preferir_hoja: str | None = None) -> Dato | None`

- [ ] **Step 1: Write the failing tests**

```python
def test_higher_source_wins_and_losers_are_kept():
    d = elegir([Dato(valor=(20, 30), fuente="ia"), Dato(valor=(15, 30), fuente="detalle", hoja="ES-400")])
    assert d.valor == (15, 30) and d.fuente == "detalle"
    assert [a.fuente for a in d.alternativas] == ["ia"] and d.en_conflicto is False

def test_same_rank_disagreement_is_a_conflict_never_silent():
    a = Dato(valor=(20, 30), fuente="detalle", hoja="ES-400")
    b = Dato(valor=(20, 40), fuente="detalle", hoja="ES-200")
    d = elegir([a, b], preferir_hoja="ES-200")
    assert d.valor == (20, 40) and d.en_conflicto is True and d.alternativas[0].valor == (20, 30)
    d2 = elegir([a, b])  # no preference: most frequent value, tie → first by hoja
    assert d2.valor == (20, 40) and d2.en_conflicto is True

def test_equal_copies_count_not_conflict():
    d = elegir([Dato(valor="EYG#3@15", fuente="detalle", hoja="ES-400"),
                Dato(valor="EYG#3@15", fuente="detalle", hoja="ES-400")])
    assert d.copias == 2 and d.en_conflicto is False

def test_unreadable_text_blocks_ia():
    d = elegir([Dato(valor=None, fuente="detalle", ilegible=True, texto="E#3@1S"),
                Dato(valor="E#2@15", fuente="ia")])
    assert d.ilegible is True and d.valor is None and d.alternativas[0].fuente == "ia"

def test_empty_is_none():
    assert elegir([]) is None
```

- [ ] **Step 2: Run** `uv run pytest tests/test_estructura_dato.py -v` → FAIL (module missing).
- [ ] **Step 3: Implement** `dato.py`. `elegir`: keep the top-rank group; inside it, group by `valor` (use `repr` of the JSON-able value as the key); if one value → winner = first, `copias` = group size; if several → prefer the group whose any member has `hoja == preferir_hoja`, else the largest group, tie → the group whose first member has the smallest `hoja`; set `en_conflicto=True`. Every other datum (same rank or lower) goes to `alternativas` (flattened, winner excluded). Return a copy, never mutate inputs.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(estructura): Dato con su fuente y la precedencia; los conflictos del mismo rango nunca se callan`.

---

### Task 3: `Armado` and the lossless parser

**Files:**
- Create: `packages/klave_engine/estructura/armado.py`
- Test: `tests/test_estructura_armado.py`

**Interfaces:**
- Produces:
  - `NUMEROS = ("2", "2.5", "3", "4", "5", "6", "7", "8", "10", "12")` (the keys of `costing.steel.BAR_KG_PER_M`; import them, don't duplicate the weights)
  - `class GrupoVarillas(BaseModel)`: `cantidad: int`, `numero: str`, `posicion: Literal["esquina","cara","lecho_sup","lecho_inf","ambos"] | None = None`
  - `class Zona(BaseModel)`: `tramo: Literal["todo","extremos","centro"]`, `separacion_m: float | None`, `longitud_m: float | None = None`
  - `Forma = Literal["perimetral","rombo","interior","grapa","liga"]`
  - `class JuegoEstribos(BaseModel)`: `tipo: Literal["estribo","grapa","liga"]`, `cantidad: int`, `numero: str`, `zonas: list[Zona] = []`, `referencia: str | None = None`, `formas: list[Forma] = []`, `formas_fuente: str | None = None`
  - `class Parrilla(BaseModel)`: `numero: str`, `separacion_m: float`, `lecho: Literal["sup","inf","unico"]`, `sentidos: Literal["ambos","x","y"] | None`
  - `class Armado(BaseModel)`: `longitudinales: list[GrupoVarillas] = []`, `estribos: list[JuegoEstribos] = []`, `parrillas: list[Parrilla] = []`, `texto_original: str = ""`, `avisos: list[str] = []`; method `vacio() -> bool`
  - `FAMILIAS_CON_PARRILLA = frozenset({"losa", "muro", "muro_concreto", "zapata", "dado", "losa_cimentacion"})`
  - `parsear_armado(textos: list[str], familia: str) -> Armado`
  - `texto_longitudinal(a: Armado) -> str`, `texto_estribos(a: Armado) -> str`, `texto_armado(a: Armado) -> str`

- [ ] **Step 1: Write the failing tests** — every Marina string, exact structure:

```python
E, G = "estribo", "grapa"

@pytest.mark.parametrize("textos,familia,long,estr", [
    (["8#8"], "columna", [(8, "8")], []),
    (["4#4+2#3"], "castillo", [(4, "4"), (2, "3")], []),
    (["8#8+4#6"], "columna", [(8, "8"), (4, "6")], []),
    (["REFUERZO 1#3"], "castillo", [(1, "3")], []),
    (["E#2@15"], "castillo", [], [(E, 1, "2", [("todo", 0.15)])]),
    (["EYG#3@15"], "castillo", [], [(E, 1, "3", [("todo", 0.15)]), (G, 1, "3", [("todo", 0.15)])]),
    (["2E#3@20"], "castillo", [], [(E, 2, "3", [("todo", 0.20)])]),
    (["2E#3EXT@10", "CENTRO@20"], "columna", [], [(E, 2, "3", [("extremos", 0.10), ("centro", 0.20)])]),
    (["4E#3EXT@10", "CENTRO@20"], "castillo", [], [(E, 4, "3", [("extremos", 0.10), ("centro", 0.20)])]),
    (["2E+1G#3EXT@10", "CENTRO@15"], "castillo", [],
     [(E, 2, "3", [("extremos", 0.10), ("centro", 0.15)]), (G, 1, "3", [("extremos", 0.10), ("centro", 0.15)])]),
    (["E#3"], "castillo", [], [(E, 1, "3", [])]),
    (["G#3@14"], "castillo", [], [(G, 1, "3", [("todo", 0.14)])]),
    (["DALA 15x30 4#3,E#2@20"], "dala", [(4, "3")], [(E, 1, "2", [("todo", 0.20)])]),
    (["4#8 + 12#6 3E#3 VER CORTE"], "pilote", [(4, "8"), (12, "6")], [(E, 3, "3", [])]),
])
def test_marina_strings(textos, familia, long, estr):
    a = parsear_armado(textos, familia)
    assert [(g.cantidad, g.numero) for g in a.longitudinales] == long
    assert [(j.tipo, j.cantidad, j.numero, [(z.tramo, z.separacion_m) for z in j.zonas]) for j in a.estribos] == estr
    assert a.avisos == []

def test_ver_corte_is_a_reference():
    a = parsear_armado(["2E#3 VER CORTE"], "pilote")
    assert a.estribos[0].referencia == "VER CORTE" and a.estribos[0].zonas == []

def test_mesh_only_where_meshes_belong():
    muro = parsear_armado(["#4@20"], "muro_concreto")
    assert [(p.numero, p.separacion_m, p.lecho, p.sentidos) for p in muro.parrillas] == [("4", 0.20, "unico", None)]
    k = parsear_armado(["#4@20"], "castillo")
    assert k.parrillas == [] and k.avisos and "#4@20" in k.avisos[0]

def test_slab_layers():
    a = parsear_armado(["LOSA MACIZA DOBLEMENTE ARMADA H=20 LS #4@20 A/S LI #4@20 A/S"], "losa")
    assert [(p.lecho, p.sentidos) for p in a.parrillas] == [("sup", "ambos"), ("inf", "ambos")]

def test_two_digit_bars():
    assert parsear_armado(["6#10+2#12"], "columna").longitudinales[1].numero == "12"

def test_nothing_lost_silently():
    a = parsear_armado(["6#4 E#3@1S"], "castillo")
    assert a.longitudinales[0].cantidad == 6 and any("@1S" in w for w in a.avisos)
    b = parsear_armado(["8#9"], "columna")  # #9 is not a Mexican bar number
    assert b.longitudinales == [] and b.avisos

@pytest.mark.parametrize("textos,familia", [(["4#5+2#4", "2E#3@15"], "castillo"),
    (["2E+1G#3EXT@10", "CENTRO@15"], "castillo"), (["EYG#3@20"], "castillo"),
    (["LS #4@20 A/S LI #4@20 A/S"], "losa"), (["4#8 + 12#6 3E#3 VER CORTE"], "pilote")])
def test_round_trip(textos, familia):
    a = parsear_armado(textos, familia)
    assert parsear_armado([texto_armado(a)], familia).model_dump(exclude={"texto_original"}) == \
        a.model_dump(exclude={"texto_original"})

def test_canonical_texts():
    a = parsear_armado(["4#5+2#4", "2E+1G#3EXT@10", "CENTRO@15"], "castillo")
    assert texto_longitudinal(a) == "4#5+2#4"
    assert texto_estribos(a) == "2E+1G#3 EXT@10 CENTRO@15"
    assert texto_estribos(parsear_armado(["EYG#3@15"], "castillo")) == "EYG#3@15"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_estructura_armado.py -v` → FAIL.
- [ ] **Step 3: Implement.** Join the texts with `" | "` (line boundary kept so a `CENTRO@` line continues the stirrup set before it), upper-case, normalize `%%%`→`%`, `Ø`→`#`, collapse spaces. Consume, in this order, recording consumed spans:
  1. Stirrup sets: `(?:(\d)\s*)?E(?:ST(?:RIBOS?)?)?(?:\s*(?:Y|\+)\s*(?:(\d)\s*)?G(?:RAPAS?)?)?\s*#\s*(NUM)` (`EYG`, `E Y G`, `nE+mG`, `E`), or a grapa alone `(?:(\d)\s*)?G(?:RAPAS?)?\s*#\s*(NUM)`; then optional `EXT\s*@\s*(\d{1,3})` and, possibly after the line separator, `CENTRO\s*@\s*(\d{1,3})` → zones; else optional `@\s*(\d{1,3})` → one `todo` zone; else optional `VER\s+CORTE|VER\s+DETALLE` → `referencia`.
  2. Meshes: `(?:(LS|L\.S\.|LECHO\s+SUP\w*)|(LI|L\.I\.|LECHO\s+INF\w*))?\s*#\s*(NUM)\s*@\s*(\d{1,3})\s*(A\s*/\s*S|A\.?S\.?|AMBOS\s+SENTIDOS)?` — accepted only if `familia in FAMILIAS_CON_PARRILLA`, else an aviso `"malla «…» en un {familia}: no se toma"`.
  3. Bar groups: `(\d{1,2})\s*(?:V|VAR|VARS|VARILLAS)?\s*#\s*(NUM)(?!\s*@)` chained by `+`.
  `NUM = (?:10|12|2\.5|[2-8])(?!\d)`; any other number after `#` → aviso. After consumption, every remaining `#` or `@` (and the 1–3 chars around it) → aviso `"sin leer: «…»"`. Section tokens (`\d+x\d+`), family words, `H=`, `REFUERZO`, commas are context and are not reported. Renders: longitudinal `"+".join(f"{c}#{n}")`; stirrups: `E`/`nE`, `EYG` when one estribo + one grapa share number and zones, `nE+mG` otherwise, then `#n`, then `@s` for a single `todo` zone or `EXT@a CENTRO@b`, or ` VER CORTE`; meshes `LS #4@20 A/S` etc.; `texto_armado` joins the three parts with a space.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(estructura): el armado como estructura — parser sin pérdida (grupos, EYG, nE+mG, zonas EXT/CENTRO en dos líneas, VER CORTE, mallas sólo donde van) y su texto canónico`.

---

### Task 4: Tables and the tabla de varillas

**Files:**
- Create: `packages/klave_engine/estructura/tablas.py`, `packages/klave_engine/estructura/reglas.py` (table part)
- Test: `tests/test_estructura_reglas.py`

**Interfaces:**
- Consumes: `Dato`, `elegir` (Task 2); `ancla_texto` (Task 1); `SheetFrame` (`detection/frames.py`).
- Produces:
  - `class Tabla(BaseModel)`: `encabezados: list[str]`, `filas: list[dict[str, str]]`, `entidades: list[str]`, `hoja: str`, `bbox: BBox`
  - `leer_tablas(textos: list[NormalizedEntity], encabezados: tuple[str, ...], ancla: str, hoja_de: Callable[[NormalizedEntity], str]) -> list[Tabla]`
  - `class FilaVarilla(BaseModel)`: `LA1, LA2, LT1, LT2, LG1, LG2, LG3, r: float | None` (cm)
  - `TABLA_ESTANDAR: dict[str, FilaVarilla]` — the PDF: `2.5: 30,30,30,40,20,10,5,4` · `3: 30,35,35,50,20,15,5,4` · `4: 35,45,50,65,30,15,5,6` · `5: 40,60,60,80,35,20,10,7` · `6: 50,70,70,100,40,25,10,9` · `8: 85,115,None,None,55,30,10,11` · `10: 130,180,None,None,65,40,15,14` · `12: 185,255,None,None,80,50,15,17`
  - `tabla_de_varillas(tablas: list[Tabla]) -> tuple[Dato, list[str]]` — the `Dato` (valor `dict[str, FilaVarilla]`, fuente `cuadro`, `copias`) or the standard table as `supuesto`; the list holds contradictions between copies.

- [ ] **Step 1: Write the failing tests** — a block `NOTAS` holding Marina's table (header row at y=0 with `VARILLA, LA1, LA2, LT1, LT2, LG1, LG2, LG3, r` at x = −1.65, −0.67, −0.04, 0.63, 1.26, 1.91, 2.55, 3.20, 3.97; the title `TABLA DE VARILLAS` above; eight rows below at pitch 0.25 with Marina's values, #8 = `85 115 115 150 55 30 10 11`, #10/#12 without LT cells), inserted twice:

```python
def test_marina_table_two_copies(tmp_path):
    dato, contradicciones = tabla_de_varillas(_tablas(tmp_path, copies=2))
    t = dato.valor
    assert dato.fuente == "cuadro" and dato.copias == 2 and contradicciones == []
    assert sorted(t, key=float) == ["2.5", "3", "4", "5", "6", "8", "10", "12"]
    assert t["8"].model_dump() == dict(LA1=85, LA2=115, LT1=115, LT2=150, LG1=55, LG2=30, LG3=10, r=11)
    assert t["10"].LT1 is None and t["12"].LA2 == 255

def test_copies_that_differ_are_reported(tmp_path):
    dato, contradicciones = tabla_de_varillas(_tablas(tmp_path, copies=2, cambio={("8", "LT1"): 120}))
    assert contradicciones and "#8" in contradicciones[0] and "LT1" in contradicciones[0]

def test_no_table_means_standard_supuesto():
    dato, _ = tabla_de_varillas([])
    assert dato.fuente == "supuesto" and dato.valor["8"].LT1 is None
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** `leer_tablas`: header = texts whose content equals each required header token, on one baseline (|Δy| ≤ 0.5 × median height) within the same `hoja`; the anchor column = texts under the `ancla` header (|Δx| ≤ half the median header spacing) going down while consecutive gaps ≤ 2.5 × row height; each other text below the header joins the nearest anchor row by y (≤ half the row pitch) and the nearest header by x (≤ half the header spacing); empty cells stay absent. Use `ancla_texto` for positions. `tabla_de_varillas` reads tables with headers `("VARILLA","LA1","LA2","LT1","LT2","LG1","LG2","LG3","r")`, anchor `VARILLA`; compares copies field by field.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(estructura): lector de tablas del plano y la tabla de varillas (copias contadas, diferencias reportadas, la estándar como supuesto)`.

---

### Task 5: Numbered notes and the rest of `Reglas`

**Files:**
- Create: `packages/klave_engine/estructura/notas.py`
- Modify: `packages/klave_engine/estructura/reglas.py`
- Test: `tests/test_estructura_reglas.py`

**Interfaces:**
- Produces:
  - `class Nota(BaseModel)`: `seccion: str`, `numero: int`, `texto: str`, `hoja: str`, `entidades: list[str]`
  - `leer_notas(textos: list[NormalizedEntity], hoja_de: Callable[[NormalizedEntity], str]) -> tuple[list[Nota], list[str]]` (notes, contradictions between copies)
  - `class Reglas(BaseModel)`: `tabla_varillas: Dato`, `recubrimiento_m: dict[str, Dato]`, `gancho_estribo: Dato` (valor `{"angulo": 135, "recto_diametros": 10}`), `gancho_grapa: Dato` (`{"angulo": 180, "recto_diametros": 10}`), `soldar_desde_numero: Dato | None`, `traslape_max_numero: Dato | None`, `primer_estribo_m: Dato | None` (with `texto` naming the families it applies to), `primer_estribo_familias: list[str]`, `anclajes_declarados_m: dict[str, Dato]`, `plantilla_espesor_m: Dato | None`, `contradicciones: list[str]`, `avisos: list[str]`
  - `RECUBRIMIENTO_SUPUESTO = {"zapata": .05, "dado": .05, "pilote": .05, "contratrabe": .05, "losa_cimentacion": .05, "columna": .05, "trabe": .04, "losa": .04, "muro_concreto": .04, "castillo": .03, "dala": .03, "cerramiento": .03}`
  - `leer_reglas(entities: list[NormalizedEntity], frames: list[SheetFrame]) -> Reglas`; `reglas_estandar() -> Reglas` (everything `supuesto`)

- [ ] **Step 1: Write the failing tests** with Marina's exact lines (left-aligned at x=0, pitch 0.22, h=0.10), section headings `NOTAS GENERALES DE ESTRUCTURA.` and `REFUERZO :`:

```python
MARINA_GENERALES = [
    "4. EL RECUBRIMIENTO MINIMO LIBRE, NO SERA MENOR QUE EL DIAMETRO DEL",
    "REFUERZO LONGITUDINAL NI MENOR A:",
    "5.0 CM EN ELEMENTOS ESTRUCTURALES DE CIMENTACION",
    "5.0 CM EN COLUMNAS, EN CASO DE USAR PAQUETES DE VARILLAS SERA 1.5",
    "VECES EL DIAMETRO DE LA BARRA MAS GRUESA.",
    "4.0 CM EN TRABES Y LOSAS",
    "3.0 A 5.0 CM EN CASTILLOS, CADENAS, DALAS Y CERRAMIENTOS",
    "5. EN TODOS LOS ELEMENTOS DE CONCRETO EL CURADO DEBERA MANTENERSE",
]
MARINA_REFUERZO = [
    "3. EN TRABES LA SEPARACION DE LOS ESTRIBOS EMPEZARÁ A PARTIR DEL PAÑO",
    "DE LOS APOYOS COLOCANDO EL PRIMER ESTRIBO A 6 CMS.",
    "4. NO SE PERMITIRA TRASLAPAR NI SOLDAR MAS DEL 50%%% DEL REFUERZO",
    "EN UNA MISMA SECCION, UNICAMENTE SE PERMITIRA TRASLAPAR VARILLA",
    "HASTA EL #6, DEL #8 Y DIAMETROS MAYORES SE SOLDARAN",
    "COMO LO INDICA LA FIG-D.",
    "7. EL ANCLAJE DE ESTRIBOS Y GRAPAS SE HARA CON UN DOBLEZ A 135° Y 180°",
    "RESPECTIVAMENTE, RESPETANDO LOS RADIOS (r) INDICADOS EN LA TABLA DE",
    "VARILLAS, SEGUIDO DE UN TRAMO RECTO DE 10Ø COMO SE INDICA EN LA",
    "FIG-B.",
]

def test_notes_rejoined_by_number(tmp_path):
    notas, _ = leer_notas(_lines(tmp_path, MARINA_REFUERZO, heading="REFUERZO :"), lambda e: "ES-001")
    n4 = next(n for n in notas if n.seccion == "REFUERZO" and n.numero == 4)
    assert n4.texto.endswith("SE SOLDARAN COMO LO INDICA LA FIG-D.")

def test_marina_rules(tmp_path):
    r = leer_reglas(_marina_notes_and_table(tmp_path), frames=[])
    cov = {k: (d.valor, d.fuente) for k, d in r.recubrimiento_m.items()}
    assert cov["zapata"] == cov["dado"] == cov["pilote"] == cov["contratrabe"] == (0.05, "nota")
    assert cov["columna"] == (0.05, "nota") and cov["trabe"] == cov["losa"] == (0.04, "nota")
    assert cov["castillo"] == cov["dala"] == cov["cerramiento"] == (0.03, "nota")
    assert cov["muro_concreto"] == (0.04, "supuesto")
    assert any("3.0 a 5.0" in a for a in r.avisos)
    assert r.traslape_max_numero.valor == "6" and r.soldar_desde_numero.valor == "8"
    assert r.primer_estribo_m.valor == 0.06 and r.primer_estribo_familias == ["trabe", "contratrabe"]
    assert r.gancho_estribo.valor == {"angulo": 135, "recto_diametros": 10} and r.gancho_estribo.fuente == "nota"
    assert r.gancho_grapa.valor == {"angulo": 180, "recto_diametros": 10}
    assert r.anclajes_declarados_m["castillo"].valor == 1.00          # «100CM ANCLAJE DE CASTILLO»
    assert r.plantilla_espesor_m.valor == 0.05                         # «PLANTILLA 5 CMS. F'C=100 KG/CM2»
    assert any("#8" in c and "suelda" in c for c in r.contradicciones)  # table lists LT for #8

def test_no_notes_means_supuestos():
    r = reglas_estandar()
    assert r.recubrimiento_m["castillo"].fuente == "supuesto" and r.soldar_desde_numero is None
```

(`_marina_notes_and_table` = the Task 4 table fixture plus both note lists, plus an MTEXT `"\\A1;100CM\\PANCLAJE DE\\P CASTILLO"` and a TEXT `"PLANTILLA 5 CMS.  F'C=100 KG/CM2"`.)

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** `leer_notas`: a numbered line matches `^(\d{1,2})[.\-)]\s+`; continuation lines are the next texts down the same left column (|Δx| ≤ 1 × height, or indented ≤ 4 × height) with gap ≤ 1.5 × height, until the next numbered line or a heading (`^[A-ZÁÉÍÓÚÑ ]+\s*[:.]$`, which also sets `seccion`). Copies (same `seccion`, `numero`, `texto`) collapse; same key with different text → contradiction. Rule patterns run over the joined note texts: cover lines `(\d+(?:\.\d)?)\s*(?:A\s*(\d+(?:\.\d)?))?\s*CM\s+EN\s+(…)` mapped by words (`CIMENTACION` → zapata, dado, pilote, contratrabe, losa_cimentacion; `COLUMNAS` → columna; `TRABES Y LOSAS` → trabe, losa; `CASTILLOS|CADENAS|DALAS|CERRAMIENTOS` → castillo, dala, cerramiento; a range takes its minimum and adds an aviso); `TRASLAPAR VARILLA\s+HASTA EL #(\d+)` and `DEL #(\d+) Y DIAMETROS MAYORES SE SOLDAR`; `PRIMER ESTRIBO A (\d+)\s*CM` with families from the words before it (`EN TRABES` → trabe, contratrabe); `DOBLEZ A (\d+)°\s*Y\s*(\d+)°` with `ESTRIBOS Y GRAPAS` order and `RECTO DE (\d+)\s*Ø`; anchorages `(\d+)\s*CM\s*ANCLAJE DE\s*(CASTILLO|COLUMNA|…)` on any text; `PLANTILLA\s+(\d+)\s*CMS?`. Then the contradiction rule: if `soldar_desde_numero` is set and the table has an `LT1`/`LT2` for any bar ≥ it → `"La tabla de varillas da traslape para #8, pero la nota dice que del #8 en adelante se suelda."`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(estructura): reglas del proyecto desde las notas numeradas y la tabla — recubrimientos por familia, ganchos, traslape hasta #6 y soldadura desde #8, primer estribo, anclajes declarados, plantilla; contradicciones a la vista`.

---

### Task 6: Stack association

**Files:**
- Modify: `packages/klave_engine/estructura/asociacion.py`
- Test: `tests/test_estructura_asociacion.py`

**Interfaces:**
- Consumes: `ancla_texto` (Task 1); `SheetFrame`; `TextPatternConfig` and `_mark_in_text` logic from `detection/schedules.py` (move `_mark_in_text`/`_MARK_RE` into `asociacion.py` as `marca_en_texto(texto, config) -> str | None` and import it back in schedules; extend `_MARK_RE` to `K|C|T|COL|CT|CTA|TB|ZC|ZCM|Z|D|P|MC|CE|CR` with an optional `.n` suffix so `K-15A.1` and `P-4` are marks).
- Produces:
  - `ARMADO_RE = re.compile(r"#\s*\d|@\s*\d|^\s*CENTRO\b|^\s*EXT\b", re.I)`
  - `class Asociacion(BaseModel)`: `etiqueta_id: str`, `marca: str`, `hoja: str`, `textos: list[str]` (top to bottom), `entidades: list[str]`, `via: Literal["pila", "fila"]`
  - `class Rechazo(BaseModel)`: `entidad_id: str`, `texto: str`, `hoja: str`, `motivo: Literal["ambigua", "otra_familia", "sin_dueno"]`, `marcas: list[str]`
  - `asociar(entities: list[NormalizedEntity], frames: list[SheetFrame], config: TextPatternConfig) -> tuple[list[Asociacion], list[Rechazo]]`

- [ ] **Step 1: Write the failing tests** with Marina's measured geometry (label h=0.13 centred; lines h=0.10 left-aligned; offsets from §2 of the spec):

```python
K11 = [("8#6", 0.134, 0.537), ("2E#3EXT@10", -0.179, 0.353), ("CENTRO@20", -0.179, 0.186)]
K12 = [("4#6+4#4", -0.109, 0.506), ("2E#3EXT@10", -0.219, 0.322), ("CENTRO@15", -0.219, 0.155)]

def test_marina_stacks_side_by_side(tmp_path):
    ents = _stacks(tmp_path, [("K-11", (0.0, 0.0), K11), ("K-12", (1.0, 0.0), K12)])
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    by = {a.marca: a.textos for a in asoc}
    assert by == {"K-11": ["8#6", "2E#3EXT@10", "CENTRO@20"], "K-12": ["4#6+4#4", "2E#3EXT@10", "CENTRO@15"]}
    assert all(a.via == "pila" for a in asoc) and rech == []

def test_stack_inside_a_block(tmp_path):
    ents = _stacks(tmp_path, [("K-11", (0.0, 0.0), K11)], as_block="EST-CASTILLOS", at=(213.3, -2.0))
    asoc, _ = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc[0].textos == ["8#6", "2E#3EXT@10", "CENTRO@20"]

def test_slab_label_never_attaches(tmp_path):
    ents = _stacks(tmp_path, [("K-12", (0.0, 0.0), K12)],
                   loose=[("LOSA MACIZA DOBLEMENTE ARMADA H=20 LS #4@20 A/S LI #4@20 A/S", 0.0, 0.8)])
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert "LOSA" not in " ".join(asoc[0].textos)
    assert all(r.motivo != "sin_dueno" for r in rech)   # a family label is the slab's, not an orphan

def test_equidistant_line_is_rejected(tmp_path):
    ents = _stacks(tmp_path, [("K-1", (0.0, 0.0), []), ("K-2", (0.0, 0.40), [])], loose=[("6#4", -0.05, 0.20)])
    asoc, rech = asociar(ents, _one_frame(ents), TextPatternConfig())
    assert asoc == [] and rech[0].motivo == "ambigua" and sorted(rech[0].marcas) == ["K-1", "K-2"]

def test_other_frame_and_orphans(tmp_path):
    ents = _stacks(tmp_path, [("K-1", (0.0, 0.0), [])], loose=[("4#3", 0.0, 0.18), ("6#4", 30.0, 0.0)])
    frames = _two_frames_split_at(ents, y=0.1)          # the label and its line in different frames
    asoc, rech = asociar(ents, frames, TextPatternConfig())
    assert asoc == [] and {r.texto for r in rech if r.motivo == "sin_dueno"} == {"4#3", "6#4"}
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Labels = textual entities whose whole content (≤ 10 chars after stripping `CASTILLO `/`COLUMNA `) is a mark. Armado lines = textual entities matching `ARMADO_RE`. Frame of an entity = the frame containing `ancla_texto` (same `source_file`); no frame → its own group. For each label, look up then down: the first line in the same frame whose vertical gap to the label (between text bands `[y, y + height]` from `ancla_texto` and `properties["height"]`) is ≤ 1.5 × label height and whose x-band overlaps the label's x-band widened by 3 × line height; continue in that direction while the next gap ≤ 1.2 × line height and the x-band overlaps the stack's. Collect `(label, direction, lines, first_gap)`. A line claimed by two labels whose first gaps differ by ≤ 10 % → `Rechazo("ambigua")` and dropped from both; otherwise it goes to the smaller gap. Lines containing a family word of another family (`LOSA|DALA|CADENA|TRABE|CONTRATRABE|MURO|ZAPATA`) are never stacked; they are not orphans either. Every remaining armado line with no owner, not a numbered note (`^\d{1,2}[.\-)]\s`), and not a family-level note → `Rechazo("sin_dueno")`. Order each stack's texts top to bottom.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(estructura): asociación texto–marca por pila medida en el dibujo — exclusiva, por hoja, por familia; lo ambiguo y lo huérfano se reportan`.

---

### Task 7: `schedules.py` reads through the parser and the association (the five faults)

**Files:**
- Modify: `packages/klave_engine/detection/schedules.py`, `packages/klave_engine/pipeline.py:466-474` (pass `frames`)
- Test: `tests/test_schedules.py` (extend; update the two assertions whose stirrup strings become canonical `E#2@20`/`E#3@15`), `tests/test_sintesis.py` (add one test)

**Interfaces:**
- Consumes: `parsear_armado`, `texto_longitudinal`, `texto_estribos` (Task 3); `asociar`, `Asociacion`, `Rechazo`, `marca_en_texto` (Task 6).
- Produces (all additive on `ElementSpec`): `armado: Armado | None = None`, `hoja: str = ""`, `metodo: Literal["fila","pila","cotas","geometria","nota","ia"] = "nota"`, `campos_con_texto: list[str] = []` (subset of `["seccion","longitudinales","estribos","parrillas"]`), `entidades: list[str] = []`, `avisos: list[str] = []`. `rebar` = `texto_longitudinal(armado)` (all groups), `stirrups` = `texto_estribos(armado)`, `mesh` = rendered parrillas (only for mesh families). `ScheduleInventory` adds `rechazos: list[Rechazo] = []`. `build_schedule_inventory(..., frames: list[SheetFrame] | None = None)`; `detail_boxes` stays accepted for old callers and is derived from `frames` when given.

- [ ] **Step 1: Write the failing tests**

```python
def test_eyg_is_estribo_y_grapa_never_mesh(tmp_path):
    inv = build_schedule_inventory(_stack_entities(tmp_path, "K-4", ["6#4", "EYG#3@15"]), frames=_frame())
    k4 = inv.by_mark["K-4"]
    assert (k4.rebar, k4.stirrups, k4.mesh) == ("6#4", "EYG#3@15", None)
    assert [(j.tipo, j.numero) for j in k4.armado.estribos] == [("estribo", "3"), ("grapa", "3")]

def test_all_bar_groups_kept(tmp_path):
    inv = build_schedule_inventory(_stack_entities(tmp_path, "K-6", ["4#5+2#4", "2E#3@15"]), frames=_frame())
    assert inv.by_mark["K-6"].rebar == "4#5+2#4" and inv.by_mark["K-6"].stirrups == "2E#3@15"

def test_slab_label_is_not_k4s(tmp_path):
    inv = build_schedule_inventory(_stack_entities(tmp_path, "K-4", ["6#4", "EYG#3@15"],
        loose=[("LOSA MACIZA DOBLEMENTE ARMADA H=20 LS #4@20 A/S LI #4@20 A/S", 0.0, 0.9)]), frames=_frame())
    assert all("LOSA" not in s.source_text for s in inv.specs if s.mark == "K-4")

def test_ia_never_covers_an_unreadable_text(tmp_path):
    inv = build_schedule_inventory(_stack_entities(tmp_path, "K-4", ["6#4", "EYG#3@1S"]), frames=_frame())
    assert "estribos" in inv.by_mark["K-4"].campos_con_texto and inv.by_mark["K-4"].stirrups is None
    merge_external_specs(inv, [{"mark": "K-4", "family": "castillo", "stirrups": "EYG#2@15",
                                "source": "ia", "source_text": "IA", "confidence": 0.5}])
    assert inv.by_mark["K-4"].stirrups is None
    assert any(s.source == "ia" and s.mark == "K-4" for s in inv.specs)   # kept as a reading

def test_ia_fills_only_where_no_text(tmp_path):
    inv = build_schedule_inventory(_stack_entities(tmp_path, "K-4", ["6#4"]), frames=_frame())
    merge_external_specs(inv, [{"mark": "K-4", "family": "castillo", "stirrups": "E#2@15",
                                "source": "ia", "source_text": "IA", "confidence": 0.5}])
    assert inv.by_mark["K-4"].stirrups == "E#2@15"

def test_conflicting_readings_are_all_kept(tmp_path):
    inv = build_schedule_inventory(_two_frames_with(tmp_path, "K-5", ["6#4", "EYG#3@15"], (20, 30), (20, 40)),
                                   frames=_frames_es200_es400())
    secs = {(s.hoja, s.section_cm) for s in inv.specs if s.mark == "K-5" and s.section_cm}
    assert secs == {("ES-200", (20, 40)), ("ES-400", (20, 30))}

def test_stack_label_is_a_definition_not_a_placement(tmp_path):
    ents = _stack_entities(tmp_path, "K-11", ["8#6", "2E#3EXT@10", "CENTRO@20"])
    inv = build_schedule_inventory(ents, frames=_frame())
    label = next(e for e in ents if e.text == "K-11")
    assert label.entity_id in inv.cuadro_mark_entities
```

In `tests/test_sintesis.py`: a `column_tag` detection with `properties={"section_cm": "20x30", "spec_rebar": "4#5+2#4"}` → `firma(...)["armado"] == "4#5+2#4"`.

- [ ] **Step 2: Run** `uv run pytest tests/test_schedules.py tests/test_sintesis.py -v` → new tests FAIL.
- [ ] **Step 3: Implement.**
  - Replace `_parse_rebar` and the "bare marks next to a bare spec" loop in `_parse_annotations` with: run `asociar(entities, frames, config)`; for each `Asociacion`, one `ElementSpec(source="detalle", metodo="pila", hoja=<frame code>, armado=parsear_armado(a.textos, family), campos_con_texto=[fields whose text was present], entidades=a.entidades, avisos=armado.avisos, source_text=f"{marca} · {' / '.join(a.textos)}")`. Add each stack label's entity id to `cuadro_mark_entities` (keep today's `has_armado` path too; both feed it).
  - Table rows (`_parse_tables`) and family notes parse their joined text with `parsear_armado(..., family)`; `metodo="fila"` / `"nota"`.
  - Cotas and drawn-section readers set `metodo="cotas"` / `"geometria"` and `hoja`.
  - `_merge_fields` only fills a field from another reading of the **same `hoja`**; readings from different frames never merge (they are compared later, Task 8).
  - `merge_external_specs`: append every IA spec to `inventory.specs` (`source="ia"`, `metodo="ia"`); fill a `by_mark` field only if no drawing reading of that mark has that field in `campos_con_texto`.
  - `inventory.rechazos` = the association's rejections.
  - Pipeline: pass `frames=frames` to `build_schedule_inventory`.
- [ ] **Step 4: Run** `uv run pytest -q` → PASS (update only the two canonical-string assertions noted above; any other failure is a regression to fix, not an assertion to change).
- [ ] **Step 5: Commit** `fix(schedules): la lectura del armado sin sus cinco fallas — EYG ya no es malla, se guardan todos los grupos de varillas, una etiqueta de losa no se pega a un castillo, las lecturas de hojas distintas no se funden, la IA nunca tapa un texto que no se pudo leer; las claves de variante de esas marcas cambian (eran incorrectas)`.

---

### Task 8: Definitions per mark

**Files:**
- Create: `packages/klave_engine/estructura/definiciones.py`
- Test: `tests/test_estructura_definiciones.py`

**Interfaces:**
- Consumes: `Dato`, `elegir` (Task 2); `Armado`, `JuegoEstribos`, `GrupoVarillas` (Task 3); `ScheduleInventory`, `ElementSpec` (Task 7).
- Produces:
  - `normalizar_marca(texto: str) -> str`
  - `FUENTE_DE_LECTURA: dict[tuple[str, str], str]` mapping `(source, metodo)` → `Fuente`: `("cuadro","fila")→"cuadro"`, `("detalle","pila")→"detalle"`, `("detalle","cotas")→"detalle"`, `("detalle","geometria")→"seccion_dibujada"`, `("nota", *)→"nota"`, `("ia", *)→"ia"`
  - `class Definicion(BaseModel)`: `marca: str`, `familia: str`, `seccion_cm: Dato | None`, `longitud_m: Dato | None`, `longitudinales: Dato | None` (valor `list[GrupoVarillas]`), `estribos: Dato | None` (valor `list[JuegoEstribos]`), `parrillas: Dato | None`, `hojas: list[str]`, `avisos: list[str]`
  - `construir_definiciones(inv: ScheduleInventory) -> tuple[dict[str, Definicion], dict[str, Definicion]]` (by mark, by family)
  - `asignar_formas(estribos: list[JuegoEstribos], longitudinales: list[GrupoVarillas]) -> tuple[list[JuegoEstribos], list[str]]`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("raw,norm", [("K15A.1", "K-15A.1"), ("k-4a", "K-4A"), ("C 1", "C-1"),
    ("CTA-6", "CTA-6"), ("K-15A", "K-15A"), ("P-4", "P-4"), ("MC-1", "MC-1")])
def test_normalizar_marca(raw, norm):
    assert normalizar_marca(raw) == norm

def test_no_prefix_joins():
    marks = {normalizar_marca(m) for m in ["K-1", "K-1A", "K1", "K-15A", "K-15A.1"]}
    assert marks == {"K-1", "K-1A", "K-15A", "K-15A.1"}

def test_conflict_between_frames():
    defs, _ = construir_definiciones(_inv([_spec("K-5", "detalle", "cotas", "ES-400", section=(20, 30)),
                                           _spec("K-5", "detalle", "cotas", "ES-200", section=(20, 40))]))
    s = defs["K-5"].seccion_cm
    assert s.en_conflicto and {s.valor, s.alternativas[0].valor} == {(20, 30), (20, 40)}

def test_drawing_beats_ia_and_ia_is_kept():
    defs, _ = construir_definiciones(_inv([_spec("K-4", "detalle", "pila", "ES-400", texts=["6#4", "EYG#3@15"]),
                                           _spec("K-4", "ia", "ia", "", stirrups="EYG#2@15")]))
    e = defs["K-4"].estribos
    assert e.fuente == "detalle" and e.valor[0].numero == "3" and e.alternativas[0].fuente == "ia"

def test_unreadable_blocks_ia():
    defs, _ = construir_definiciones(_inv([_spec("K-4", "detalle", "pila", "ES-400", texts=["6#4", "EYG#3@1S"]),
                                           _spec("K-4", "ia", "ia", "", stirrups="EYG#2@15")]))
    assert defs["K-4"].estribos.ilegible and defs["K-4"].estribos.valor is None

@pytest.mark.parametrize("long,estr,formas", [
    (["8#8"], "2E#3EXT@10 CENTRO@20", [["perimetral", "rombo"]]),
    (["4#3"], "E#2@15", [["perimetral"]]),
    (["6#4"], "EYG#3@15", [["perimetral"], ["grapa"]]),
    (["4#5+2#4"], "2E#3@15", [["perimetral", "interior"]]),
    (["10#8"], "3E#3EXT@10 CENTRO@20", [["perimetral", "rombo", "interior"]]),
    (["6#8+6#6"], "4E#3EXT@10 CENTRO@20", [["perimetral", "rombo", "interior", "interior"]]),
])
def test_assumed_shapes(long, estr, formas):
    a = parsear_armado(long + [estr], "castillo")
    out, avisos = asignar_formas(a.estribos, a.longitudinales)
    assert [j.formas for j in out] == formas and all(j.formas_fuente == "supuesto" for j in out)
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** `normalizar_marca`: upper, strip, family prefix letters + `-` + the rest without spaces (`K15A.1` → `K-15A.1`), exact string afterwards. `construir_definiciones` groups `inv.specs` by normalized mark (family notes by family), builds one `Dato` per reading per field (`ilegible=True, valor=None` when the field is in `campos_con_texto` but the armado lacks it), and calls `elegir(..., preferir_hoja=None)`. Shapes rule (supuesto): per estribo set, total bars N: 1 piece → perimetral; 2 pieces → perimetral + rombo if N ≥ 8 else perimetral + interior; 3 → perimetral + rombo + interior; 4 → perimetral + rombo + interior + interior; grapa sets → `grapa` each; anything else → `formas=[]` and an aviso.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(estructura): definiciones por marca — cada campo con su fuente, conflictos entre hojas a la vista, la IA detrás del plano, formas de estribo supuestas y dichas`.

---

### Task 9: Elements (placement + definition)

**Files:**
- Create: `packages/klave_engine/estructura/elementos.py`
- Test: `tests/test_estructura_elementos.py`

**Interfaces:**
- Consumes: `Definicion` (Task 8); `Reglas` (Task 5); `Detection`; `SheetSegmentation`; `costing.referencias.element_id(detection, meters_factor)`.
- Produces:
  - `FAMILIAS_ESTRUCTURALES = ("castillo","columna","trabe","contratrabe","zapata","pilote","muro_concreto","dala","cerramiento")`
  - `class Elemento(BaseModel)`: `element_id: str`, `detection_id: str`, `marca: str`, `familia: str`, `vista: str | None`, `hoja: str`, `definicion: Literal["marca","familia","ninguna"]`, `seccion_cm: Dato | None`, `altura_m: Dato | None`, `longitud_m: Dato | None`, `longitudinales: Dato | None`, `estribos: Dato | None`, `parrillas: Dato | None`, `recubrimiento_m: Dato | None`
  - `construir_elementos(detections: list[Detection], segmentation: SheetSegmentation | None, por_marca: dict[str, Definicion], por_familia: dict[str, Definicion], reglas: Reglas, meters_factor: float | None, altura_supuesta_m: float) -> list[Elemento]`
  - `resolver(elemento: Elemento, por_marca, por_familia, reglas) -> Elemento` (re-joins definition fields; used again after decisions)

- [ ] **Step 1: Write the failing tests**

```python
def test_only_structural_plan_placements():
    seg = _seg(plan="v_pa", detail="v_det")
    dets = [_tag("K-4", "v_pa"), _tag("K-4", "v_det"), _tag("K-4", "v_pa", role="cuadro")]
    els = construir_elementos(dets, seg, _defs("K-4"), {}, reglas_estandar(), 1.0, 2.7)
    assert len(els) == 1 and els[0].vista == "v_pa"

def test_join_exact_and_family_fallback_flagged():
    els = construir_elementos([_tag("K-4", "v_pa"), _tag("K-99", "v_pa")], _seg(plan="v_pa"),
                              _defs("K-4"), {"castillo": _family_def("castillo")}, reglas_estandar(), 1.0, 2.7)
    by = {e.marca: e for e in els}
    assert by["K-4"].definicion == "marca" and by["K-99"].definicion == "familia"

def test_height_from_levels_else_supuesto():
    seg = _seg(plan="v_pa", story_heights={"v_pa": 2.9})
    e = construir_elementos([_tag("K-4", "v_pa")], seg, _defs("K-4"), {}, reglas_estandar(), 1.0, 2.7)[0]
    assert (e.altura_m.valor, e.altura_m.fuente) == (2.9, "nota")
    e2 = construir_elementos([_tag("K-4", "v_pa")], _seg(plan="v_pa"), _defs("K-4"), {}, reglas_estandar(), 1.0, 2.7)[0]
    assert (e2.altura_m.valor, e2.altura_m.fuente) == (2.7, "supuesto")

def test_cover_by_family_from_rules():
    e = construir_elementos([_tag("K-4", "v_pa")], _seg(plan="v_pa"), _defs("K-4"), {}, _reglas_marina(), 1.0, 2.7)[0]
    assert (e.recubrimiento_m.valor, e.recubrimiento_m.fuente) == (0.03, "nota")

def test_no_units_no_crash():
    assert construir_elementos([_tag("K-4", "v_pa")], _seg(plan="v_pa"), _defs("K-4"), {}, reglas_estandar(), None, 2.7)
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Placements: detections with `family in FAMILIAS_ESTRUCTURALES`, `properties.get("role") != "cuadro"`, `mark` non-empty, and (when `segmentation` exists) assigned to a view in `segmentation.structural_plan_views()`. Height for castillo/columna: `story_heights()[view]` as `Dato(fuente="nota", texto="niveles NTC/NPT")`, else `altura_supuesta_m` as `supuesto`. Beam length: `properties["estimated_span_length"] × meters_factor` as `medido` (none without units). Section: definition's `seccion_cm`, else the detection's measured `section_cm` property as `medido`. Armado fields copied from the definition `Dato`s. `recubrimiento_m` = `reglas.recubrimiento_m[familia]`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(estructura): elementos = colocación en planta + definición + reglas; sólo plantas estructurales, sin prefijos, el respaldo por familia dicho`.

---

### Task 10: Steel from the structured armado

**Files:**
- Create: `packages/klave_engine/estructura/acero.py`
- Modify: `packages/klave_engine/costing/steel.py` (`compute_steel` gains `estructura: dict | None = None`; castillos/columnas and trabes branches; dalas/zapatas parse with `parsear_armado`), `packages/klave_engine/costing/report.py:321-374` (`generate_cost_report(..., estructura: dict | None = None)` passed through)
- Test: `tests/test_estructura_acero.py`, `tests/test_steel.py` (existing must pass unchanged)

**Interfaces:**
- Consumes: `Elemento` (Task 9); `Reglas` (Task 5); `BAR_KG_PER_M` (`costing/steel.py`).
- Produces:
  - `diametro_m(numero: str) -> float` (= float(numero) / 8 × 0.0254)
  - `gancho_m(numero: str, reglas: Reglas, tipo: Literal["estribo","grapa"]) -> float` (= 2 × ROUNDUP(recto_diametros × Ø, 2 decimals))
  - `longitud_pieza_m(forma: Forma, b_m: float, h_m: float, r_m: float, numero: str, reglas: Reglas, barras: int) -> float`
  - `posiciones(longitud_m: float, zonas: list[Zona], primer_m: float | None, extremos_m: float) -> int`
  - `extremos_supuesto_m(b_m: float, h_m: float, longitud_m: float) -> float` (= max(b, h, L/6, 0.60))
  - `class AceroElemento(BaseModel)`: `kg_por_numero: dict[str, float]`, `formula: list[str]`, `supuestos: list[str]`
  - `acero_elemento(e: Elemento, reglas: Reglas, anclaje_m: float) -> AceroElemento | None` (None when section, length/height or longitudinal is missing)

- [ ] **Step 1: Write the failing tests** (values match the workbook where the method is the same):

```python
R = _reglas_marina()   # Task 5 fixture: 135° + 10Ø, cover columna 0.05, castillo 0.03

def test_hooks():
    assert gancho_m("3", R, "estribo") == pytest.approx(0.20)   # 10 × 0.009525 → 0.10, × 2
    assert gancho_m("2", R, "estribo") == pytest.approx(0.14)
    assert gancho_m("4", R, "estribo") == pytest.approx(0.26)

def test_piece_lengths_c1():
    assert longitud_pieza_m("perimetral", .45, .45, .05, "3", R, 8) == pytest.approx(1.60)   # workbook F35
    assert longitud_pieza_m("rombo", .45, .45, .05, "3", R, 8) == pytest.approx(1.18995, abs=1e-4)  # F40 1.19
    assert longitud_pieza_m("grapa", .15, .30, .03, "3", R, 6) == pytest.approx(0.29)          # (0.15−0.06)+0.20

def test_positions_laid_out():
    z = [Zona(tramo="extremos", separacion_m=.10), Zona(tramo="centro", separacion_m=.20)]
    assert extremos_supuesto_m(.45, .45, 3.10) == pytest.approx(0.60)
    assert posiciones(3.10, z, None, 0.60) == 21            # 6 + 6 at ends (first at s/2), 9 between
    assert posiciones(3.10, [Zona(tramo="todo", separacion_m=.15)], None, 0.0) == 20
    assert posiciones(4.00, [Zona(tramo="todo", separacion_m=.15)], 0.06, 0.0) == 27   # trabe: first at 6 cm each end

def test_c1_element_kg():
    e = _elemento("C-1", "columna", (45, 45), 3.10, ["8#8"], "2E#3EXT@10 CENTRO@20", cover=.05)
    a = acero_elemento(e, R, anclaje_m=0.40)
    assert a.kg_por_numero["8"] == pytest.approx(8 * 3.50 * 3.973, rel=1e-6)                  # 111.244
    assert a.kg_por_numero["3"] == pytest.approx(21 * (1.60 + 1.18995) * 0.560, rel=1e-4)     # 32.810
    assert any("rombo" in s and "supuesto" in s for s in a.supuestos)
    assert any("extremos 0.60 m" in s for s in a.supuestos)

def test_steel_stage_uses_elements_and_falls_back():
    boq, dets = _boq_with_c1()
    with_model = compute_steel(boq, dets, None, None, 1.0, 2.7, estructura=_estructura_c1())
    line = next(l for l in with_model.lines if l.concept_code == "ACE-001")
    assert line.quantity == pytest.approx((111.244 + 32.810) * 1.05, rel=1e-3)   # waste unchanged in E0
    assert any("2E#3 EXT@10 CENTRO@20" in n for n in line.notes)
    old = compute_steel(boq, dets, _old_specs(), None, 1.0, 2.7)               # no estructura: today's path
    assert old.lines and old.lines[0].concept_code == "ACE-001"
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - `posiciones`: with one `todo` zone: first at `primer_m` (or s/2), last at L − first, count = floor((L − 2·first)/s) + 1. With `extremos`+`centro`: positions from `first` every `s_ext` while ≤ `extremos_m`, mirrored from the top; centre stirrups strictly between the last bottom and the first top position at `s_c`: ceil(gap / s_c) − 1. Zone lengths stated on the definition (`Zona.longitud_m`) win over `extremos_m`.
  - `primer_m` = `reglas.primer_estribo_m` only for families in `reglas.primer_estribo_familias`, else None (→ s/2, recorded in `supuestos`).
  - `longitud_pieza_m`: perimetral 2(b−2r)+2(h−2r); rombo 2(b−2r)/√2 + 2(h−2r)/√2; interior 2(h−2r) + 2(b−2r)/3; grapa/liga (min side − 2r); plus `gancho_m` (`grapa` type for grapa/liga).
  - `acero_elemento`: longitudinal = Σ groups cantidad × (length + `anclaje_m`) × kg/m (anchorage by table is E1 — keep `SteelAssumptions.anchorage_m` and say so in `supuestos`); stirrups = Σ sets Σ formas `posiciones × longitud_pieza × kg/m`; no shapes → None and the caller reports it.
  - `compute_steel`: when `estructura` is given, for each detection in the EST-001 line (and EST-002/CIM-008 lines) find its element by `detection_id`; use `acero_elemento`; marks without a computable element keep today's default-armado path and are listed as today. Notes per mark: `"{marca}: {n} pzas × {texto_armado} sección {b}x{h} cm ({fuente})"` plus the supuestos. Without `estructura` the formulas are unchanged, but the strings may now be canonical (`EYG#3@15`, `2E#3@15`, `4#5+2#4`) which `parse_rebar`/`parse_spacing` cannot read: when either returns None on a non-empty string, read it with `parsear_armado` (prefix `E` to a bare `#n@s` stirrup string first, as old runs stored them) and take all longitudinal groups and the first estribo set — so a run between Task 7 and Task 12, or any caller without `estructura`, never silently drops an armado it used to read. Add a test: `_old_specs()` with `rebar="4#5+2#4", stirrups="2E#3@15"` yields both bar groups and the stirrups in ACE-001's notes. Dalas/zapatas: parse `spec["rebar"]`, `spec["stirrups"]`, `spec["mesh"]` with `parsear_armado` (so `4#3,E#2@20` works); formulas unchanged.
  - `generate_cost_report` passes `estructura` to `compute_steel`.
- [ ] **Step 4: Run** `uv run pytest tests/test_estructura_acero.py tests/test_steel.py tests/test_beams_costing.py tests/test_story_heights.py -v` → PASS.
- [ ] **Step 5: Commit** `feat(acero): el acero de castillos, columnas y trabes desde el armado estructurado — grupos, juegos de estribos por forma, ganchos 2×10Ø, recubrimiento por familia, estribos acomodados por zona; corridas viejas siguen por el camino de antes`.

---

### Task 11: The drawing's checks (1, 2, 7, 8, 10, 11)

**Files:**
- Create: `packages/klave_engine/estructura/verificaciones.py`
- Test: `tests/test_estructura_verificaciones.py`

**Interfaces:**
- Consumes: `Definicion`, `Elemento`, `Reglas`, `Rechazo`, `ScheduleInventory`, `Detection`, `SheetSegmentation`, entities.
- Produces:
  - `Severidad = Literal["bloquea","duda","aviso"]`
  - `class Verificacion(BaseModel)`: `id: str` (stable: sha1 of numero + marca + hoja + texto, 12 hex), `numero: int`, `severidad: Severidad`, `mensaje: str` (Spanish, no rule codes), `marcas: list[str]`, `elementos: list[str]`, `datos: list[Dato]`, `hoja: str`, `bbox: BBox | None`
  - `CRITICOS: dict[str, tuple[str, ...]]` — spec §4.1 table, E0 fields: castillo/columna `("seccion_cm","altura_m","longitudinales","estribos")`, trabe/contratrabe `("seccion_cm","longitud_m","longitudinales","estribos")`, pilote `("seccion_cm","longitud_m","longitudinales","estribos")`, zapata `("seccion_cm","parrillas")`, muro_concreto `("seccion_cm","parrillas")`, dala/cerramiento `("seccion_cm","longitudinales","estribos")`
  - `verificar(por_marca, por_familia, elementos, reglas, inv, entities, detections, segmentation) -> list[Verificacion]`

- [ ] **Step 1: Write the failing tests** — one per check, minimal inputs:

```python
def test_1_undefined_mark():
    v = _run(elementos=[_el("K-99", definicion="ninguna")])
    assert _one(v, 1).severidad == "bloquea"
    v2 = _run(elementos=[_el("K-99", definicion="familia")])
    assert _one(v2, 1).severidad == "duda" and "nota general" in _one(v2, 1).mensaje

def test_2_and_10_defined_but_not_placed():
    v = _run(defs=["K-50"], plan_texts=[])
    assert _one(v, 2).severidad == "aviso"
    v2 = _run(defs=["K-50"], plan_texts=[("K-50", "v_pa")])        # written in a planta, no placement
    assert _one(v2, 10).severidad == "duda" and not _all(v2, 2)

def test_7_critical_missing():
    v = _run(elementos=[_el("P-4", familia="pilote", longitud=None)])
    assert _one(v, 7).severidad == "bloquea" and "longitud" in _one(v, 7).mensaje
    v2 = _run(elementos=[_el("K-1", estribos=_estribos("E#3"))])    # no spacing; a castillo supuesto exists
    assert _one(v2, 7).severidad == "duda" and "separación" in _one(v2, 7).mensaje

def test_8_contradictions():
    v = _run(defs_conflict=("K-5", (20, 30), (20, 40)), reglas=_reglas_marina())
    msgs = [x.mensaje for x in _all(v, 8)]
    assert any("K-5" in m and "20x30" in m and "20x40" in m for m in msgs)
    assert any("#8" in m and "suelda" in m for m in msgs)

def test_11_orphans_ambiguity_and_cuadro_consistency():
    v = _run(rechazos=[_rech("6#4", "ambigua", ["K-1", "K-2"]), _rech("4#3", "sin_dueno", [])],
             parse_avisos={"K-4": ["sin leer: «@1S»"]},
             cuadro_without_stack=["K-7"])
    assert len(_all(v, 11)) == 4 and all(x.severidad == "duda" for x in _all(v, 11))

def test_ids_are_stable():
    assert [x.id for x in _run(elementos=[_el("K-99")])] == [x.id for x in _run(elementos=[_el("K-99")])]
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** each check exactly as spec §4 (E0 subset). Check 10's "mark text in a planta": textual entities whose content is a mark, inside a structural plan view's bbox (same source file), not in any detection's `source_entities`, not in `inv.cuadro_mark_entities`. Check 11 includes `inv.rechazos`, each definition reading's `avisos`, `role=cuadro` labels that own no stack, and stack-owning labels counted as placements. Messages in Spanish, e.g. `"K-5 tiene dos secciones en el plano: 20x40 (ES-200) y 20x30 (ES-400). Se usa la de la hoja de su planta; confírmalo."`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(estructura): las verificaciones del propio plano — marca sin definir, definida sin colocar, dato crítico faltante, el plano que se contradice, marca escrita sin elemento, texto sin dueño`.

---

### Task 12: The model, the scorecard, decisions, pipeline and recompute

**Files:**
- Create: `packages/klave_engine/estructura/modelo.py`
- Modify: `packages/klave_engine/pipeline.py` (build after `write_json(processed / "detections.json", ...)` ~line 629; pass to `generate_cost_report`; write after costing), `packages/klave_engine/costing/recompute.py` (load `estructura.json`, re-apply decisions, pass on, re-write), `packages/klave_engine/evals/gold.py:185-210` (`_engine_money` passes `optional("estructura.json")`)
- Test: `tests/test_estructura_modelo.py`

**Interfaces:**
- Consumes: everything above; `CostReport`.
- Produces:
  - `ESTRUCTURA_FILENAME = "estructura.json"`, `DECISIONES_FILENAME = "estructura_decisiones.json"`
  - `class Decision(BaseModel)`: `marca: str`, `campo: Literal["seccion_cm","longitud_m","longitudinales","estribos","parrillas"]`, `valor: Any`, `nota: str = ""`, `actor: str = ""`, `fecha: datetime`
  - `class ResumenFamilia(BaseModel)`: `familia: str`, `colocaciones: int`, `con_definicion: int`, `criticos_total: int`, `criticos_del_plano: int`, `bloquea: int`, `duda: int`, `aviso: int`, `en_juego_mxn: float | None`, `en_juego_cantidad: dict[str, float]`
  - `class Estructura(BaseModel)`: `version: int = 1`, `reglas: Reglas`, `definiciones: list[Definicion]`, `por_familia: list[Definicion]`, `elementos: list[Elemento]`, `verificaciones: list[Verificacion]`, `resumen: list[ResumenFamilia]`, `avisos: list[str]`
  - `construir_estructura(entities, frames, inv, detections, segmentation, meters_factor, altura_supuesta_m) -> Estructura`
  - `cargar_decisiones(control_dir: Path) -> list[Decision]`, `guardar_decision(control_dir: Path, d: Decision) -> None`
  - `aplicar_decisiones(e: Estructura, decisiones: list[Decision]) -> Estructura` (adds `humano` `Dato`s, re-resolves elements, re-runs checks; unknown marks → `avisos`)
  - `resumir(e: Estructura, report: CostReport) -> list[ResumenFamilia]`
  - `leer_estructura(processed: Path) -> Estructura | None`, `escribir_estructura(processed: Path, e: Estructura) -> None`

- [ ] **Step 1: Write the failing tests**

```python
def test_pipeline_writes_estructura_on_demo(tmp_path, data_dir):
    root = tmp_path / "demo"; write_demo_project(root)
    run_full_pipeline(root, get_settings())
    e = leer_estructura(root / get_settings().processed_dir_name)
    assert e is not None and e.reglas.tabla_varillas.fuente == "supuesto" and isinstance(e.resumen, list)

def test_decision_applies_and_survives(tmp_path):
    e = _estructura_k5_conflict()
    d = Decision(marca="K-5", campo="seccion_cm", valor=[20, 40], nota="hoja de PA", actor="Diego", fecha=_now())
    out = aplicar_decisiones(e, [d])
    k5 = next(x for x in out.definiciones if x.marca == "K-5").seccion_cm
    assert k5.fuente == "humano" and tuple(k5.valor) == (20, 40) and not k5.en_conflicto
    assert not [v for v in out.verificaciones if v.numero == 8 and "K-5" in v.marcas]

def test_decision_for_a_vanished_mark_is_a_warning():
    out = aplicar_decisiones(_estructura_k5_conflict(),
                             [Decision(marca="K-77", campo="estribos", valor=[], fecha=_now())])
    assert any("K-77" in a for a in out.avisos)

def test_resumen_counts_and_money():
    r = resumir(_estructura_k5_conflict(), _report_with_est001_price(4000.0))
    cas = next(x for x in r if x.familia == "castillo")
    assert cas.colocaciones == 2 and cas.con_definicion == 2 and cas.duda >= 1
    assert cas.en_juego_mxn == pytest.approx(0.20 * 0.10 * 2.9 * 2 * 4000.0)   # Δ area × height × 2 pzas × P.U.

def test_recompute_without_estructura_still_works(tmp_path, data_dir):
    root = tmp_path / "demo"; write_demo_project(root); settings = get_settings()
    run_full_pipeline(root, settings)
    for p in (root / settings.processed_dir_name).rglob(ESTRUCTURA_FILENAME):
        p.unlink()                                            # now it looks like an old run
    report = _recompute(root)   # same call as tests/test_variantes_api.py::_project → recompute_and_persist(...)
    assert report.boq.lines and not any("estructura" in w.lower() and "error" in w.lower()
                                        for w in report.boq.warnings)

def test_instalaciones_only_is_empty_not_a_crash():
    e = construir_estructura([], [], ScheduleInventory(), [], None, None, 2.7)
    assert e.elementos == [] and e.resumen == [] and e.verificaciones == []
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** `construir_estructura` = `leer_reglas` → `construir_definiciones` → `asignar_formas` on each definition's estribos (writing the shapes into the `Dato` value) → `construir_elementos` → `verificar`. Pipeline: build after the final `detections.json` write, apply `cargar_decisiones(control_dir)`, pass `estructura.model_dump(mode="json")` to `generate_cost_report`, then `resumen = resumir(...)`, `escribir_estructura(processed, ...)`; log stage `estructura_built` with counts and elapsed ms. Recompute: `leer_estructura` → `aplicar_decisiones(cargar_decisiones(...))` → pass on → `resumir` → `escribir_estructura`. `en_juego`: for section conflicts Δ(area) × height × placements × P.U. of the line that holds the placements; for armado conflicts Δkg via `acero_elemento` with the alternative × P.U. of the ACE line; unpriced → `en_juego_cantidad` only.
- [ ] **Step 4: Run** `uv run pytest -q` → PASS; record the demo pipeline time before/after in the commit body.
- [ ] **Step 5: Commit** `feat(estructura): el modelo en el pipeline y en el recálculo — estructura.json, decisiones humanas que sobreviven a la reprocesada, la tarjeta por familia con lo que está en juego`.

---

### Task 13: API

**Files:**
- Create: `apps/api/routes/estructura.py`
- Modify: `apps/api/main.py` (import + `app.include_router(estructura.router)`)
- Test: `tests/test_estructura_api.py`

**Interfaces:**
- Consumes: `leer_estructura`, `guardar_decision`, `Decision`, `ESTRUCTURA_FILENAME` (Task 12); `append_labels` (`costing/etiquetas.py`); `_recompute_after_review` (`apps/api/routes/reviews.py`); `ProjectStore`, `get_store`, `get_settings`, `project_recompute_lock` (`apps/api/dependencies.py`); `clean_actor` (`apps/api/events.py`).
- Produces:
  - `GET /projects/{project_id}/estructura` → `{"disponible": bool, "resumen": [...], "verificaciones": [...], "reglas": {...}, "avisos": [...]}`; `{"disponible": false}` (200) when the run has no `estructura.json`
  - `GET /projects/{project_id}/estructura/elementos?familia=castillo` → `{"elementos": [...], "definiciones": {marca: Definicion}}`
  - `POST /projects/{project_id}/estructura/decisiones` body `{"marca": str, "campo": str, "valor": Any, "nota": str}` header `X-Actor` → saves, appends a label `{"action": "decide_value", "marca", "campo", "valor", "antes"}`, recomputes, returns the new `GET /estructura` payload. 404 unknown project, 422 unknown `campo` or empty `nota` when overriding a drawing value.

- [ ] **Step 1: Write the failing tests** (pattern of `tests/test_variantes_api.py`: unreachable users DB env, `TestClient(create_app())`, a processed demo project):

```python
def test_get_estructura_and_decide(data_dir, monkeypatch):
    client, pid = _client_with_processed_project(data_dir, monkeypatch, with_estructura=True)
    body = client.get(f"/projects/{pid}/estructura").json()
    assert body["disponible"] is True and "resumen" in body and "verificaciones" in body
    r = client.post(f"/projects/{pid}/estructura/decisiones",
                    json={"marca": "K-5", "campo": "seccion_cm", "valor": [20, 40], "nota": "hoja PA"},
                    headers={"X-Actor": "Diego"})
    assert r.status_code == 200, r.text
    assert any(l.get("action") == "decide_value" for l in read_labels(_control_dir(data_dir, pid)))

def test_old_run_is_not_an_error(data_dir, monkeypatch):
    client, pid = _client_with_processed_project(data_dir, monkeypatch, with_estructura=False)
    assert client.get(f"/projects/{pid}/estructura").json() == {"disponible": False}

def test_override_needs_a_note(data_dir, monkeypatch):
    client, pid = _client_with_processed_project(data_dir, monkeypatch, with_estructura=True)
    r = client.post(f"/projects/{pid}/estructura/decisiones",
                    json={"marca": "K-5", "campo": "seccion_cm", "valor": [25, 40], "nota": ""})
    assert r.status_code == 422
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** following `apps/api/routes/propuestas.py` (router prefix `/projects`, tags `["estructura"]`, `store.read_artifact` raising `HTTPException` for missing artifacts → catch and answer `{"disponible": False}`; hold `project_recompute_lock` around save + recompute).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(api): /estructura — la lectura estructural, sus elementos y la decisión humana que recalcula`.

---

### Task 14: The «Lectura estructural» tab in Revisión

**Files:**
- Modify: `apps/web/lib/api.ts` (types `Estructura`, `ResumenFamilia`, `Verificacion`, `DatoView`; `getEstructura(projectId)`, `getEstructuraElementos(projectId, familia)`, `decidirEstructura(projectId, body, actor)`)
- Create: `apps/web/components/EstructuraSection.tsx`
- Modify: `apps/web/app/proyecto/[id]/revision/page.tsx` (add `"estructura"` to `RevisionTab` and the tab list, render `<EstructuraSection>` like `PropuestasSection`)

**Interfaces:**
- Consumes: the Task 13 endpoints.
- Produces: a tab labelled «Lectura estructural» showing (1) the per-family table — Familia · Colocadas · Con definición · Del plano (n de m) · Bloquea · Dudas · En juego — sorted by «En juego»; (2) the findings grouped by severity, each with its message, its sources side by side (`fuente` in words: «cuadro», «detalle», «sección dibujada», «nota», «medido», «regla», «supuesto», «IA (por confirmar)», «decisión de …»), a «Ver en el plano» link (`/proyecto/{id}/plano?bbox=…`) per source, and for conflicts one «Usar este valor» button per value that opens a note field (required) and posts the decision; (3) `{"disponible": false}` → a Callout «Esta lectura es anterior a la lectura estructural. Reprocesa el proyecto para verla.»

- [ ] **Step 1: Implement** the types and calls in `lib/api.ts` (same `getJSON`/`postJSON` helpers as the propuestas calls), the component (same state pattern as `PropuestasSection`: `state`, `failed`, `busy`, `notice`, `error`, `reloadKey`), and the tab. No probability/confidence anywhere; no rule codes; Spanish copy.
- [ ] **Step 2: Verify types and lint:** `cd apps/web && npx tsc --noEmit && npm run lint` → no errors.
- [ ] **Step 3: Verify in the browser** with the preview tools: start the API and web dev servers (`.claude/launch.json` entries; create them if missing: `make api` on 8000, `make web` on 3000), log in with the local test account, open a processed project's Revisión → «Lectura estructural»; check the table renders, a conflict shows two values with their sources, «Usar este valor» without a note is refused, with a note it applies and the conflict disappears after recompute; check the old-run callout on a project without `estructura.json`; check dark mode and a 375 px viewport. Take a screenshot as proof.
- [ ] **Step 4: Commit** `feat(web): la pestaña «Lectura estructural» en Revisión — la tarjeta por familia, los hallazgos con sus fuentes lado a lado y la decisión con nota`.

---

### Task 15: Gold — the `estructura` fence and a Marina entry

**Files:**
- Modify: `packages/klave_engine/evals/gold.py` (`EstructuraExpectation`, capture, evaluate, markdown)
- Test: `tests/test_gold.py` (extend)
- Create (generated, committed): `evals/gold/marina-estructural.json`; recaptured: `evals/gold/demo.json`, `prueba-1.json`, `torre-reforma-s101.json` (only if their `estructura`/money changed — say so in the commit)

**Interfaces:**
- Produces: `class EstructuraExpectation(BaseModel)`: `por_familia: dict[str, dict[str, int]]` (keys `colocaciones`, `con_definicion`, `criticos_total`, `criticos_del_plano`), `verificaciones: dict[str, int]` (`"1"`…`"11"` → count), `transcripcion: str | None` (path to a transcription JSON). `GoldEntry.estructura: EstructuraExpectation | None = None`. Evaluation is exact; a transcription, when set, must match per (marca, hoja) reading (Task 16 format).

- [ ] **Step 1: Write the failing test**

```python
def test_estructura_fence_is_exact(tmp_path):
    want = EstructuraExpectation(por_familia={"castillo": {"colocaciones": 2, "con_definicion": 2,
                                 "criticos_total": 8, "criticos_del_plano": 6}}, verificaciones={"8": 1})
    ok, diffs = score_estructura(want, _estructura_like(want))
    assert ok and diffs == []
    ok2, diffs2 = score_estructura(want, _estructura_like(want, castillo_con_definicion=1))
    assert not ok2 and "castillo" in diffs2[0]
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** `score_estructura(want, estructura_json) -> tuple[bool, list[str]]`, capture from a fresh run (read `estructura.json` from the scratch processed dir **before** the scratch is deleted), include in `evaluate_entry`'s pass/fail and in `render_markdown`.
- [ ] **Step 4: Run** → PASS. Then capture Marina: `make gold-capture ROOT=data/uploads/marina_lote_04_estructural_d1cd5ec8 ID=marina-estructural` and `uv run python -m klave_engine.evals.gold money --only marina-estructural`; run `make eval-gold` and recapture any entry whose money or estructura moved because of Tasks 7/10, listing in the commit which concepts moved and why (truncated bar groups restored, EYG grapas counted, stirrup geometry by shape).
- [ ] **Step 5: Commit** `test(gold): la lectura estructural entra al gold — cerca exacta por familia y por verificación; Marina estructural como entrada nueva; recapturas con su razón`.

---

### Task 16: The Marina transcription, hand-reviewed, and the round's closing checks

**Files:**
- Create: `scripts/transcribir_marcas.py`, `evals/transcripcion/marina_lote_04_estructural.json`, `docs/lectura-estructural.md`
- Modify: `evals/gold/marina-estructural.json` (`estructura.transcripcion` set)

**Interfaces:**
- `python -m scripts.transcribir_marcas <dxf> --out <draft.json>` — **independent of the engine's association**: walks model space with ezdxf and expands INSERTs with `virtual_entities()` (depth ≤ 3) itself, lists every mark-like label and, for each, every text within 1.6 m containing `#`, `@`, `CENTRO`, `EXT`, `REFUERZO` or `VER CORTE`, with dx, dy, heights, block path and the frame code (frames read from the run's `frames.json` for naming only).
- Transcription format: `{"revisado_por": "…", "revisado_en": "YYYY-MM-DD", "lecturas": [{"marca": "K-4", "hoja": "ES-400", "textos": ["6#4", "EYG#3@15"], "longitudinal": "6#4", "estribos": "EYG#3@15", "seccion_cm": [15, 30] | null}]}` — one entry per (marca, hoja) the drawing defines.

- [ ] **Step 1:** Write and run the script on `data/raw/marina-4/converted/02 ESTRUCTURAL L.04 - 26.01.15.dxf`; save the draft to the scratchpad (not the repo).
- [ ] **Step 2: Hand review, mark by mark.** For every label in the draft decide which texts it owns by reading the dump (and, where unclear, rendering the frame region to an image and looking at it). Record the decision per (marca, hoja) in `evals/transcripcion/marina_lote_04_estructural.json` with the canonical texts. The first ten castillo rows must equal spec §2's table; C-1/C-2/C-3, K-9…K-20A, K-15A, P-1…P-5 per §2's second list. Anything that cannot be decided from the drawing goes into a `"dudas"` list with the reason — not guessed.
- [ ] **Step 3:** Set `estructura.transcripcion` in `evals/gold/marina-estructural.json`; run `uv run python -m klave_engine.evals.gold run` → the Marina transcription matches the engine's readings exactly. Every mismatch is fixed in the engine (Tasks 3, 6, 7) with a regression test from the real case — never by editing the transcription to agree with the engine.
- [ ] **Step 4: Closing checks (spec §10 E0 «Done when»)** on scratch copies of Marina, PRUEBA-1 and Torre (copy `drawings/` to the scratchpad and `run_full_pipeline` there): all Marina armado texts parse or carry an aviso naming the token; no `ia` value fills a field whose text exists; `Reglas` = 8 table rows, covers for 4 family groups, weld from #8, lap limit #6, first stirrup 6 cm, castillo anchorage 100 cm, the #8 contradiction among the findings; K-5/K-6/K-8 section conflicts appear as check 8 dudas; the three scorecards exist; pipeline time on Marina within +10 % of today's (measure before Task 1 and now; write both numbers in the commit).
- [ ] **Step 5:** Write `docs/lectura-estructural.md` (one page, Spanish, for the engineer: where each value comes from, what each finding means, how to decide a conflict). 
- [ ] **Step 6: Commit** `test(estructura): la transcripción de Marina hecha a mano como verdad de la lectura — y el cierre de E0 con sus números`.

---

## After E0

Diego's spot-check list (spec §12) is produced from the Marina run: the findings tab plus the transcription's `dudas`. E1 (cimentación complete) gets its own plan once this round is merged.

---

## E0 close-out addendum (2026-10-27) — runs before Task 16

Added by the controller from Task 15's review (R248, the PRUEBA-1 overlap note, the Task 12 variant-split note). Diego approved closing these on 2026-10-27; gold recaptures are allowed when each moved value is raw-verified and the commit says why.

### Task 15b: D-n labels join their dados, and dado heights come from their cortes

**Why:** On Marina the 23 `EST-DADOS` tags (D-1…D-5B, D-X) sit 0.07–0.46 m beside the 23 dado outlines, but the engine never joins them («puede ser la suya, sin juntar»). So dado placements carry no definition, 14 of check 10's 21 dudas are this gap, zapata/dado and `verificaciones.1/aviso` cannot be fenced, and CIM-002 uses a supposed dado height although each dado's corte X-X'/Y-Y' (ES-005/006/007) dimensions it with a vertical cota on `COTAS-100` (e.g. handle 42766 «100» on D-1, 429EA on D-3; the plan view beside it shows «55»/«60»).

**Files (expected; follow the code):** `packages/klave_engine/estructura/elementos.py` and/or the association that joins tags to outlines; the dado/zapata family path (`detection/schedules.py::family_of_mark`, `footing_detector.py`); `estructura/definiciones.py` for the height Dato; `evals/gold/marina-estructural.json`; tests under `tests/`.

- [ ] **Step 1 (raw truth first):** an independent script (ezdxf + `virtual_entities()`, not the engine's association) lists, for every D-n tag on Marina `02 ESTRUCTURAL`, its nearest dado outline, distance, and the corte cota(s) that dimension that mark's height (by the corte's title naming the mark). Save it under `scripts/` only if it is reused by the gold; otherwise in the scratchpad.
- [ ] **Step 2:** join a D-n tag to the dado outline it labels when it is on that outline's own layer family (`EST-DADOS`), within reach of that outline and no nearer outline of the same family competes; a contested tag stays a `duda` naming both outlines. `D-` is a dado ONLY where the drawing states it (title word DADO, the `EST-DADOS` layer, or a cuadro heading); elsewhere D- stays ambiguous (R159 stands — never a dala/dado guess from the prefix alone).
- [ ] **Step 3:** the dado height Dato: source `detalle` when its corte dimensions it (value from the cota text, not measured length), else `supuesto` with check 7. A plan-view cota beside the outline («55»/«60») is a side, never the height. CIM-002 uses the joined height.
- [ ] **Step 4:** D-X (drawn nested inside D-4) is NOT decided by the engine: report it as a `duda` «D-X dentro de D-4: ¿pedestal o dado aparte?» and price neither twice. Diego answers this in the spot-check.
- [ ] **Step 5:** tests from the real case (a synthetic fixture shaped like D-1 + its corte, a contested tag, D-X nested), then recapture `marina-estructural`: fence zapata/dado placements and their definitions, `verificaciones.1/aviso`, the new 10/duda count, and CIM-002 — each raw-verified; the commit states old → new values and why.

**Done when:** every Marina dado placement is joined to its D-n definition or carries a `duda`/`bloquea` naming what is missing; every dado height is the corte's cota or a visible `supuesto`; CIM-002 is fenced; gold green with stated recapture.

### Task 15c: a castillo tag belongs to one view (PRUEBA-1 overlap)

**Why:** On PRUEBA-1 (four plan views on one sheet: cimentación, PB, PA, azotea) 20 castillo tags fall inside both the planta-alta and the azotea view boxes; the engine splits castillos 69/65/65/18 against about 22 tags actually in the azotea area. A tag counted in the wrong storey moves heights and money (EST-001).

**Files (expected):** `packages/klave_engine/detection/views.py` (view boxes and assignment), any caller that assigns detections to views; `evals/gold/prueba-1.json`; tests.

- [ ] **Step 1 (raw truth):** an independent script lists PRUEBA-1's view titles and the drawn extent of each view (its linework, not the title box), and for each castillo tag the view(s) whose box contains it. Confirm by rendering the sheet region to an image and looking at it.
- [ ] **Step 2:** assignment never puts one tag in two views: overlapping boxes are resolved by the view whose own drawn content (grid/walls/outlines of that view) contains the tag, else the nearest view title below/above per the sheet's layout; an unresolvable tag is a `duda`, never counted twice and never dropped silently.
- [ ] **Step 3:** tests (two overlapping view boxes with tags in the overlap), Marina/Torre unchanged (they have no overlapping boxes — confirm), recapture `prueba-1` with each moved castillo count and EST-001 raw-verified; commit states old → new.

**Done when:** each PRUEBA-1 castillo tag is in exactly one view, the per-view counts equal the raw count, gold green with stated recapture.

### Task 15d: variants are split over the detections a line counts (all families)

**Why:** In Task 12 the fix «a line's variants are grouped only over the detections that line counts» was narrowed to `COLUMN_VOLUME` lines in `costing/boq.py` because the general form moved gold (PRUEBA-1 EST-004 variants). The defect is real for every other family: a detection that a line does NOT count can still shape that line's variant split pro rata, silently (Marina K-15A on ES-000 invented 0.44 m³ before the column fix).

**Files:** `packages/klave_engine/costing/boq.py` (`dividir` and its callers), `tests/test_story_heights.py` or a new focused test, `evals/gold/prueba-1.json` (and any other entry that moves).

- [ ] **Step 1:** make the general form: every line's variants are grouped over exactly the detections it counts; remove the column-only narrowing.
- [ ] **Step 2:** for each gold value that moves, show from the raw drawing which detections the line counts and that the new split is the right one; recapture with the reason.
- [ ] **Step 3:** tests: one per family kind that has variants (column volume, wall area, beam length…) with an uncounted detection that must not shape the split.

**Done when:** no line's variant split includes a detection the line does not count; gold green with stated recapture.
