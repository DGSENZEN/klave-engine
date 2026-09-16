# Producto v1 · La capa de cuantificación y procedencia para OPUS y Neodata — design

**Date:** 2026-09-16 · **Status:** approved in brainstorming, pending Diego's review of this text
**Supersedes in priority:** `2026-09-14-catalogo-base-y-paridad-opus-design.md` (Fases D–E of that spec are re-sequenced here; nothing in it is deleted)

## 0. The product, in one sentence

A contractor's cost engineer drops a plan set in and gets back the generadores de obra negra with every quantity linked to the drawing, mapped onto the office's own catálogo, and delivered into OPUS or Neodata, the tools they already price in. An anteproyecto gives the same thing as a paramétrico with its assumptions written down; the proyecto ejecutivo later shows what moved.

Klave is not a replacement for OPUS or Neodata. It is the step before them that nobody sells: the cuantificador that doesn't sleep, plus the provenance those tools never had.

### Who it's for

1. The cost engineer in a contractor's office preparing licitaciones (primary).
2. The independent estimator or small despacho (same workflow, smaller scale).
3. The residente running estimaciones on site — later, on the same element graph (§10).

### What "essential" means

After three bids an office has (a) its catálogo with drawing-read quantities attached and corrections remembered, (b) a mapping memory in its own vocabulary, (c) a project that continues to site on the same lines. Going back to hand cuantificación costs them all three. That, not features, is the lock-in.

### The pitch the product is checked against

«Nos mandas tus planos hoy; mañana tienes los generadores de obra negra con cada cantidad ligada al plano, en tu catálogo, listos para meter a OPUS o Neodata. Lo que no leímos te lo decimos con nombre. Y cuando llegue la revisión C del proyecto, te decimos qué cambió, en cantidades y en pesos.»

## 1. Decisions taken (brainstorming 2026-09-16)

| # | decision |
|---|---|
| 1 | Pre-contract first: plano → propuesta. The site product rides on the same graph later. |
| 2 | Obra negra done to the bone: cimentación, estructura, albañilería, acabados básicos, terracerías. Everything else stays as levantamiento counts. |
| 3 | Prices: office base as master, Klave's official base and generated matrices underneath to fill holes and flag outliers. |
| 4 | Anteproyecto and ejecutivo are one maturing project, with a real "what moved" view. |
| 5 | Feed OPUS and Neodata; do not try to replace them. "Better than" is not in the pitch. |
| 6 | The reader that generalizes and learns from reviews is the killer feature; it is a product feature, not a service. Its design is a separate spec (§10). This spec only guarantees the hook: every Revisión action is captured as a label from day one. |
| 7 | Second-tier killer features: revision diff, completeness check, convocante catálogo verification, office índices. |
| 8 | Nothing is deleted from the app. Copilot, escalatorias, zona, cargos stay on the roadmap, frozen until the spine is done. |
| 9 | The pilot (one real bid through the tool beside the old way, timed and diffed) is a deliverable and a gate. |

## 2. The spine — what gets built properly

Each item has a done condition a stranger could check.

### 2.1 Reading obra negra

**Have:** grid per frame, columns/castillos, footings, beams, contratrabes, slabs by system, walls with openings, plantilla, excavation/fill/haul, piles, terracerías, formwork and rebar derived, acabados by mark; disciplines routed by content; coverage per sheet with reasons; hallazgos that cross-check the drawing; gold F1 = 1.0 on three sets + eight fixtures.

**Done when:** a plan set from an office that is not ours goes through with no calibration and, per concept, the read quantity lands inside the spread between two human cuantificadores on the same set. That spread is the bar. Per sheet, the engine states what it read and what it left as captura, with counts. Until other offices' plan sets arrive, the gold is a regression fence and nothing more.

**Work in this spec:** none beyond the label hook (§2.6) and PDF-vector ingestion as a spike (§8). Reading improvements wait for foreign drawings.

### 2.2 Mapping onto the office's catálogo

