# Catálogo base y paridad OPUS — design (draft 2026-09-14, pending Diego's review)

**Goal.** A fresh taller opens with a priced catalog, a plano turns into a
licitación-grade catálogo de conceptos with sourced prices in hours instead
of weeks, and the catálogo screen does everything an estimator does in OPUS
without leaving one sheet. A person still reviews and signs; nothing is
invented silently.

**Why now.** The honest assessment of 2026-09-14: the engine produces good
structural quantities with provenance, but the chain breaks twice —
cantidades → conceptos (the engine speaks 30 rule codes; a licitación
catalog has 200–600) and conceptos → precios (the shipped catalog has zero
matrices; every gold fixture's direct cost is $0.00). The doctrine "no
invented prices" was right and was never followed by the data it requires.

**What exists and is reused.** SQLite workspace catalog (`catalog_store.py`:
insumos, concepts, apu_components, price_sources + reference_prices,
plantillas, parametric_rules, aliases, insumo_analysis, indices,
workspace_settings); CDMX Tabulador 2026 parsed to 5,458 reference rows
with 155 sections → partida; SICT costo horario; FSR machinery
(`labor.py`, region presets); costo horario (`equipment.py`); indirectos,
financiamiento, cargos adicionales (`indirectos.py`); escalatorias
(`escalatoria.py`, INEGI índices with roll-forward); matcher with ficha
técnica (`matching.py`, `ficha.py`); LOPSRM descriptions
(`descripciones.py`); imports: Excel matrices, destajos, custom price books,
and — as of today — the native OPUS base (`sources/opus_native.py`).

**Principles (binding).**
1. Every price and every matrix says where it came from: `oficial`,
   `importada`, `generada`, `taller`. The origin is a column, not prose.
2. Generated things are marked generated until a person touches them; a
   touch promotes the row to `taller` and records who.
3. An official price is the fence for a matrix: a generated matrix whose
   direct cost lands outside tolerance of the tabulador price of the same
   concept is shown as out of range, never used as if validated.
4. One sheet per screen, keyboard first, inspector on the right instead of
   modals, every action reachable from ⌘K.
5. Gold quantities per rule code must not move. Variants roll up to their
   rule code for the fence; the fence gains no new expectations without a
   declared recapture.

---

## 1. Data model: the four layers

### 1.1 Origin and validation on concepts and insumos

`concepts` gains:

| column | type | meaning |
|---|---|---|
| `origin` | TEXT NOT NULL DEFAULT 'taller' | `oficial` · `importada` · `generada` · `taller` |
| `origin_ref` | TEXT | the source it came from: `cdmx-tabulador-2026-06 · IB12BB`, `PRISMA acero 2026 · EMC3`, `generada · plantilla concreto-estructural` |
| `variant_of` | TEXT | rule code this concept is a specialization of (§5); NULL otherwise |
| `spec_signature` | TEXT (json) | the ficha that makes the variant distinct: `{"fc":250,"section_cm":[30,40]}` |
| `validation` | TEXT (json) | `{"reference_ref_id":…, "reference_price":…, "direct_cost":…, "deviation_pct":…, "verdict":"validada|fuera_de_rango|sin_referencia", "at":"…"}` |
| `touched_by` / `touched_at` | TEXT | set when a person edits a generated or imported row (promotes to `taller`) |

`insumos` gains `origin` and `origin_ref` with the same vocabulary. The
existing `source`, `source_type` (`cotizacion|publicacion|seed`), `region`
and `vigencia` stay; `origin` is the layer, `source` the document.

Migration: existing rows get `origin='taller'` if they were user-created
or edited, `'oficial'` if `source_type='publicacion'`, `'importada'` if
`import_source` is set, else `'taller'`. The seed "Referencia Klave" rows
become `generada` with `origin_ref='semilla Klave'` — they were never
official and should stop looking like it.

### 1.2 Básicos: components that are themselves analyses

Today `apu_components(concept_code, resource_code, quantity)` references an
insumo. A básico (concreto hecho en obra, mortero, cuadrilla) is an insumo
whose price is computed from its own matrix. Model:

- `insumos.kind` TEXT NOT NULL DEFAULT 'insumo': `insumo` · `basico` ·
  `cuadrilla`.
- A `basico` or `cuadrilla` row may have rows in `apu_components` keyed by
  its own code (the same table; OPUS does exactly this — the 1S2E cuadrilla
  has its matrix in the F table).
- `unit_cost` of a básico is derived at read time by `apu.py` (recursive,
  cycle-guarded, depth ≤ 4, error names the cycle). The stored `unit_cost`
  is a cache written on every recompute so exports and the price book stay
  fast; `origin_ref` says "derivado de su matriz".
- A `cuadrilla` is a básico whose components are labor categories with
  counts; its unit is JOR; FSR applies per member category (already how
  `labor.py` prices categories), never to the composite twice.
- `UnitPriceAnalysis` gains `lines[i].sub_analysis: UnitPriceAnalysis | None`
  so the web inspector can expand a básico inline.
- The OPUS reader stops flattening: cuadrillas and auxiliares import as
  `kind=cuadrilla|basico` with their matrices; the "no anida básicos"
  problem line disappears.

### 1.3 The base catalogs as sources, the taller as master

The store already holds published rows in `reference_prices` per
`price_sources` row, and `adopt_reference` prices an *insumo* from one. The
missing verb is adopting a *concept*:

- `adopt_reference_as_concept(ref_id, *, code=None, phase=None)` creates a
  concept with `origin='oficial'`, `origin_ref` = source · clave, unit and
  description from the row, `phase` from the source's section mapping
  (`cdmx_capitulos.py` already resolves it), a `concept_price` at the
  published price (the existing `create_priced_concept` path — price
  without matrix, marked "precio de tabulador"), and `validation` =
  `sin_matriz`.
- The same for imported bases: an imported OPUS or Excel base lands as a
  `price_sources` row of kind `matrices` with its concepts *and* matrices
  in `reference_prices` (+ new `reference_components`), so a base can be
  browsed without polluting the taller; "Traer al taller" copies concept,
  matrix and insumos with `origin='importada'`. Today `import_matrices`
  writes straight into the taller; that stays as the "importar directo"
  option, but the default becomes browse-then-bring.
- The taller catalog is the master. Projects consume it; per-project
  divergence stays in `CostingOverrides` and documented adjustments (no
  per-project catalog fork in this round — recorded in Out of scope).

---

## 2. Official sources: the priced base that ships

Each source is a `SourceSpec` in `sources/registry.py` with a parser, a
test on a fixture excerpt, a `vigencia`, and a manifest sha256. A fresh
taller imports all of them on first run (idempotent; the sources page shows
what is loaded and its vigencia).

| source | file(s) in `data/sources` | parser | yields |
|---|---|---|---|
| CDMX Tabulador 2026 (mar, jun) | present | present | 5,458 priced concepts, section → partida |
| SICT maquinaria 2026 | present | present | costo horario per machine |
| SICT costo directo carretero 2026 | present (485 pp) | new, pypdfium2 text: `LINEA CÓDIGO descripción` + `unidad $precio` | ~4,000 priced concepts (terracerías, estructuras, drenaje, pavimentos, túneles, señalamiento) |
| CONAGUA Catálogo General 2026 | downloaded (119 pp) | new: `NNNN NN concepto UNIDAD $ precio`, `NNNN 00` = group | agua potable, alcantarillado, piezas especiales, tubería, obras civiles |
| INIFECH Chiapas tabulador | downloaded (90 pp, encrypted; pypdfium2 reads it) | new: 10-digit code, multi-line description, 15 regional prices → `extra.regiones` | the regional price signal for §6.4 |
| Guanajuato UEC Tabulador de Referencia 2026 | downloaded: **Excel**, one file per region (I–VI, ~3,400 rows each) | new (openpyxl): hierarchical `UEC.ED.cap.sub.item`, unit, price; six files → one source with `extra.regiones` | ~3,400 priced concepts × 6 regions, edificación and urbanización |
| Guanajuato UEC listado de materiales (sep 2026) | downloaded (3 pp, table) | new (pdfplumber tables): material, presentación, unidad, 6 regional market prices | the first official **insumo** price list (kind `insumos`) |
| Guanajuato UEC listado de maquinaria (sep 2026) | downloaded (1 p, table) | new: máquina, motor, HP, costo horario | costo horario, state level |
| INEGI INPP construcción | CSV from BIE, user-downloaded | existing `indices` import + roll-forward | escalatorias per LOPSRM art. 58 (documented, no new parser) |
| CONASAMI 2026 | constants in `labor.py` | verify vigencia | salario mínimo general / frontera |

Dropped after inspection: SICT paramétricos 2026 (narrative models per road type, not concept rows) and SICT servicios (file not in hand). Guanajuato also publishes 23 Excel "catálogos de referencia" for typical buildings (aulas, bardas, canchas, líneas de agua) — catálogo de conceptos with quantities per prototype, a later track for plantillas.

Parser rule shared by all PDF tabuladores: a row is `clave`, a description
that may wrap, a unit token, a price; group headers become
`group_clave/group_description`; the section → partida map is per source
(`cdmx_capitulos.py` becomes `secciones.py` with one dict per publisher).
Every parser reports what it could not read as `problems`, never drops
silently, and the sources page shows the count.

Licensing: everything in this table is a government publication and ships
with Klave. Vendor bases (Ingeniería Integral/PRISMA, CMIC) are the
taller's own imports; Klave never ships them. The CMIC "Catálogo de costos
directos de vivienda 2026" is the recommended purchase for matrices; if
its PDF layout is regular, a parser joins §3.1 as an import path.

---

## 3. Matrices: imported first, generated and fenced second

### 3.1 Import paths

- Excel export (exists), OPUS native base (exists; gains básicos per §1.2
  and multi-base zip: a zip with several `<BASE>*` prefixes imports each as
  its own source), destajos (exists), CMIC PDF (conditional on layout).
- Import lands in `reference_prices` + `reference_components` as a
  browsable base (§1.3); "importar directo al taller" remains for a
  taller's own OPUS history.
- Extras from OPUS (FSR parameters, costos horarios with parameters,
  integración percentages) become *proposals* on the Salario real and
  Equipo screens: "la base trae FSR 1.77 con estos parámetros — adoptar".
  Never applied silently.

### 3.2 Generated matrices, validated against the official price

`costing/generacion.py`:

- **Plantillas de matriz por familia** (`data/plantillas_matriz.json`, in
  repo, curated): for each family the engine knows (concreto estructural
  por elemento, cimbra por elemento, acero de refuerzo, mampostería,
  aplanados, pisos, excavación, relleno, plantilla, instalaciones básicas)
  the structure of the matrix: material lines with a formula for quantity
  from the ficha (cemento per m³ from f'c class, varilla kg from
  rebar spec, block count from block size), waste factors, the cuadrilla
  and its rendimiento, herramienta as % of MO, equipo where standard.
  Each rendimiento carries a `source` string (publication, edition, page)
  — the curated table is itself a sourced document, reviewed by Diego.
- **Insumo prices** for generated matrices come from the official layer
  where it exists (labor from CONASAMI + FSR presets, equipment from SICT)
  and otherwise from a seed list `data/insumos_semilla.json` marked
  `origin=generada`, `source="precio de referencia, validar"`, replaceable
  by one import.
- **Validation**: the generated concept is matched to a reference row
  (`matching.py`, ficha-aware); direct cost from the matrix is compared to
  the published price. `|deviation| ≤ 15 %` → `validada`; otherwise
  `fuera_de_rango` with the deviation shown; no match → `sin_referencia`.
  The tolerance is a workspace setting; the verdict is stored in
  `validation` and recomputed when insumo prices change.
- **Where it runs**: on demand ("Generar matriz" for one concept or "Generar
  las que faltan" for the taller), and automatically for concepts produced
  by synthesis (§5). Never on import of a base that already brings
  matrices.
- **UI**: a generated row wears the `generada` badge and its verdict
  (validada / fuera de rango / sin referencia); opening the matrix shows
  each line's source. Editing any line promotes the concept to `taller`
  and keeps the validation for reference.

---

## 4. Synthesis: from the drawing to a licitación catalog

Today `boq.py` maps detections to one of ~30 rule codes (EST-001 concreto
en columnas, EST-004 muros, CIM-002 zapatas…). A licitación catalog says
"Concreto f'c=250 kg/cm² en columnas de 30×40 cm" and prices that.

`costing/sintesis.py`:

- For each rule code, the engine already carries per-element specs
  (section from the schedule chain, f'c/fy from notes, block kind, finish
  key, diameter). Synthesis groups the rule's detections by
  `spec_signature` (the subset of the ficha that changes the price, per
  family: concrete → f'c + element + section band; rebar → fy + diameter
  set; masonry → block size + kind; finishes → finish key; pipes →
  material + diameter).
- Each group becomes a **variant concept**: code `EST-001.C250-30X40`
  (rule code, dot, signature slug), `variant_of='EST-001'`,
  description synthesized by `descripciones.py` from the ficha, unit and
  phase inherited, `production_rate_per_day` from the rule concept until a
  matrix says otherwise.
- The variant is priced by §1.3 (adopt the best reference match if the
  matcher's score clears the existing threshold and units agree) or §3.2
  (generate and validate). The chosen path and verdict are in `validation`.
- The BoQ emits lines per variant, each carrying `variant_of`; totals by
  rule code are unchanged, which is what gold fences. `make eval-gold`
  gains a check that Σ variant quantities == rule quantity per fixture.
- Variants are taller concepts (`origin=generada`) and persist; a second
  project with the same signature reuses them. Review sits where it does
  today: Revisión shows the variant in the concept column, the catálogo
  sheet shows the variant nested under its rule code.

---

## 5. OPUS parity: features, each with its data and its screen

Ordered by how much each compounds the others.

| # | feature | data | screen |
|---|---|---|---|
| 5.1 | Catálogo maestro with browse-and-bring | §1.3 | Catálogo › Base tab: search across all loaded bases (official + imported), filter by partida/source/region, "Traer al taller" (single, multi-select), diff when a taller concept already has that clave |
| 5.2 | Básicos y auxiliares (nested matrices) | §1.2 | Matrix inspector expands a básico inline; editing a básico shows "usado en N matrices" before saving |
| 5.3 | Cuadrillas with FSR | §1.2 | Salario real tab lists cuadrillas as compositions of categories; per-member FSR; cost per jornada shown live |
| 5.4 | Precios por zona | `workspace_settings.region`; per-source regional prices (`extra.regiones`); a `factor_zona` table (source, region → factor) derived from INIFECH/CDMX comparisons, editable | Sources page shows region; adopting a reference applies the factor with provenance "CDMX × factor Chiapas R3 1.04"; insumo rows show region |
| 5.5 | Mass price update | new import log entry kind `ajuste_masivo` (undoable via existing `undo_import`) | Insumos tab: select by type/family/source → "+X %" with vigencia stamp |
| 5.6 | Find & replace insumo across matrices | store: `replace_resource(old, new, scope)` writes one undoable import entry | Insumos tab row action "Sustituir en matrices…" with the list of affected concepts |
| 5.7 | Dónde se usa | `GET /catalog/insumos/{code}/uso` | Insumo inspector: concepts, quantities, share of each concept's cost |
| 5.8 | Escalatorias por fórmula | `escalatoria.py` gains fórmula polinómica (Σ coef × índice/índice₀) beside explosión-based | Contrato › Ajuste de costos: choose method, show the index series used |
| 5.9 | Cargos adicionales y sobrecosto | `indirectos.CargoAdicional` exists | Presupuesto › Integración tab shows cargos rows editable; sobrecosto = the whole stack shown as one number with its components |
| 5.10 | Programas del art. 45-A | derived: explosión × programa → suministros, mano de obra, maquinaria por periodo | Programa node gains three tabs; XLSX export each |
| 5.11 | Licitación document set | `exports.py`: presupuesto normal/desglosado, resumen de capítulos, APU por concepto, análisis de MO/equipo/costos horarios, catálogo de insumos, explosión, programas, cálculo FSR, indirectos, utilidad, escalatorias — the exact format list OPUS ships (read from the IGIV table of the base) | Presupuesto › "Documentos" action: pick the set, one XLSX per document or one workbook |
| 5.12 | Printable APU per concept | template in `exports.py` | Matrix inspector "Imprimir análisis" |

Each feature ships with its ⌘K action and its keyboard path.

---

## 6. UX: the catálogo screen

- Tabs stay (Insumos · Conceptos y matrices · Base · Plantillas y
  paramétricos · Salario real y vigencia); "Fuentes de referencia" becomes
  **Base** with the browse-and-bring sheet.
- The conceptos sheet gains an **origin column** (badge: oficial /
  importada / generada / taller) and a **verdict column** for generated
  rows; variants nest under their rule code with a chevron.
- The **inspector** on the right replaces every modal in the catálogo:
  matrix (with básico expansion), ficha técnica, validation (published
  price vs direct cost, deviation, reference row link), "dónde se usa",
  history (who touched it).
- Empty state of a fresh taller is no longer empty: the Base tab shows the
  official sources loaded and a one-click "Traer los conceptos de mi
  partida" for the partidas the engine will need.
- Copy: every generated or imported item names its origin in the row, in
  Spanish, without percentages of confidence (house rule).

---

## 7. Honesty rules (consolidated)

1. No row without `origin`; no generated row without a verdict.
2. A generated matrix out of range is displayed with its deviation and is
   excluded from `moneyState` publishable totals until a person promotes
   it (the existing unpriced path: the line shows quantity, no peso).
3. Adopting a published price copies vigencia and region; a stale vigencia
   (older than the workspace's `vigencia_max_meses`) is flagged on the row
   and in the carátula.
4. Synthesis never changes a quantity, only how it is named and priced;
   Σ variants == rule quantity is a test, not a hope.
5. Vendor bases are the taller's; Klave ships only government sources and
   its own curated rendimientos with their citations.

---

## 8. Testing

- Store migrations: origin backfill on an existing db fixture; básico
  recursion with cycle detection; `adopt_reference_as_concept`; browse
  tables.
- Parsers: one fixture excerpt per new source (5–10 rows each) with the
  exact expected rows; regional extra for INIFECH; INPP CSV to `indices`.
- Generation: for each plantilla family a synthetic concept → matrix →
  direct cost; validation verdicts at the tolerance boundary; promotion on
  edit.
- Synthesis: prueba-1 and Marina fixtures → variants; Σ variant quantities
  == rule quantity for every concept in every gold fixture (new gold
  assertion, no recapture needed); description text golden per variant.
- OPUS reader: básicos nested (1S2E round-trips as cuadrilla with 3
  members), multi-base zip.
- Web: tsc, lint, build; the catálogo sheet keyboard path per new action
  (Playwright not in repo — manual checklist in the plan).

---

## 9. Phasing (one plan each)

| phase | delivers | depends on |
|---|---|---|
| A · La base con precio | §1.1 origin/validation schema + migration, §1.3 adopt-as-concept + browse tables, §2 new official parsers (SICT ×3, CONAGUA, INIFECH, Guanajuato, INPP), Base tab (5.1) | — |
| B · Básicos y OPUS batch 1 | §1.2 básicos/cuadrillas + OPUS reader nesting, 5.2, 5.3, 5.5, 5.6, 5.7, inspector (§6) | A |
| C · Matrices generadas | §3.2 plantillas, seed insumos, validation, verdict UI | A, B |
| D · Síntesis desde el plano | §4 variants, BoQ per variant, gold Σ check, Revisión/catálogo nesting | C |
| E · Zona, escalatorias, documentos | 5.4, 5.8, 5.9, 5.10, 5.11, 5.12 | A (5.4), B (5.11) |

Phase A starts immediately after this spec is approved. Blind detection
tests with other offices' drawings run in parallel when the plan sets
arrive and do not block any phase.

---

## Out of scope (recorded so nobody "helpfully" adds them)

- Per-project catalog forks; the taller stays the master.
- Scraping licensed bases (PRISMA, arq.com.mx, analisisdepreciosunitarios,
  Neodata, Ecostos).
- A CompraNet crawler for won-bid prices (a later track, per partida).
- Nested básicos deeper than 4 levels.
- Automatic promotion of generated rows; a person promotes.
- Reading OPUS report formats (IGIV) beyond listing their names.

## Decisions for Diego before Phase A

1. **Tolerance** for matrix validation: 15 % proposed.
2. **Default region** of a fresh taller: CDMX proposed (the richest source);
   the taller changes it in settings.
3. **Generated matrices on by default** for synthesized variants (marked,
   fenced) — proposed yes; the alternative is variants priced only by
   adopted references, which leaves most of them unpriced.
4. **Vendor base license** (Ingeniería Integral): read before Phase B
   treats it as more than your own import.
5. **CMIC vivienda 2026 purchase**: yes/no; if yes, the PDF decides whether
   a parser is worth writing.
