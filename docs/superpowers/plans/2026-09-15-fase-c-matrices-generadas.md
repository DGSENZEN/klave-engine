# Fase C · Matrices generadas, validadas contra el precio oficial — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (inline execution, Diego's standing preference). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A concept without a matrix gets one generated from a curated plantilla of its family, every line with its source; the generated concept is matched to a published row and its direct cost compared to the published price, and the verdict (validada · fuera de rango · sin referencia) sits on the row, is recomputed when prices move, and survives a person's edit.

**Architecture:** `costing/generacion.py` reads `plantillas_matriz.json` (in the package, curated, every rendimiento and every factor carries a `source`) and `insumos_semilla.json` (reference prices, marked "precio de referencia, validar", applied only to insumos that have no price). A plantilla is chosen by unit + keywords + elemento; quantities come from small formulas over the ficha (f'c, sección, espesor, elemento) evaluated by an allow-listed evaluator. `apu_components` gains `source`; `ApuLine` carries it. Validation runs in the store: match against reference rows of `precios_unitarios` sources with the existing matcher, compare, store the verdict in `concepts.validation`; revalidation after price changes reuses the stored reference (no re-matching). Tolerance is a workspace setting (15 %).

**Tech Stack:** as Fase A/B.

**Spec:** [2026-09-14-catalogo-base-y-paridad-opus-design.md](../specs/2026-09-14-catalogo-base-y-paridad-opus-design.md) §3.2, §6, §7, §8. Deviation recorded: the curated files live in `packages/klave_engine/costing/` (the runtime `data/` dir is gitignored and per-deployment), not in `data/`.

## Global Constraints

Same fences and design rules as Fase A/B. Gold stays green: generation never runs on import, never on seed concepts that already have a matrix, never on a taller matrix without `force`. A generated row is `origin=generada`; a person's edit promotes it and keeps the verdict. No new header buttons: row actions, the contextual callout on the Conceptos tab, ⌘K.

---

### Task 1: Plantillas, seed prices and the generator

**Files:** Create `packages/klave_engine/costing/plantillas_matriz.json`, `packages/klave_engine/costing/insumos_semilla.json`, `packages/klave_engine/costing/generacion.py`; Test `tests/test_generacion.py`.

**Interfaces:**
- `cargar_plantillas() -> list[Plantilla]`; `Plantilla(key, label, unit, keywords, elementos, cuadrillas, insumos, lines, rendimiento)`; `LineaGenerada(resource_code, quantity, source, formula)`.
- `ficha_numerica(description, spec_signature) -> dict[str, float|str]` (fc, fy, b_cm, h_cm, espesor_cm, elemento, acabado, diam_mm, material).
- `elegir_plantilla(description, unit, phase) -> Plantilla | None`.
- `generar(description, unit, phase, spec_signature=None) -> Generada(plantilla_key, lines, cuadrillas, insumos_nuevos, rendimiento, ficha)`.
- `evaluar(formula, vars) -> float` — numbers, vars, + - * / ( ), `max`, `min`, `cemento_ton(fc)`, `piezas_m2(l_cm, h_cm, junta_cm)`.

- [ ] Failing tests: each family picks its plantilla from a synthetic description; columnas 30×40 cimbra = 2(b+h)/(b·h); concreto hecho en obra f'c=150 gets cemento by table; every line has a non-empty source; unknown description → None; evaluator refuses names/attributes.
- [ ] Implement; commit.

### Task 2: Store — sources on lines, generate, validate, revalidate, tolerance

**Files:** Modify `catalog_store.py` (schema v27 `apu_components.source`; `load_template_sources`; `set_apu_components(..., sources=)` keeps sources of surviving lines; `generate_matrix(code, *, actor, force)`; `generate_missing(*, actor)`; `validate_concept(code, *, rematch=True)`; `validate_generated()`; `_revalidate_priced()` hooked after `upsert_insumo` price change, `adjust_prices`, `undo_adjustment`, `replace_resource`, `recompute_basicos`; `validation_tolerance()`/`set_validation_tolerance()`), `catalog_services.py` (`ensure_labor_priced(store, extra_categories)`), `models.py` (`ApuLine.source`), `apu.py` (`line_sources=`); Test `tests/test_validacion.py`.

- [ ] Failing tests: generate for a concept without matrix writes lines with sources, creates the cuadrilla (kind cuadrilla), prices unpriced insumos from the seed list marked "precio de referencia, validar", prices labor with CONASAMI + Fsr when no labor was applied, sets origin generada · plantilla; a published row within 15 % → validada with deviation; 15.1 % → fuera_de_rango; no row → sin_referencia; raising a price revalidates without re-matching; a person's edit promotes to taller and keeps validation; tolerance setting changes the verdict; generate on a taller matrix without force refuses.
- [ ] Implement; suite, gold; commit.

### Task 3: API

**Files:** Modify `apps/api/routes/catalog.py`: `POST /concepts/{code}/generar` (`{force}`), `POST /matrices/generar-faltantes`, `POST /concepts/{code}/validar`, `POST /matrices/validar`, `GET/PUT /matrices/validacion` (tolerance), `GET /matrices/plantillas`; `GET /catalog` apus carry `source`; `GET /apus/{code}` lines carry `source`. Tests in `tests/test_validacion.py`.

- [ ] Commit.

### Task 4: Web — verdict on the row, sources in the matrix, generate from the row, the callout

**Files:** Modify `apps/web/lib/api.ts` (types + fns), `apps/web/app/catalogo/page.tsx` (ConceptRows: `VeredictoBadge` next to OrigenBadge; matrix lines show their source; an open concept without matrix shows the row-level "Generar matriz"; a generada concept's matrix footer offers "Validar de nuevo" and "Regenerar"; ApusSection callout: "N sin matriz · Generar las que faltan" and the validation summary with the tolerance editable inline), `CommandPalette.tsx` entry "Matrices: generar las que faltan" → `/catalogo?tab=apus`.

- [ ] tsc, lint, build; commit.

### Task 5: Docs, bitácora, memory, fences, finishing menu.