**Have:** OPUS native import (matrices, cuadrillas, FSR, costos horarios), Excel matrices import, Neodata Excel import (untested on a real file), aliases (`taller_clave`), the matcher with the ficha, the four-layer origin model.

**Missing:** the engine still emits its ~30 rule codes. This is the largest gap and the first thing every office hits.

**Design:**
- Fase D synthesis from the prior spec §4, unchanged: detections grouped by `spec_signature` per family → variant concepts `EST-001.C250-30X40` with `variant_of`, description synthesized from the ficha, Σ variants == rule quantity fenced in gold.
- **Mapping step (new):** each variant is matched onto the office's imported base (`reference_prices` rows of `kind=matrices|precios_unitarios` from that office's sources) with `matching.rank` + the ficha gate. Score ≥ 0.8 maps automatically; 0.5–0.8 maps as a duda for Revisión; below stays as a variant priced by Klave's layers, flagged «sin equivalente en tu catálogo».
- **Mapping memory (new):** a confirmed or corrected mapping writes an alias `(variant signature → office clave)` scoped to the workspace. The next project with the same signature maps without asking. Corrections are labels (§2.6).
- **Output vocabulary rule:** no rule code appears on any document, export or screen a client sees. The office's clave and description always; the variant behind it in the inspector.

**Done when:** a catálogo produced from a drawing uses the office's claves and descriptions for every read line, the engineer sees each mapping with its reason, one correction sticks for the next project, and the gold Σ-variants check is green.

### 2.3 The generador as the artifact

**Have:** generadores XLSX, budget lines with `source_detections`, visor highlight per concept, measurements on hover, Revisión with confirm/exclude/reassign.

**Design:**
- Every generador line carries: sheet, frame, eje(s) or nearest grid, nivel, element mark, the measured dimensions and the formula used, and a stable `element_id` that survives reprocessing (needed by the revision diff and later by estimaciones).
- **Standalone deliverable:** the XLSX plus a read-only share link to the visor for a project (token-scoped, no account), so a supervisor or a partner clicks any line and sees the polyline. Existing auth/workspaces gain a `share_token` per project with expiry.
- The click from the exported line back to the drawing: each line's reference is a URL to the visor with `?element=`.

**Done when:** a cuantificador in your office takes the generadores as-is for one real bid, and every line can be clicked to its lines on the sheet from the export.

### 2.4 OPUS and Neodata, both directions

**Have:** OPUS in (native + Excel), Neodata in (Excel, unverified), XLSX exports of presupuesto/generadores/cotización.

**Design:**
- **Writers:** `sources/opus_excel.py` and `sources/neodata_excel.py` produce the workbook each tool imports: catálogo de conceptos with clave, descripción, unidad, cantidad, and matrices/insumos when the office wants Klave's prices. Layouts are reverse-engineered from real exports of each tool (round-trip: import → export → import must be identity on the fixtures).
- **Neodata reader:** Excel-first. A native path (SQL Server backup) is out of scope until a real base is in hand.
- **Row action, no header button:** on the Conceptos sheet and on the project's Cuantificación node, «Exportar → OPUS / Neodata» lives in the existing Exportar menu.

**Done when:** a file exported from Klave imports into OPUS and into Neodata without manual fixing, verified on real installations of both (Diego's machines or the pilot office's), and a real Neodata export imports into Klave with its matrices intact.

### 2.5 The captura list

**Have:** coverage per sheet, omitidos, unpriced lines shown as such, disciplines declared as levantamiento.

**Design:** one section on the Cuantificación node and on the exported generadores: «Lo que el plano no dio», grouped by partida, with counts of elements the engine saw but could not quantify, disciplines left as levantamiento, and — once §3.2 exists — partidas expected and absent. Never silently missing.

**Done when:** a propuesta cannot be incomplete without the engineer having seen the list.

### 2.6 The label hook (for the reader spec)

