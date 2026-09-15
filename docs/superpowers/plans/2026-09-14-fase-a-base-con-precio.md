# Fase A · La base con precio — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (inline execution, Diego's standing preference). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A fresh taller opens with the official Mexican price sources loaded, browses them in one sheet, brings concepts to the taller with their provenance, and every concept and insumo in the taller says which of the four layers it belongs to.

**Architecture:** Schema v13 adds `origin` and friends to concepts and insumos. Bases stay in `price_sources` + `reference_prices` (+ new `reference_components`) and are browsed, not dumped; "Traer al taller" is the verb. New parsers (pypdfium2 text for PDFs, openpyxl for Guanajuato's Excel) join the sources registry. The server downloads a source on demand into `data/sources` and imports it, so the first-run bootstrap is one call. The web catálogo gets a Base tab, origin badges, and a selection bar.

**Tech Stack:** Python 3.14 / FastAPI / SQLite (`catalog_store.py`), pypdfium2 + pdfplumber (present), openpyxl (present), httpx (present); Next 16 web with the repo's tokens and primitives.

**Spec:** [docs/superpowers/specs/2026-09-14-catalogo-base-y-paridad-opus-design.md](../specs/2026-09-14-catalogo-base-y-paridad-opus-design.md) §1.1, §1.3, §2, §5.1, §6.

## Global Constraints

- Fences: `uv run pytest -q > /dev/null 2>&1; echo $?`, `make eval-gold` (must stay green, no recapture expected in this phase), `uv run ruff check .`, `cd apps/web && npx tsc --noEmit && npm run lint`, `npm run build --prefix apps/web` from the repo root.
- Design system: tokens only, Phosphor icons, no sync setState in effects, no ref writes during render.
- Copy in Spanish; no confidence percentages stamped on rows; every generated/imported item names its origin in the row.
- Never write into `data/` from tests (use the `data_dir` fixture).
- `data/` is gitignored: parsers are tested on fixture excerpts committed under `tests/fixtures/sources/`.

---

### Task 1: Schema v13 — origin on concepts and insumos

**Files:** Modify `packages/klave_engine/costing/catalog_store.py` (schema, migration, `load_concepts`, `list_insumos`, `create_concept`, `update_concept`, `upsert_insumo`, `import_matrices`, `adopt_reference`, `adopt_concept_reference`); Test `tests/test_catalog_origin.py`.

**Interfaces:**
- Produces: concept rows carry `origin`, `origin_ref`, `variant_of`, `spec_signature` (dict|None), `validation` (dict|None), `touched_by`, `touched_at`; insumo rows carry `origin`, `origin_ref`.
- `ORIGINS = ("oficial", "importada", "generada", "taller")`.
- Writers accept `origin`/`origin_ref` kwargs; a user edit through `update_concept(..., actor=...)` on a non-taller row sets `origin='taller'`, `touched_by`, `touched_at`.

- [ ] Write failing tests: fresh db → seed concepts are `generada` with `origin_ref='semilla Klave'`; `adopt_reference` marks the insumo `oficial` with `origin_ref='<source> · <clave>'`; `import_matrices` marks concepts and insumos `importada`; `update_concept(actor="Diego")` on an `importada` row promotes it to `taller` and records who; migration from a v12 db backfills (`source_type='publicacion'` → oficial, `import_source` set → importada, else taller).
- [ ] Add columns via the existing `ALTER TABLE` migration pattern (schema_version 13) and the backfill statement.
- [ ] Thread `origin`/`origin_ref` through the writers; expose in readers.
- [ ] Run the new tests and the full suite; commit `feat(catalogo): origen en conceptos e insumos — oficial, importada, generada o taller, con quién lo tocó`.

### Task 2: Browsable bases and "Traer al taller"

**Files:** Modify `catalog_store.py` (new table `reference_components`, `import_matrices_as_source`, `adopt_reference_as_concept`, `browse_reference`, `reference_in_taller`); Test `tests/test_base_browse.py`.

**Interfaces:**
- `reference_components(ref_id, resource_clave, description, unit, quantity, unit_cost, resource_type)`.
- `import_matrices_as_source(parse: MatricesParse, *, source_key, name, publisher, region, vigencia) -> int` writes concepts as `reference_prices` (kind `matrices`) and their components.
- `adopt_reference_as_concept(ref_id, *, code=None, phase=None, actor="") -> dict`: creates the concept (`origin='oficial'` for `precios_unitarios`, `'importada'` for `matrices`), with the published price (via `create_priced_concept`) or with matrix + insumos when components exist; refuses a duplicate clave in the taller unless `force`.
- `browse_reference(q, *, source_keys, partida, region, limit, offset) -> {rows, total}`; each row carries `in_taller: bool` (a taller concept whose `origin_ref` ends with `· <clave>`).

- [ ] Failing tests for each interface, including the OPUS parse landing as a browsable source and adoption creating a priced concept with its matrix.
- [ ] Implement; keep `import_matrices` (direct into taller) untouched.
- [ ] Suite green; commit.

### Task 3: pypdfium2 text helper and the four PDF parsers

**Files:** Create `sources/pdftext.py` (`page_lines(path) -> Iterator[(page, lines)]` via pypdfium2, and `page_tables(path)` via pdfplumber), `sources/sict_costo_directo.py`, `sources/conagua.py`, `sources/inifech.py`, `sources/guanajuato_listas.py` (materiales + maquinaria); Test `tests/test_sources_nuevas.py` with excerpts under `tests/fixtures/sources/`.

**Row grammars (from the sampled pages):**
- SICT costo directo: `LINEA CÓDIGO descripción… ` then continuation lines, then `unidad $precio` on its own line (pdfium) — code `\d{3}\.\d{2}\.\d{4}`; a line `LINEA CÓDIGO(3.2) TÍTULO` without price is a group; region `MX`, vigencia `2026-02`, kind `precios_unitarios`, partida from the código's first three digits (101 terracerías, 102 estructuras, 103 drenaje, 104 pavimentos, 105 túneles, 106 señalamiento…) in a `secciones_sict` dict.
- CONAGUA: `NNNN NN descripción UNIDAD $ precio`; `NNNN 00 descripción` is a group; unclaved lines between rows are context appended to `group_description`; region `MX`, vigencia `2026-01`.
- INIFECH: `\d{10}` code, description lines, then `UNIDAD $ p1 $ p2 … $ p15`; `price` = región 1, `extra={"regiones": {"1": p1, …}}`; region `MX-CHP`, vigencia `2026-01` (confirm from page 1).
- Guanajuato materiales (table): `Familia | Descripción | Presentación | Unidad | R1…R6` → kind `insumos`, `price` = first non-empty region, `extra.regiones` with the ones present; maquinaria (table): `Descripción | Motor | Potencia | Operación | Costo Horario` → kind `costo_horario`.

- [ ] For each parser: a fixture excerpt (10–20 rows), a failing test asserting the exact rows, implementation, green.
- [ ] Registry entries with `url`, `filename`, `vigencia`, `kind`; `available_sources` unchanged.
- [ ] Commit.

### Task 4: Guanajuato Excel tabulador (six regions, one source)

**Files:** Create `sources/guanajuato_tabulador.py`; Test in `tests/test_sources_nuevas.py`.

- Sheet columns `Código | Concepto | Unidad | Cantidad | Costo`; hierarchy rows have a short code (`ED`, `10`, `100`) and no unit; concept codes `UEC.ED.10.100.1010`; `group_clave/group_description` = the last `100`-level row; partida from the `10`-level title mapped through the shared partida vocabulary (`matching.partida_por_texto`).
- The parser receives the RI filename and reads the sibling `RII…RVI` files present in the same directory; `price` = región I, `extra.regiones` = all present; region `MX-GUA`, vigencia `2026-02`.

- [ ] Failing test with two tiny synthetic workbooks (RI, RII); implement; green; commit.

### Task 5: Download-and-import and first-run bootstrap

**Files:** Modify `apps/api/routes/catalog.py` (`POST /sources/{key}/download`, `POST /sources/bootstrap`), `sources/registry.py` (`fetch_source(spec, data_dir) -> manifest entry` with httpx, sha256, `fetched_at`); Test `tests/test_sources_download.py` with a mocked transport.

- [ ] `fetch_source` streams to `data/sources/<filename>.part`, renames, updates `manifest.json`; refuses non-2xx and empty bodies with a clear `problems` message.
- [ ] `download` endpoint = fetch + `import_reference`; `bootstrap` = every official source not yet imported, in registry order, returning per-source results (never raising on one failure).
- [ ] Tests with `httpx.MockTransport`; commit.

### Task 6: Browse API and origin in the catalog payload

**Files:** Modify `apps/api/routes/catalog.py` (`GET /catalog/base`, `POST /catalog/base/adopt`), `GET /catalog` payload gains origin fields; `apps/web/lib/api.ts` types and clients.

- [ ] `GET /catalog/base?q=&source=&partida=&region=&offset=&limit=` → `{rows, total, sources: [...]}`.
- [ ] `POST /catalog/base/adopt` body `{ref_ids: [...], phase?: string}` → `{created: [...], skipped: [{ref_id, reason}]}`; publishes `catalog_updated`.
- [ ] Tests through the FastAPI test client (existing pattern in `tests/test_catalog_api*.py`); commit.

### Task 7: Web — Base tab, origin badges, selection bar

**Files:** Modify `apps/web/app/catalogo/page.tsx`; Create `apps/web/components/OrigenBadge.tsx`, `apps/web/components/SelectionBar.tsx`, `apps/web/components/BaseSheet.tsx`.

- [ ] `OrigenBadge`: four tones (oficial · importada · generada · taller) from tokens; used in the conceptos sheet and insumos sheet as a column, and in the presupuesto partidas rows (read-only).
- [ ] `SelectionBar`: fixed to the bottom of the sheet, appears only with a selection; children are the batch actions; `Esc` clears.
- [ ] `BaseSheet`: replaces the "Fuentes de referencia" tab content: sources list collapsed at top (state, vigencia, region, "Descargar e importar" when the file is missing, "Importar" when present), then the browse sheet (search, partida chips, source and region filters, paging), row action "Traer" (`Enter` on a focused row), checkbox selection → SelectionBar "Traer N al taller"; brought rows show the `in_taller` mark.
- [ ] Empty-taller prompt on the Conceptos tab when the taller has no concept beyond the rule codes: "Trae los conceptos de tus partidas" → switches to the Base tab with the engine's partidas preselected.
- [ ] ⌘K entries: "Base: buscar en las publicaciones", "Traer al taller".
- [ ] tsc, lint, build green; commit.

### Task 8: Docs, bitácora, memory, fences

- [ ] README "Catálogo del taller" bullet mentions the Base tab and the sources that load on first run.
- [ ] `docs/auditoria-motor.md` bitácora entry for Fase A.
- [ ] Full fences; finishing menu.
