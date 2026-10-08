# Lectura estructural completa · every structural element, its inner structure, and its generadores — design

**Date:** 2026-10-08 · **Status:** approved in brainstorming, pending Diego's review of this text
**Related:** `2026-09-16-producto-v1-cuantificacion-design.md` (the product: generadores fed into OPUS/Neodata), `2026-10-04-lector-que-aprende-design.md` (the reader that learns; §6.4 here feeds it)
**References Diego gave:** `AC Cimentación Marina.xlsx` (the office's hand steel takeoff for the foundation), `Tema 2.2.4 Cuantificacion Elementos Estructurales Tabla.pdf` (tabla de varillas + figures A–D)

## 0. The problem, in one sentence

Klave finds most structural elements and even reads most of their armado, but it does not hold an element together — its identity, its geometry, its section, its height or length, and what is inside it — so readings get dropped between stages, gaps are filled silently or not at all, and the generadores are less accurate than the drawing allows.

**Goal:** the complete structure (cimentación and superestructura) read element by element, with every quantity (excavation, plantilla, concrete, cimbra, steel, laps, welds) computed from that element by a written formula, and every value traceable to the place in the drawing it came from. **Accuracy is measured against the drawing itself** (its cuadros, details, notes, cotas and counts must agree with each other and with what Klave read), plus Diego's workbook as the reference for foundation steel.

## 1. Decisions taken (brainstorming 2026-10-08)

| # | decision |
|---|---|
| 1 | **Scope is the complete structure**, not only steel: every structural family and every generador concept that comes from it. |
| 2 | **Approach A: one structural model per project** (definitions + placements + rules → elements), with the drawing's own consistency checks as the accuracy measure. Rejected: B, patching each family where it is (the join and the checks would be rebuilt per family); C, AI transcription of detail sheets (not reproducible, needs a key, breaks "the model may doubt, never measure") — AI stays a gap-filler marked `ia`. |
| 3 | **Reference truth = drawing-derived checks**, spot-checked by Diego; the corrected steel workbook is the reference for foundation steel. |
| 4 | **Every value carries its source**; precedence fixed (§3.1); losing values are kept so a disagreement can be shown. |
| 5 | **Laps and welds are explicit lines**: lap kg as their own rows in the acero generador, butt welds (#8 and larger, per Marina note 4) as a PZA concept. Waste is a separate visible setting, default 0 %. |
| 6 | **Nothing is invented.** A missing value becomes a `supuesto` with a check; an unparseable text stays raw with an `aviso`. |
| 7 | **Built in rounds E0–E4** (§10), each fenced by gold. |

## 2. What exists and what's missing (measured on Marina, 2026-10-08)

Run `run_e0a51785` of `marina_lote_04_estructural_d1cd5ec8` (43,969 entities, 2,151 detections).

| family | found | missing |
|---|---|---|
| castillo 336, columna 23 | mark + section on all | armado read from details for most marks, but dropped by the steel stage (below) |
| trabe 183, contratrabe 94 | mark + section (272/277) | 10 CTA marks with no armado |
| pilote 23 | found, marked | no section, no length — priced as pieces; the workbook has 35×35–70×70, 8 m, zoned stirrups. Marina's notes say pile characteristics are "en los detalles" (`DETALLE DE PILOTE P-1…`), which Klave does not read |
| zapata/dado 38 | found | **none joined to its D-mark**; dado depth and armado therefore never reach the element |
| muro 63, muro_concreto 4 | found | no thickness; MC armado is only a mesh spacing |
| losa 83 panels | 53 with thickness | losa de cimentación (143.6 m²) and maciza (108.5 m²) without armado |
| excavation | 10.8 m³ (zapatas only) | Marina has a **sótano** ("LOSA ESTRUCTURAL DE SÓTANO", levels from NTC+1.45, 3.9 m muros de contención); the dig is not measured |

**Armado:** `schedules.json` has a definition for 45 of the 57 marks in the workbook (C, K, P, D, MC). The steel stage parses 60/66 longitudinal texts but **only 22/59 stirrup texts** — zones (`2E#3EXT@10 CENTRO@20`), several stirrups per set (`2E`, `3E`, `4E`), estribo + grapa (`EYG#2@15`, `2E+1G#3…`), two bar groups (`4#4+2#3`), and stirrups without spacing (`E#3`, `E#4`) are dropped. Columnas, pilotes, dados and muros de carga get no steel at all.

**Rules in the drawing, unused:** Marina's `02 ESTRUCTURAL` carries the TABLA DE VARILLAS and NOTAS GENERALES DE ESTRUCTURA as real text inside blocks `NOTAS DE CIMENTACIÓN`, `ESPECIFICACIONES  EST-PB`, `ESPECIFICACIONES EST-AZOTEAS` (three identical copies). The table equals the PDF except #8, where Marina lists LT1 115 / LT2 150 while its own note 4 says only up to #6 may be lapped and #8+ is welded (Fig. D). Notes also give covers (5 cimentación, 5 columnas, 4 trabes/losas, 3–5 castillos/dalas/cerramientos), stirrup hooks (135° + 10Ø; grapas 180° + 10Ø), first stirrup at 6 cm from the paño, no laps in nudos or within two peraltes, and a detail «ANCLAJE DE CASTILLO 100 CM». Klave uses none of it (single cover 2.5 cm, 7.5 cm hooks, flat 40 cm anchorage, no laps).

## 3. The structural model (`klave_engine/estructura/`)

Runs in the pipeline after detection, taxonomy and `build_schedule_inventory`, before costing. Writes `estructura.json` per run: `{reglas, definiciones, elementos, verificaciones, resumen}`.

### 3.1 `Dato` — a value with its source

`Dato[T] = {valor: T, fuente, hoja, texto | entidades, alternativas: list[Dato[T]]}`.

Precedence (higher wins, losers kept in `alternativas`):

`humano` > `cuadro` > `detalle` (text in a detail) > `seccion_dibujada` (geometry read inside the section, §6.1) > `nota` > `medido` (geometry in the planta) > `regla` (project rules applied) > `supuesto` (Klave's default, always flagged) — with `ia` only filling a field nothing else filled, marked *por confirmar*.

`humano` is a decision taken in Revisión (§4.3). No confidence number is stored or shown (doctrine).

### 3.2 `Definicion` — one per mark

`mark`, `familia`, `seccion` (b×h | diámetro | espesor), `extension` (pilote length, dado peralte, muro height, losa thickness), `fc`, `armado: Armado`, each a `Dato`. Built from today's `ElementSpec`s (extended: `schedules.py` stops collapsing to strings and emits structured armado) and, from E3, from the drawn section. Family-level notes ("DALA 15x30 4#3 E#2@20") are definitions with `mark = familia`.

### 3.3 `Armado` — structure, not text

- `longitudinales: list[GrupoVarillas{cantidad, numero, posicion: esquina|cara|lecho_sup|lecho_inf|ambos}]`
- `estribos: list[JuegoEstribos{forma: perimetral|rombo|interior|grapa|liga, numero, por_juego, zonas: list[Zona{tramo: extremos|centro|longitud_m, separacion_m, longitud_m?}]}]`
- `parrillas: list[Parrilla{numero, separacion_m, lecho: sup|inf|unico, sentidos: ambos|x|y}]`
- `texto_original` and `avisos` (what could not be parsed).

**Grammar (from Marina's real strings, all must parse):** `8#8`, `10#8`, `1#3`, `4#4+2#3` · `E#2@15`, `2E#2@15`, `2E#3@20`, `3E#3@20` · `2E#3EXT@10 CENTRO@20`, `3E#3EXT@10 CENTRO@20`, `4E#3EXT@10 CENTRO@20`, `2E+1G#3EXT@10 CENTRO@15` · `EYG#2@15` (estribo y grapa) · `E#3`, `E#4` (no spacing → `aviso` + check 7) · `#4@20`, `#4@15` as a muro or losa mesh (never as longitudinal bars) · slab labels already read by `slab_rebar_kg_per_m2` (`#4@20 A/S L.S. y L.I.`).

**Stirrup shapes before E3.** `nE` gives how many stirrups per set, not their shapes. Until the drawn section is read, shapes follow the workbook's practice as `supuesto`: 4 bars → 1 perimetral; 6 bars in a rectangle → perimetral + interior (or grapa when `G`); 8 bars → perimetral + rombo; 10–12 bars → perimetral + rombo + interior. The drawn section (§6.1) replaces the supuesto.

### 3.4 `Reglas` — per project

- `tabla_varillas[numero] = {LA1, LA2, LT1, LT2, LG1, LG2, LG3, r}` (cm)
- `recubrimiento[familia]` (a range "3.0 a 5.0" → the minimum, with an `aviso`)
- `ganchos`: estribo 135° + 10Ø, grapa 180° + 10Ø, 90° variant 13Ø
- `soldar_desde_numero` (Marina: 8), `traslape_max_numero` (Marina: 6)
- `primer_estribo_m` (Marina: 0.06), `sin_traslape_en_nudos_peraltes` (Marina: 2)
- `anclajes_declarados` (Marina: castillo 1.00 m), `fc[familia]`, `plantilla_espesor_m`, `nivel_desplante[...]`, `nivel_terreno_natural`, `longitud_comercial_m` (supuesto 12)
- each a `Dato`. Read from tables and numbered notes (§6.2, §6.3); when a project has no table, the standard table (the PDF's values, #8+ without laps) applies with source `supuesto`.

### 3.5 `Elemento` — placement + definition + rules

A placement is today's `Detection` (mark, family, planta/view, ejes, bbox, measured geometry, stable `element_id` from F1). The join is by normalized mark (`K-15A.1` ≡ `K15A.1`); family-level definitions apply when no mark definition exists. Resolved, each as a `Dato`: `seccion`, `longitud_o_altura` (definition → levels/cortes → measured), `volumen_m3`, `cimbra_m2`, `armado`, `continuidad` (same mark at the same position in the planta above → continues; used for splices), `apoyos` (what each end bears on: column, wall, cimentación, nothing).

**Compatibility.** In E0–E1 the model writes its resolved values onto the detections the BoQ already reads (as `apply_schedule` does today: `section_cm`, `section_area_du2`, heights, lengths). Concepts, gold and exports keep working while steel (E0) and cimbra (E2) move to reading `Elemento` directly.

## 4. Checks (`estructura/verificaciones.py`) — the accuracy measure

Each finding: `{tipo, severidad: bloquea|duda|aviso, elementos[], datos_en_conflicto[], hoja, bbox, texto}`.

| # | check | severity |
|---|---|---|
| 1 | mark placed in a planta, defined nowhere | bloquea |
| 2 | mark defined, never placed | aviso |
| 3 | section disagreement — cuadro vs detail cotas vs planta geometry, beyond 1 cm or 5 % | duda |
| 4 | armado disagreement — two texts, or text vs bars drawn in the section (E3) | duda |
| 5 | count disagreement — a stated count ("4 PILOTES", "(X2)", "No. piezas") vs placements | duda |
| 6 | levels — storey heights, NTC/NPT and cortes inconsistent; element taller than its storey | duda |
| 7 | critical value missing — pilote without length, muro without thickness, losa/contratrabe without armado, dado not joined to its mark, stirrup without spacing; says which `supuesto` replaced it | bloquea if no supuesto exists, else duda |
| 8 | the drawing contradicts itself — table vs notes, copies of a block that differ | duda |
| 9 | armado breaks the rules — bars do not fit in the section with the cover, a lap where the rules require a weld | aviso |

### 4.1 Scorecard «Lectura estructural»

Per family: placements · joined to a definition · share of critical values from the drawing (not `regla`/`supuesto`/`ia`) · open findings by severity · **money at stake** (|Δ quantity between the winning and losing values| × P.U. when the concept is priced, otherwise Δ quantity). Ranked by money at stake. Shown at the top of Revisión (no new header buttons); `GET /projects/{id}/estructura` returns `resumen` + `verificaciones`; `GET /projects/{id}/estructura/elementos?familia=` returns elements.

### 4.2 In Revisión

Each `duda`/`bloquea` is a doubt on its element with both values and their sources side by side; `?bbox=` opens the visor on each source.

### 4.3 Deciding

«Usar este valor» stores a `humano` `Dato` keyed by mark + field in `processed/estructura_decisiones.json` (definition level: applies to every placement of that mark) and writes a label to `labels.jsonl`. Decisions survive reprocess; a decision whose mark disappears becomes a warning, like orphaned reviews today.

## 5. Generadores from elements

Every row: element (mark, planta, ejes) · dimensions with their sources · formula · quantity. Formulas are written in the row («2(0.45−2·0.05)+2(0.45−2·0.05)+2·10·0.0095»).

### 5.1 Concrete

Section × length/height. Nodes are never counted twice: columns own the node; trabes and contratrabes are measured paño a paño; dados use their peralte; pilotes their stated length; muros length × height × thickness; losas area × thickness (losa de cimentación net of contratrabe footprints).

### 5.2 Cimbra (contact area)

Columns/castillos: perimeter × height. Trabes: two sides less slab thickness + bottom. Contratrabes and dados: sides. Losas: underside (not a slab cast on the ground). Muros: two faces. Stays on the existing EST-008/009/010/011, CIM-006/009 concepts.

### 5.3 Excavation, plantilla, fill, haul

Excavation = footprint of foundation and sótano × (nivel de terreno natural − nivel de desplante) + over-dig margin (`sobreexcavacion_m`, supuesto 0.30 m per side). Missing terrain level or margin → `supuesto` + check 7. Plantilla = area bearing on ground × `plantilla_espesor_m` (Marina 5 cm). Relleno and acarreo derived as today (CIM-004/005, swell only on the haul).

### 5.4 Steel

- **Bar data:** diameter = número/8 in × 0.0254; kg/m by número per NMX-B-506 (`BAR_KG_PER_M`).
- **Longitudinal:** cantidad × (length + anchorage at each end). An end anchored straight adds LA1 or LA2 (LA2 when the bar has more than 30 cm of concrete under it); an end in escuadra (note 6, Fig. A) adds LG1 + LG2; a declared anchorage (Marina «ANCLAJE DE CASTILLO 100 CM») wins. Bend allowances are ignored, and the row says so.
- **Splices:** a bar run longer than `longitud_comercial_m`, and a column/castillo bar where `continuidad` says the mark continues to the storey above, gets a splice. Up to `traslape_max_numero` it adds LT1/LT2 as **lap rows**; from `soldar_desde_numero` it adds **one weld per bar per splice** (PZA). Splices are never placed in nudos (rule), which only affects position, not quantity.
- **Stirrups — length per shape**, inside the family's cover r, plus hooks = 2 × ROUNDUP(10Ø, cm) (135°; 180° for grapas; matches the workbook: #2 0.14, #3 0.20, #4 0.26):
  - perimetral: 2(b−2r) + 2(h−2r)
  - rombo: 2(b−2r)/√2 + 2(h−2r)/√2
  - interior: perimeter of the rectangle through the bars it ties, offset by r (workbook supuesto for 12 bars: 2(h−2r) + 2(b−2r)/3)
  - grapa / liga: one leg, (b−2r) or (h−2r)
  - from E3, the drawn polyline's length replaces the formula.
- **Stirrups — count:** positions are laid out along the element from `primer_estribo_m`, zone by zone (ends from the detail or, if absent, NTC confinement length max(b, h, L/6, 0.60 m) as `supuesto`; centre @ its spacing), and counted — no "+1 per zone" ambiguity.
- **Mesh (parrillas):** per direction and layer, bars = ROUNDUP(clear width / s) + 1, each the clear length + end anchorage (LG for escuadra).
- **Output:** the acero generador per element and per bar size (like the workbook), lap rows, a weld count, and a summary of kg and t per bar size. Steel concepts per family (castillos/columnas, trabes/contratrabes, cimentación, losas, muros) carry **variants by bar size** (`BoqLine.variants`, v1 R1) so an office's per-diameter catálogo maps directly. Welds get a new PZA concept. Concept codes are assigned in the plan.
- **Waste:** `desperdicio_pct`, visible, default 0 %.

## 6. Reading the inner structure

Deterministic geometry and text rules. `ia` fills only what nothing else filled.

### 6.1 Section details (`estructura/secciones.py`, E3)

Inside each detail frame (`frames.py`), for each section outline with a mark and cotas:
- **Detail scale** = cota text value ÷ measured length (a 1:20 detail on a 1:50 sheet still measures right).
- **Bars:** small circles, donuts, hatched dots, including exploded block children (`parent_insert`) → count and position (corner/face); size only when drawn to scale.
- **Stirrups:** closed polylines inside the outline, classified: offset ≈ cover → perimetral; 45° square through mid-face bars → rombo; smaller rectangle around a subset → interior; open polyline with hooks → grapa/liga. The drawn cover = outline-to-perimetral offset.
- **Alzados:** stirrup lines grouped by cotas → zone lengths and spacings.
- Output: a `Definicion` with source `seccion_dibujada`: counts and shapes from the drawing, sizes from the text; check 4 compares.

### 6.2 Tables (`estructura/tablas.py`)

One reader for tables made of grid lines + text cells, inside model space or inside blocks: TABLA DE VARILLAS, cuadros de castillos/columnas/dados/pilotes, and cuadros whose cells hold section sketches (read with §6.1). Columns are matched by header tokens (VARILLA, LA1…, MARCA, SECCIÓN, ARMADO, ESTRIBOS); rows anchored on the first column's values. (A prototype on Marina rebuilt all 8 rows × 9 columns of the three copies exactly by anchoring rows on the VARILLA column.)

### 6.3 Numbered notes (`estructura/notas.py`)

NOTAS / ESPECIFICACIONES blocks are parsed into `Reglas`: covers by family, hooks, weld threshold, lap limit, first stirrup, f'c, plantilla, pile length, desplante. Line-wrapped notes are rejoined by their number. Repeated copies merge; differing copies or a note against a table → check 8.

### 6.4 Content signature for symbol blocks (`estructura/firmas.py`, E4)

Per block definition, a name-independent signature: counts of child entity types, hatch-fill ratio, closed vs open shapes, normalized shape hash (scale- and rotation-invariant). Used to recognise placement symbols (pile octagons, column markers, castillo hatches) whatever the office calls the block, and added to the lector's features (S0 showed names do not transfer between offices; geometry does).

## 7. Reference and measurement

- **Drawing-derived:** the scorecard and the check counts (§4) are the accuracy measure for every family.
- **Foundation steel:** a corrected reference built by script from `AC Cimentación Marina.xlsx` — the workbook's own inputs, recomputed with these corrections, each documented:
  1. Pilares `M60` uses `$F$22` (2 m) for P-5's 6 m zone → use `M22`.
  2. Pilares row 78 multiplies by the wrong «N° Elementos» cells (no effect while all are 1) → own column.
  3. Pilares lower table (C-01…C-08) `#REF!`/`#VALUE!` → excluded until repaired.
  4. Muros bar counts not rounded (50.67) → ROUNDUP.
  5. Losa de cimentación (1/s + 1) bars **per metre** → per span (§5.4); the difference is shown.
  6. Zone "+1 each" double count → positions laid out (§5.4).
  7. «1/4"» weighed at 0.384 kg/m (that is 5/16") → 0.248 kg/m — **to confirm with Diego**.
  8. Castillo stirrup sizes K-1…K-3A step 1/4, 3/8, 1/2, 1/2, 3/4 column by column (looks like an Excel autofill); the drawing reads E#2 for K-1…K-8 → **the drawing wins; Diego spot-checks**.
  9. Dados cover 7.5 cm vs Marina note 4's 5 cm for cimentación → **to confirm** (office choice or error).
- **Fence:** E1 must match the corrected reference within ±1 % in kg per bar size per element, for every workbook element Klave places.
- **Gold:** each `evals/gold/*.json` gains an `estructura` block — per family placements, joined, share from the drawing, finding counts by type (deterministic → exact). Marina also pins the verified armado per mark (`source: human`, Diego's spot-checks survive recapture). Intentional detector changes recapture and say so in the commit.

## 8. Honesty rules

- Nothing is invented; every `supuesto` is visible in the row, the element and the scorecard.
- A higher source wins, but every conflict is recorded and shown.
- No confidence number is shown anywhere; uncertainty is a duda.
- `ia` values are *por confirmar* and never outrank a drawing source.
- A broken detail, table or note never fails the run; it becomes a finding.
- Rule codes never appear on client-facing documents (existing rule).

## 9. Testing

- **Parsers:** every Marina armado string in §3.3 as a unit case; the notes parser on Marina's `NOTAS DE CIMENTACIÓN` text; the table reader on all three Marina copies (identical 8×9 grids).
- **Formulas:** each workbook element (Pilares P-1…P-5 by zone, Columnas C-1…C-3, castillos K-*, Dados D-*, Muros MC-*, Losa cim.) as a test: its inputs → the corrected reference's kg per bar size.
- **Geometry (E3):** small synthetic DXFs — a 45×45 section with 8 bars, perimetral + rombo, a 1:20 detail inside a 1:50 frame, a cuadro with section sketches.
- **End to end:** gold on Marina, PRUEBA-1 and Torre (so nothing is tuned to Marina alone); money gold recaptured when steel changes, stated in the commit.
- **Time:** the model + checks add ≤ 10 % to Marina's pipeline time, measured each round.

## 10. Phasing (one plan each)

**E0 · Foundation of the model.** `Dato`, `Definicion`, `Armado` + parser, `Reglas` from notes and table, `Elemento` join, checks 1, 2, 7, 8, scorecard + API + Revisión panel, gold `estructura` block. Steel stage reads structured armado (zones, several stirrups per set, grapas, two bar groups).
*Done when:* all 59 Marina stirrup texts parse (or carry an explicit aviso); Marina `Reglas` = 8 table rows, covers for 4 family groups, weld from #8, first stirrup 6 cm, castillo anchorage 100 cm, the #8 contradiction flagged; scorecards for Marina, PRUEBA-1, Torre; gold recaptured.

**E1 · Cimentación complete.** Pilotes from `DETALLE DE PILOTE` (section, length, zoned armado), dados joined to D-marks, contratrabe armado, losa de cimentación mesh, muros de contención, excavation/plantilla from levels, steel by §5.4 with lap rows and welds.
*Done when:* every Marina pilote and dado is joined to a definition or carries a `bloquea` naming what is missing; excavation shows its levels and supuestos; foundation steel within ±1 % of the corrected reference.

**E2 · Superestructura.** Columnas/castillos with `continuidad` (splices per storey), trabes paño a paño with escuadra anchorage, losas (maciza, reticular nervaduras, vigueta), dalas/cadenas/cerramientos, block wall thickness, cimbra from elements, checks 3, 5, 6.
*Done when:* Marina and PRUEBA-1 superstructure families have scorecards with no unexplained `bloquea`; no regression in gold.

**E3 · Drawn sections.** §6.1 + §6.2 cuadros with sketches, check 4.
*Done when:* on Marina's K and C details, bar counts and stirrup shapes are read from the drawing and every disagreement with the text is a listed duda.

**E4 · Block signatures.** §6.4, placements by signature, features into the lector.
*Done when:* LOPO on the S0 setup measures the signature's effect on castillo/columna/pilote.

## 11. Out of scope

Structural steel (Marina has HSS 10"×10" columns and IPR 12"×8" beams: profiles, plates and welds get their own spec) · escalera armado quantities (escaleras are read as definitions; their steel comes later) · instalaciones · precast beyond vigueta y bovedilla · progress billing.

## 12. What Diego owes / open items

- Spot-check list after E0: castillo stirrup sizes (workbook vs drawing), K-5/K-6 sections (workbook 40×20 vs drawing 20×30), D-marks without a definition.
- Confirm the «1/4"» weight (0.384 vs 0.248 kg/m) and dados cover (7.5 vs 5 cm).
- Ask Marina's calculista about #8 laps (table lists them; note 4 forbids them).
- Natural ground level for Marina if the drawing does not state it (otherwise excavation stays a `supuesto`).