Every Revisión action — confirm, exclude, reassign, mapping correction, measurement override — is appended to `labels.jsonl` per project with: element_id, sheet, the engine's proposal, the person's verdict, the features the rules computed for that element, actor, timestamp. Nothing consumes it in this spec. It exists so the flywheel spec has data from the first pilot on. Consent line in the workspace terms: drawings and corrections may be used to improve the reader; opt-out per workspace.

## 3. Killer features (second tier)

### 3.1 Revision diff — «qué cambió entre la Rev 2 y la Rev 3»

**Why:** every bid gets plan revisions; every contract gets aditivas and deductivas. Nobody has a tool for it because nobody else reads the drawing. It also gives anteproyecto→ejecutivo "what moved" for free.

**Data:** runs already exist per upload (`processed/runs/run_*`). A project gains **revisiones**: each upload of a plan set is a revisión with a label (Rev A, B, C or the date). Element identity across runs: match by (sheet, family, mark) first, then by bbox overlap ≥ 0.6 within the same frame; unmatched = added/removed.

**Output:** per concept: quantity before, after, delta, and pesos delta at the current prices; per element: added, removed, changed (dimensions); on the visor: the diff painted (green added, red removed, amber changed). Export: aditivas/deductivas XLSX in the same generador format.

**Screen:** the Cuantificación node gets a «Cambios» tab when the project has ≥ 2 revisiones; the tablero node shows «Rev C · 14 cambios». Anteproyecto→ejecutivo uses the same screen with «supuesto → leído» instead of «antes → después».

**Done when:** on Marina, an artificially edited copy of the structural sheet (3 columns moved, 1 footing removed, 1 beam resized) produces exactly those changes and nothing else, and the pesos delta equals the presupuesto recomputed.

### 3.2 Completeness check — «esperado y ausente»

**Why:** the omission that loses the bid: 1,983 m² of muro and no aplanado in the catálogo.

**Data:** a curated `data`-free table in the package, `costing/implicaciones.json`: `{"si": "zapatas", "entonces": ["plantilla", "excavación", "relleno"]}`, `{"si": "muros de block", "entonces": ["aplanado", "cadenas", "castillos"]}`, `{"si": "losa en nivel > 0", "entonces": ["escalera"]}`… each with a source and a phrase. Later versions learn the table from what offices add after the engine's pass (flywheel spec).

**Output:** the captura list (§2.5) gains a third group: «Esperado y ausente», one line per implication with the evidence («el plano trae 1,983 m² de muro»), and a row action «Agregar concepto» that opens the office's catálogo search with the family pre-filtered.

**Done when:** on prueba-1 and Marina, the check names every partida the human catálogo has that the engine's doesn't, with zero false positives on the gold sets.

### 3.3 Convocante catálogo verification — «su catálogo contra el plano»

**Why:** in obra pública the convocante's quantities are wrong and the contractor who knows where bids accordingly and files extraordinarios with proof.

**Data:** import the convocante's catálogo (XLSX; PDF via the existing table readers when the layout allows) as a project-scoped reference source of kind `convocante`. Each line is matched to the project's variants/mapped concepts with the matcher; unit gate strict.

**Output:** a table clave | descripción | cantidad de la convocante | cantidad del plano | diferencia | % | evidencia (click to the visor). Totals per partida. Export XLSX. Lines the plano can't measure say so («captura»).

**Screen:** the Cuantificación node gets a «Catálogo de la convocante» tab when one is imported; the import lives in the existing Importar… menu.

**Done when:** a real convocatoria catálogo (Diego supplies one) imports, ≥ 80 % of obra negra lines match automatically, and every mismatch shows its evidence.

### 3.4 Office índices — «tus índices en cada proyecto»

**Why:** engineers sanity-check with ratios; a bad reading or a design surprise shows up as an outlier ratio before anything else.

**Data:** per project, computed from the BoQ and the priced catálogo: kg acero / m³ concreto, m² cimbra / m³ concreto, m³ concreto / m² construido, m² muro / m² construido, $ obra negra / m² construido, and per-partida share of direct cost. Stored per project in `indices.json`; the workspace keeps the history. Published references: Guanajuato's catálogos de referencia and the paramétricos already in the app, by building type.

