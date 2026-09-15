# Fase B · Básicos, cuadrillas y el primer lote OPUS — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (inline execution, Diego's standing preference). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A matrix can contain a matrix (básicos, cuadrillas) and the price flows up; an insumo can be raised, replaced and traced across every matrix that uses it; and the catálogo shows all of it in the sheet, the inspector and the selection bar — no new buttons.

**Architecture:** `insumos.kind` (insumo · basico · cuadrilla) plus `apu_components` keyed by the básico's own code; a topological recompute writes each básico's `unit_cost` as a cache with provenance "derivado de su matriz". `build_apu` recurses with a cycle guard and attaches `sub_analysis` per line. Price adjustments and replacements are journaled in `price_adjustments` and undoable. The web gets an Inspector (right panel, five sections), básico expansion inline in the matrix, cuadrillas on the Salario tab, and a selection bar on the Insumos sheet.

**Tech Stack:** as Fase A.

**Spec:** [2026-09-14-catalogo-base-y-paridad-opus-design.md](../specs/2026-09-14-catalogo-base-y-paridad-opus-design.md) §1.2, §5.2, §5.3, §5.5, §5.6, §5.7, §6.

## Global Constraints

Same fences and design rules as Fase A. Gold must stay green: básicos change nothing in engine quantities; a seed matrix never becomes a básico by migration.

---

### Task 1: `kind` on insumos, recursive APU, recompute of básicos

**Files:** Modify `costing/models.py` (`Resource.kind`, `ApuLine.sub_analysis`), `costing/apu.py` (`build_apu` recursion, depth ≤ 4, cycle error names the cycle), `costing/catalog_store.py` (schema v26, `kind` through `upsert_insumo`/`list_insumos`/`load_price_book`, `set_basico_components`, `recompute_basicos`, `insumo_uses`); Test `tests/test_basicos.py`.

**Interfaces:**
- `Resource.kind: Literal["insumo","basico","cuadrilla"] = "insumo"`.
- `ApuLine.sub_analysis: UnitPriceAnalysis | None = None`.
- `store.set_basico_components(code, components, *, actor=None)`: the insumo must be `basico|cuadrilla`; components are insumos (a básico may contain a básico); refuses cycles; recomputes.
- `store.recompute_basicos() -> dict[code, unit_cost]`: topological; a básico with a component lacking price keeps its old cost and is reported.
- `store.insumo_uses(code) -> {"concepts": [{code, description, quantity, amount, share}], "basicos": [{code, description, quantity}]}`.

- [ ] Failing tests: a cuadrilla of 1 oficial + 2 ayudantes prices at Σ; a concept using the cuadrilla prices through it; `build_apu` line carries `sub_analysis`; a cycle is refused with both codes in the message; raising the ayudante's price re-prices cuadrilla and concept; `insumo_uses` reports the concept with its share.
- [ ] Implement; `GET /catalog` payload carries `kind` and `sub_analysis` is exposed in `/catalog/apus/{code}` (add endpoint returning `build_apu` for one concept).
- [ ] Suite, gold; commit.

### Task 2: OPUS reader stops flattening

**Files:** Modify `sources/matrices.py` (`InsumoRow.kind`, `InsumoRow.components`), `sources/opus_native.py`, `catalog_store.import_matrices` and `import_matrices_as_source` + `adopt_reference_as_concept` (create básicos with their matrices before the concepts that use them); Tests in `tests/test_opus_native.py` and `tests/test_base_browse.py`.

- [ ] 1S2E round-trips as `kind=cuadrilla` with three members; auxiliares as `basico`; the "no anida básicos" problem line disappears.
- [ ] Commit.

### Task 3: Price adjustments journal — mass update and find-and-replace

**Files:** Modify `catalog_store.py` (`price_adjustments` table: id, kind `ajuste|sustitucion`, at, actor, params json, rows json; `adjust_prices(codes|filter, pct, *, vigencia, actor)`, `replace_resource(old, new, *, concept_codes=None, actor)`, `list_adjustments`, `undo_adjustment(id)`), `apps/api/routes/catalog.py` (`POST /insumos/ajuste`, `POST /insumos/{code}/sustituir`, `GET /insumos/ajustes`, `DELETE /insumos/ajustes/{id}`, `GET /insumos/{code}/uso`); Test `tests/test_ajustes.py`.

- [ ] +4 % on selected codes stamps vigencia and origin_ref "ajuste +4 % (actor)" and is undone exactly; replace moves components (merging quantities when the target already sits in the matrix) and reports affected concepts; undo restores rows; básicos recompute after both.
- [ ] Commit.

### Task 4: Cuadrillas on the Salario tab

**Files:** Modify `costing/catalog_services.py` (`apply_labor` recomputes básicos), `apps/api/routes/catalog.py` (`GET/POST/PUT /cuadrillas`), `apps/web/app/catalogo/page.tsx` (SalarioRealSection: cuadrillas list with members, cost per jornada live, create/edit inline); Tests.

- [ ] Commit.

### Task 5: Web — Inspector, básico expansion, Insumos selection bar

**Files:** Create `apps/web/components/Inspector.tsx`; Modify `page.tsx` (ConceptRows: básico rows expand inline with a chevron showing the sub-matrix; InsumosSection: checkboxes + SelectionBar with "+X %" and "Sustituir por…"; row action "Dónde se usa" opens the Inspector; ConceptRows row action "Ver" opens the Inspector with Precio · Matriz · Ficha · Dónde se usa · Historial), `lib/api.ts`, ⌘K entries.

- [ ] tsc, lint, build; commit.

### Task 6: Docs, bitácora, memory, fences, finishing menu.
