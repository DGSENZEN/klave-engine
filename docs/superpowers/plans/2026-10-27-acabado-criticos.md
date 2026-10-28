# Acabado ola 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every way Klave silently loses saved work, strands a user at a dead end, or lets one keystroke or click destroy a justified record.

**Architecture:** Pure decision logic moves into small `lib/` modules with node unit tests (the web suite's pattern: `apps/web/tests/*.test.mjs`, compile list in `tests/run.mjs`). One new API route with pytest coverage. UI wiring is proved by one new Playwright spec, `e2e/acabado.spec.ts`, on a per-test obra de ejemplo, plus a browser walk.

**Tech Stack:** FastAPI + pytest; Next 16 / React 19; node:test; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-27-acabado-criticos-design.md`

## Global Constraints

- Visible copy is es-MX. Element verdicts: Confirmar / Excluir. Reversible removal: Quitar. Permanent removal: Eliminar.
- Every destructive or authority confirmation uses the existing `components/ConfirmDialog.tsx` (Cancel gets initial focus).
- Visor keys: ← → C Q unchanged. X opens the motivo field instead of excluding.
- ESLint `react-hooks/set-state-in-effect`: no synchronous setState inside effects.
- Strings fixed by the spec, verbatim:
  - «Sin análisis guardado: valores de partida»
  - «Capturar la estimación 1»
  - «Asentar la nota N — no se podrá editar ni quitar» / «Asentando…»
  - «Se está reprocesando. Lo que ves es la lectura anterior; se actualiza al terminar.»
- Run commands from the worktree root `/Users/tinkertailorr/KlaveProjects/klave-engine-ux` unless a step says otherwise. Web commands run in `apps/web`.

## Review Focus

1. A live reload that fails *after* a successful load must keep the loaded counts and stay saveable. Only a never-loaded base blocks saving.
2. Reprocess triggered by the same user from Resumen: their own screen must also stay mounted with the notice, not only collaborators' screens.
3. X pressed while the motivo field is already open must type an «x» into it, not trigger anything.
4. `POST …/estimaciones/primera` on a catalog whose rows have no `unit_price` must still create the estimación with price 0, not fail.
5. A bulk «Quitar revisión» at exactly 50 rows: no dialog. At 51: dialog.

---

### Task 1: Conteos never overwrite what failed to load (C1)

**Files:**
- Create: `apps/web/lib/conteos.ts`
- Modify: `apps/web/app/proyecto/[id]/revision/page.tsx` (conteos load `:912-935`, `guardarFila` `:1014-1035`, table render near `:1108`)
- Test: `apps/web/tests/conteos.test.mjs`; add `lib/conteos.ts` to `tests/run.mjs`

**Interfaces:**
- Produces:
  - `type CargaConteos = { base: ConteosDeProyecto | null; error: boolean }`
  - `alCargar(prev: CargaConteos, r: { ok: true; data: ConteosDeProyecto } | { ok: false }): CargaConteos` — success sets base and clears error. Failure keeps `prev.base` and sets `error: true`.
  - `puedeGuardar(c: CargaConteos): boolean` — `c.base !== null`.

- [ ] **Step 1: Write the failing tests**

```js
test("un fallo sin carga previa deja la base vacía y no se puede guardar", () => {
  const c = alCargar({ base: null, error: false }, { ok: false });
  assert.equal(c.base, null); assert.equal(c.error, true); assert.equal(puedeGuardar(c), false);
});
test("un fallo en una recarga conserva lo ya cargado y se puede guardar", () => {
  const base = { hojas: [{ hoja: "E-01", familia: "column", contado: 12 }] };
  const c = alCargar({ base, error: false }, { ok: false });
  assert.deepEqual(c.base, base); assert.equal(c.error, true); assert.equal(puedeGuardar(c), true);
});
test("una carga buena limpia el error", () => {
  const c = alCargar({ base: null, error: true }, { ok: true, data: { hojas: [] } });
  assert.equal(c.error, false); assert.equal(puedeGuardar(c), true);
});
```

- [ ] **Step 2: Run them and watch them fail.** Run: `npm test` (in `apps/web`). Expected: FAIL, module `lib/conteos` missing.
- [ ] **Step 3: Implement `lib/conteos.ts`. Wire revision/page.tsx:**
  - The load and the live reload go through `alCargar`. Never `setConteos(CONTEOS_VACIOS)` on failure.
  - With `!puedeGuardar`, the table inputs are disabled and a `Callout tone="danger"` reads «No se pudieron cargar los conteos guardados» with an action «Reintentar» that reloads.
  - `guardarFila` returns false without a PUT when `!puedeGuardar`.
  - Saving no longer clears the load error.
- [ ] **Step 4: Run the tests.** Run: `npm test`. Expected: all pass.
- [ ] **Step 5: Commit.** Message: `fix(revision): los conteos que no cargaron no se pueden sobrescribir`

### Task 2: Costo horario defaults only when there is no saved analysis (C2)

**Files:**
- Create: `apps/web/lib/costoHorario.ts`
- Modify: `apps/web/app/catalogo/page.tsx:3395-3452` (dialog load and footer)
- Test: `apps/web/tests/costo-horario.test.mjs`; add to `tests/run.mjs`

**Interfaces:**
- Produces: `inicialCostoHorario<T>(r: { ok: true; data: T | null } | { ok: false; status?: number }, defaults: T): { params: T | null; origen: "guardado" | "partida" | "error" }`
  - `ok` with data → `"guardado"`.
  - `ok` with null, or `!ok` with status 404 → defaults and `"partida"`.
  - Any other failure → `params: null`, `"error"`.

- [ ] **Step 1: Write the failing tests:** guardado; 404 gives partida; null data gives partida; a 500 or network failure gives error with null params.
- [ ] **Step 2: Run them.** Expected: FAIL, module missing.
- [ ] **Step 3: Implement. In the dialog:**
  - `"error"` shows a `Callout` with «Reintentar» and disables «Guardar y aplicar».
  - `"partida"` shows «Sin análisis guardado: valores de partida» above the form.
  - Distinguish 404 through `ApiError.status` from `lib/api.ts`.
- [ ] **Step 4: Run them.** Expected: pass.
- [ ] **Step 5: Commit.** Message: `fix(catalogo): el costo horario no escribe valores de partida sobre un análisis que no cargó`

### Task 3: First estimación from the contract catalog (C3)

**Files:**
- Modify: `apps/api/routes/obra.py` (new route beside `crear_siguiente` `:249`)
- Modify: `packages/klave_engine/costing/estimaciones.py` (new pure function)
- Modify: `apps/web/lib/api.ts` (beside `siguienteEstimacion` `:1259`)
- Modify: `apps/web/app/proyecto/[id]/estimaciones/page.tsx` (`:72-200`)
- Test: `tests/test_estimaciones.py`, `tests/test_obra_api.py`

**Interfaces:**
- Produces:
  - `primera_desde_catalogo(renglones: list[dict], inicio: str, fin: str, monto_contrato: float) -> Estimacion`. `numero=1`. One `RenglonEstimado` per row: `clave`, `description`, `unit`, `quantity_contract=quantity`, `unit_price=unit_price or 0.0`.
  - `POST /projects/{id}/estimaciones/primera?inicio=&fin=` returns `{estimacion, resumen}` like `siguiente`. It returns 409 `{error_type: "sin_catalogo"}` without catalog rows and 409 `{error_type: "ya_hay_estimaciones"}` when the list is non-empty. It does not save: the draft is saved through the existing PUT, same as `siguiente`.
  - `primeraEstimacion(id: string, inicio: string, fin: string): Promise<EstimacionConResumen>` in `lib/api.ts`.

- [ ] **Step 1: Write the failing tests.**
  - `test_primera_estimacion_sale_del_catalogo`: two rows, one without price. Asserts `numero == 1`, the clave order, `quantity_contract`, `unit_price == 0.0` for the unpriced row, and `monto_contrato`.
  - API, `test_primera_estimacion_sin_catalogo_es_409`.
  - API, `test_primera_estimacion_con_estimaciones_es_409`.
  - API, `test_primera_estimacion_trae_los_renglones_del_catalogo`. Save a catalog via the existing PUT/POST used in `test_obra_api.py`.
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_estimaciones.py tests/test_obra_api.py -q`. Expected: FAIL (function or route missing).
- [ ] **Step 3: Implement the function and the route. Web:**
  - Empty state with a catalog: primary «Capturar la estimación 1». Without one: a link «Cargar el catálogo del contrato» to `/proyecto/{id}/contrato`. The page reads `getCatalogoConvocante`.
  - «Nueva estimación» shows only when `lista.length > 0`. Errors go through `apiMessage`. The «primera estimación» text is used only for `sin_estimacion_previa`.
  - A failed list load shows a `Callout` with «Reintentar» instead of the skeleton.
- [ ] **Step 4: Run them.** Expected: pass. Then run `npm run typecheck`. Expected: ok.
- [ ] **Step 5: Commit.** Message: `feat(estimaciones): la primera estimación sale del catálogo del contrato`

### Task 4: Asentar nota asks and can't double-submit (C4)

**Files:**
- Modify: `apps/web/app/proyecto/[id]/bitacora/page.tsx:159-170, 305` (and the opening note)

- [ ] **Step 1: Write the failing e2e** in `e2e/acabado.spec.ts`: `test("asentar una nota pide confirmación y un doble clic asienta una sola")`. Steps: open the bitácora (via API helper, see Task 9), draft a note, double-click «Asentar nota». Expect the dialog «Asentar la nota 2 — no se podrá editar ni quitar». Confirm. Expect exactly one new note in `GET /projects/{id}/bitacora`.
- [ ] **Step 2: Run it.** Expected: FAIL (no dialog).
- [ ] **Step 3: Implement.** `ConfirmDialog` before `asentar()`. A `busy` flag disables the button and shows «Asentando…». Same for the opening note.
- [ ] **Step 4: Run it.** Expected: pass.
- [ ] **Step 5: Commit.** Message: `fix(bitacora): asentar una nota pide confirmación y no se duplica`

### Task 5: Reprocesar and Cerrar nodo confirm; open screens stay mounted (C5)

**Files:**
- Create: `apps/web/lib/procesando.ts`
- Modify:
  - `apps/web/app/proyecto/[id]/layout.tsx:95-215`
  - `apps/web/components/GateGuard.tsx`
  - `apps/web/components/Tablero.tsx:613-623`
  - the three Reprocesar buttons: `app/page.tsx:787-797`, `resumen/page.tsx:137-148, 218`, `plano/page.tsx:517-528`
- Test: `apps/web/tests/procesando.test.mjs`

**Interfaces:**
- Produces: `vista(estado: string | undefined, artefactos: boolean, yaAbierta: boolean): "shell" | "shell-reprocesando" | "procesando" | "fallo"`
  - `"processed"` → `"shell"`.
  - queued or running with `artefactos || yaAbierta` → `"shell-reprocesando"`.
  - queued or running otherwise → `"procesando"`.
  - failed with `artefactos` → `"shell"` (existing warning). Failed otherwise → `"fallo"`.
- The `job_updated` handler merges into the previous status, keeping `artifacts_available`.

- [ ] **Step 1: Write the failing tests:** one per row above, plus «reprocesar desde dentro: yaAbierta sin artefactos en el evento → shell-reprocesando».
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - The layout renders through `vista`. For `"shell-reprocesando"`, the shell plus a fixed `Callout tone="info"` with the spec's notice.
  - GateGuard: if the gate was open on first render of this mount and later closes, keep the children and show a `Callout tone="warning"`: «{actor} cerró este nodo; lo que guardes se conserva». The lock card shows only on a fresh mount.
  - `ConfirmDialog` before every Reprocesar: «Reprocesar el proyecto — vuelve a leer los planos para todos los que lo tienen abierto». Before «Cerrar nodo»: «Cerrar {nodo} — quien esté trabajando ahí verá el aviso».
- [ ] **Step 4: Run them.** Expected: pass. Then add to `e2e/acabado.spec.ts`: `test("reprocesar desde Resumen pide confirmación y deja la pantalla con el aviso")`. Run it. Expected: pass.
- [ ] **Step 5: Commit.** Message: `fix(proyecto): reprocesar y cerrar un nodo avisan y no desmontan lo que estás capturando`

### Task 6: Concept detail from the keyboard (C6)

**Files:**
- Modify:
  - `apps/web/app/proyecto/[id]/presupuesto/page.tsx:635-677` (group header and concept row)
  - `apps/web/components/VariantesSection.tsx:300`

- [ ] **Step 1: Write the failing e2e:** `test("el detalle de un concepto se abre con el teclado")`. Focus the first concept's disclosure button with Tab, press Enter, and expect the detail region visible with `aria-expanded="true"`.
- [ ] **Step 2: Run it.** Expected: FAIL (no button).
- [ ] **Step 3: Implement.**
  - A `<button type="button" aria-expanded aria-controls>` wraps the concept description in its cell. The row's `onClick` stays.
  - The detail row gets `id` = the `aria-controls` value.
  - Same pattern for group headers and VariantesSection groups.
  - The tour anchor `presupuesto.renglon` stays on the `<tr>`.
- [ ] **Step 4: Run it.** Expected: pass. Also run `npx playwright test e2e/recorrido.spec.ts`. Expected: pass (anchors intact).
- [ ] **Step 5: Commit.** Message: `fix(presupuesto): el detalle de un concepto se abre con el teclado`

### Task 7: Visor X asks for the motivo; review failures show (M9, M10 first item)

**Files:**
- Create: `apps/web/lib/teclasVisor.ts`
- Modify: `apps/web/app/proyecto/[id]/plano/page.tsx:321-335` (review), `:427-476` (keys), `:809-846` (Inspector buttons, ReviewNote)
- Test: `apps/web/tests/teclas-visor.test.mjs`

**Interfaces:**
- Produces: `accionDeTecla(key: string, ctx: { enCampo: boolean; seleccionado: boolean; motivoAbierto: boolean; midiendo: boolean }): "confirmar" | "pedir-motivo" | "quitar" | "siguiente" | "anterior" | "cancelar" | null`
  - Inside a field or with the motivo open, every key → null.
  - Escape with the motivo open is handled by the field itself.
  - `x` with a selection → `"pedir-motivo"`.

- [ ] **Step 1: Write the failing tests:** x → pedir-motivo; x in a field → null; x with the motivo open → null; c → confirmar; q → quitar; arrows; nothing selected → null for c/x/q.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - X and the «Excluir» button open an inline motivo `Input` (focused, `aria-label="Motivo de la exclusión"`). Enter with non-empty text calls `review(sel, "excluded", motivo)`. Esc closes the field and returns focus to the canvas.
  - Empty text: inline «Escribe el motivo para excluir».
  - The key hint reads «Teclas: C confirmar · X excluir (pide motivo) · Q quitar · ← → siguiente».
  - `review()` catches the error, sets an inline `Callout` in the Inspector («No se guardó la revisión; reintenta») and leaves the verdict unchanged.
- [ ] **Step 4: Run the tests.** Expected: pass. Then add to `e2e/acabado.spec.ts`: `test("X en el visor pide el motivo y Enter excluye con él")`. Select a detection, press x, expect the motivo field focused, type, press Enter. Expect the verdict «Excluida» and the note saved (`GET /projects/{id}/reviews`). Run it. Expected: pass.
- [ ] **Step 5: Commit.** Message: `fix(visor): excluir pide motivo también con la tecla X, y una revisión fallida se ve`

### Task 8: Confirmations for the remaining destructive actions (M8)

**Files:**
- Create: `apps/web/lib/confirmar.ts` with `pideConfirmarQuitarEnLote(n: number): boolean` (`n > 50`)
- Modify:
  - `presupuesto/page.tsx:1098-1135` (eliminar ajuste)
  - `components/OmittedSection.tsx:158-162`
  - `app/catalogo/page.tsx:1891-1895, 2141` (matrix component: confirm and always-visible icon)
  - `components/CatalogoConvocanteView.tsx:89-104` (replace when rows exist)
  - `configuracion/page.tsx:279-291` (Propietario)
  - `convenios/page.tsx:372-385`
  - `ajuste-costos/page.tsx:344-361`
  - `lectura/page.tsx:220-237` (workshop mapping)
  - `revision/page.tsx:233-266` (bulk Quitar revisión)
- Test: `apps/web/tests/confirmar.test.mjs`

- [ ] **Step 1: Write the failing test:** `pideConfirmarQuitarEnLote(50) === false`, `(51) === true`.
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Implement.** Each site opens `ConfirmDialog` naming the thing and the amount where there is one:
  - «Eliminar el ajuste de {concepto} ({importe})»
  - «Quitar {elemento} de los omitidos»
  - «Quitar {insumo} de la matriz de {concepto}»
  - «Reemplazar los {n} renglones del catálogo del contrato»
  - «Dar Propietario a {nombre} — podrá compartir, cerrar nodos y eliminar el proyecto»
  - «Eliminar el convenio {n}»
  - «Eliminar la solicitud de ajuste {n}»
  - «Quitar el mapeo {alias} → {clave}; afecta a todos los proyectos del taller»
  - «Quitar la revisión de {n} elementos»
  
  The inline «No / Sí, quitar» rows go away. Trash icon buttons get `aria-label`.
- [ ] **Step 4: Run it.** Expected: pass. Then `npm run lint` and `npm run typecheck`. Expected: 0 errors.
- [ ] **Step 5: Commit.** Message: `fix(web): lo que se elimina o da autoridad pide confirmación nombrando qué`

### Task 9: E2E harness for this wave, and the full verification

**Files:**
- Create: `apps/web/e2e/acabado.spec.ts`, built up by Tasks 4–7. This task owns its shared setup.

**Interfaces:**
- Produces: `obraLista(page): Promise<string>` in the spec. Logs in as admin, `POST /projects/demo`, waits until `GET /projects/{id}/status` is `processed`, opens the Contrato gate through the gate API, and returns the id.

- [ ] **Step 1: Write `obraLista` and add `test("la primera estimación sale del catálogo del contrato")`.** Upload a 2-row CSV through «Cargar catálogo de la convocante». Open Estimaciones and click «Capturar la estimación 1». Expect 2 rows with their claves.
- [ ] **Step 2: Run the spec.** Run: `PILOT_TEST_POSTGRES_URL=… npx playwright test e2e/acabado.spec.ts`. Expected: all pass.
- [ ] **Step 3: Full verification.**
  - `.venv/bin/python -m pytest -q`
  - `.venv/bin/ruff check .`
  - In `apps/web`: `npm test`, `npm run lint`, `npm run typecheck`, `NEXT_PUBLIC_API_URL=http://127.0.0.1:18000 npm run build`, `npx playwright test`
  
  Expected: all green.
- [ ] **Step 4: Browser walk** on the local Marina copy. Exercise each fix by hand, desktop and dark: counts with the API stopped, costo horario 404 vs 500, first estimación, asentar, reprocess from Resumen, keyboard on Presupuesto, X in the Visor, each confirmation.
- [ ] **Step 5: Commit** any fixes from the walk.