**Output:** a card on the project Resumen and on the Cuantificación node: each index with the workspace's median and range over its last N projects and the published reference; outliers flagged with the sentence («210 kg/m³; tus últimos cinco: 140–165»).

**Done when:** the indices on Marina and prueba-1 match a hand computation, and an injected 50 % rebar error on a fixture is flagged.

## 4. The smooth round

### 4.1 Performance (measured 2026-09-16 on Marina completo)

| finding | fix |
|---|---|
| `/geometry` returns 76,457 shapes / 255,564 points, 17.4 MB uncompressed, rebuilt from a 100 MB file on every visit; fetched three times per session | gzip middleware on the API; cache the built geometry per run on disk; split the payload into static shapes (once) and detections+verdicts (small, refreshed on review events) |
| canvas redraws all shapes synchronously on every wheel/mouse-move, and on every render (tooltip state) | one redraw per animation frame; static linework pre-rendered to an offscreen canvas per zoom band and blitted; detections/selection on a second layer; viewport culling and hit-testing through a grid index built at load |
| every edit on the big sheets refetches the whole catálogo/presupuesto; all fetches `no-store`; no memoized rows; no virtualization | patch state from the response and from SSE events instead of reloading; memoize row components; virtualize the base sheet and Revisión; `startTransition` for filters |
| — | optimistic updates on common edits; keep the previous view while refreshing; prefetch geometry on project-card hover |

**Targets (acceptance):** Marina plano first paint ≤ 1.5 s on a warm server; pan/zoom ≥ 55 fps median on a laptop; ≤ 4 MB over the wire per plano visit; edit-to-row-settled ≤ 200 ms; zero full-page refetches on edit.

### 4.2 The golden path (UX)

1. One primary «lo que sigue» action per project on the tablero and on each node; everything else secondary.
2. v1 screens front and center (subir, cuantificación, revisión, catálogo, generadores, exportar); presupuesto, programa, contrato, parámetros, plantillas, copilot appear when the project reaches them or the user asks. Catálogo shows Conceptos and Insumos first; Base, Plantillas and Salario reachable, not front.
3. The trade's words: cuantificación, elementos, generadores, concepto, matriz, P.U.; never detecciones, rule code, run, origen generada as user-facing terms.
4. Every empty screen says what it's for and offers the one action.
5. A new workspace opens on the demo project so the engineer sees a finished result before uploading.
6. One gesture grammar everywhere: row → inspector; selection → bottom bar; Esc; ↑↓ Enter ←; undo on every destructive action.
7. Every number one click from its lines on the drawing, from generadores, Revisión and the catálogo, not only from presupuesto.
8. Five-engineer think-aloud test on three tasks (upload → generadores; correct a duda; export to OPUS), timed. Diego arranges; the audit in §8 removes the obvious before they see it.

### 4.3 Collaboration rules (kept in mind, built as they're touched)

Take, don't lock (claims on dudas batches and partidas, expiring). The row you're in is never replaced under you; other rows patch in place with the actor's name. Conflicts per object: cells last-write-wins with undo; matrices and verdicts versioned with a side-by-side on stale save; reprocess queued, one at a time. Historial on the object in the inspector. Handoffs: node state + assignee, honest email. Presence says node and row, nothing more. Comment threads pinned to an element or row with mentions. Not built: cursors, co-editing, chat.

## 5. Cuts and freezes

**Cut (out of scope, removed from roadmap):** eléctrica and aire deep reading; new official source parsers; prefab index as a user-facing feature; rule codes on any client-facing surface.

**Freeze (bug fixes only, no roadmap until the spine is done):** instalaciones/cancelería/acabados-by-mark suites (levantamiento counts only); contrato (estimaciones, bitácora, convenios, finiquito); programa 45-A at current depth; copilot as is; Fase E (escalatorias por fórmula, zona, cargos, documentos 5.11); Klave-side pricing polish beyond Fases A–C; tablero canvas features; presupuesto beyond patch-not-reload.

**Kept and central:** everything in §2–§4.

## 6. Honesty rules (in addition to the prior spec §7)

- A quantity is never emitted by a model; models name elements, the geometry engine measures.
- No confidence stamped anywhere; uncertainty is a duda in the queue.
- Rendimientos and factors from plantillas stay marked «valor de referencia, revisar» until the office confirms them.
- The captura list is printed on every generador set.
- The diff never guesses identity: an unmatched element is «agregado» or «eliminado», not «modificado».
- Índices compare against the workspace's own history first; published references are labeled as such.

## 7. Testing

- Synthesis + mapping: prueba-1 and Marina → variants; Σ variants == rule quantity per fixture (gold); mapping fixtures with an OPUS base excerpt: auto ≥ 0.8, duda band, sin equivalente; alias memory round-trip.
- Writers: import → export → import identity on the OPUS and Neodata fixtures; header/column layouts golden.
- Generador references: every line has sheet, frame, grid, nivel, element_id; export ↔ visor link resolves.
- Diff: the edited-Marina fixture (§3.1) exact; anteproyecto→ejecutivo fixture from the paramétrico path.
- Completeness: implications table golden on the gold sets, zero false positives.
- Convocante: a real catálogo fixture, match rate and evidence.
- Índices: hand-computed values; injected-error flag.
- Performance: a script that measures the four targets against the Marina project and prints them; run before and after each performance task.
- Web: tsc, lint, build; keyboard path per new screen (manual checklist).

## 8. Phasing (one plan each)

| round | delivers | gate |
|---|---|---|
| R1 · Mapping | §2.2 synthesis + mapping + alias memory; §2.6 label hook | gold Σ check green; a Marina catálogo in OPUS vocabulary |
| R2 · Out the door | §2.4 writers + Neodata reader on a real file; §2.3 generador references + share link; §2.5 captura list | round-trip identity; a generador set an engineer accepts |
| R3 · Smooth | §4.1 performance; §4.2 items 1–7 (audit first, then fixes) | the four targets; five-engineer test scheduled |
| R4 · Cambios | §3.1 revision diff (+ anteproyecto→ejecutivo view) | edited-Marina fixture exact |
| R5 · Ver más | §3.2 completeness; §3.4 índices; §3.3 convocante | their done conditions |
| Pilot | one real bid through the tool beside the old way | hours saved, generadores accepted, export imported; if not, stop and rethink before R6 |
| R6+ | the reader spec (flywheel); site series (§10) | — |

Spikes, throwaway, before R1 ends: (a) leave-one-project-out feature classifier on our three sets, to inform the reader spec; (b) vector-PDF ingestion: pdf → entity stream the parser accepts, on one Marina sheet plotted to PDF.

## 9. Inputs only Diego can supply

- Plan sets from two or three other offices (blind test; also the reader spec's first corpus).
- A real Neodata export (catálogo with matrices, presupuesto sheets) and access to an OPUS and a Neodata installation to verify the writers.
- One real convocatoria catálogo (XLSX or PDF) for §3.3.
- One real bid for the pilot, and the five engineers for the test.
- Review of `plantillas_matriz.json` values.
- The OPUS vendor base license terms (still open from the prior spec).

## 10. Out of scope of this spec (recorded)

- The reader that generalizes and learns (rules + small model + large model for the long tail + per-office profiles + self-checks): its own spec after the spikes and the first foreign plan sets. This spec only guarantees the label hook and the consent line.
- The site series: estimación marked on the plano with croquis and acumulados; extraordinarios from the diff with generated matrices; consumos vs explosión with learned rendimientos; avance feeding the programa. Same element graph; after the pilot.
- Won-bid price intelligence from CompraNet (a data project, later).
- Bases de licitación reader (bounded LLM task; after the pilot).
- Replacing OPUS/Neodata document sets; Fase E.
