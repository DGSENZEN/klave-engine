# Recorrido guiado Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A hands-on, spotlight onboarding tour of the pre-contract spine. It runs on a per-user, sandboxed teaching obra, and replaces the current onboarding patchwork.

**Architecture:**
- **Backend:** a new engine package `klave_engine/ejemplo` draws the teaching obra (Rev A/B) and seeds its catalog. A gold test pins every element the tour points at.
- **API:** the sample route becomes per user and sandboxed. The sample gets reset and Rev B routes, exports emit an event, and tour progress lives in the users DB.
- **Web:** tour logic is pure TS in `lib/recorrido` and is node-tested: types, reducer, placement, and chapter data. Thin React components render it, and `data-tour` anchors are placed on real UI.

**Tech Stack:**
- API: FastAPI, psycopg (users DB), ezdxf, pytest.
- Web: Next 16 / React 19, Tailwind v4 tokens, Phosphor; node test runner (`apps/web/tests/run.mjs`) and Playwright.

**Spec:** `docs/superpowers/specs/2026-10-26-recorrido-guiado-design.md` (read it first; this plan argues from it).

## Global Constraints

- **Scope:** the pre-contract spine only. No contract-side screens.
- **Copy:** product copy is Spanish es-MX. Cards are at most 2 short sentences, in the order qué · cómo · por qué.
  - Never use «detecciones», «el motor», «corridas», rule codes or raw confidence %.
  - Never use prose explanations of AI reads (`docs/principios-de-interfaz.md`).
- **Web conventions:**
  - Colors come from tokens only, via `@theme inline`; no raw hex, no `[var(--x)]`.
  - Phosphor icons only.
  - Light and dark mode must both work.
  - The effect-lint rule (`react-hooks/set-state-in-effect`) applies: use `useSyncExternalStore` for the tour store.
- **Next 16:** read the relevant guide in `apps/web/node_modules/next/dist/docs/` before writing routing/navigation code (`apps/web/AGENTS.md`).
- **The sample bends to the reader:** use only what the deterministic, rule-based reader produces today, with the AI read off. Reader changes are out of scope.
- **The sample never writes into real office data:** not the taller catalog, aliases or mappings, not `labels.jsonl`, not índices history, not the workspace counters.
- **Steps:** `hacer` steps advance only on an observed event or signal. «Saltar este paso» is always offered and recorded. The tour never blocks the page from being left.
- **Lib purity:** files in `apps/web/lib/recorrido/` are pure TS with relative imports only. No React, no `@/` aliases, no DOM. `tests/run.mjs` compiles them with plain `tsc`.
- **Commits:** end every message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **The user navigates off the step's route mid-tour** (sidebar link, browser back). The card must offer «Volver al recorrido» and must not attach to a wrong anchor. Tested in Task 8 (`fuera de ruta`).
2. **SSE events from another project or another tab arrive.** They must not advance the tour. Tested in Task 8 (`ignora eventos de otro proyecto`).
3. **A chapter after Arranque is opened from «?» while the sample is missing or still processing.** It must route to Arranque, not show steps with no data. Tested in Task 8 (`sin obra va al arranque`).
4. **Reset or Rev B is requested while a job is running.** It must return 409 with a Spanish message and must not delete files under a running job. Tested in Task 5.
5. **The users DB is unreachable in protected mode.** Progress falls back to localStorage and the tour keeps working. Tested in Task 8 (`progreso cae a local`).

---

### Task 0: Bring in the restored sample route (prerequisite)

`POST /projects/demo` exists only on `fix/pilot-blockers` (e738918). Everything in Tasks 4–5 modifies it.

- [ ] **Step 1: Check whether it is on main**

  Run `git branch --contains e738918 main`. If main contains it, rebase this branch on main and skip to Task 1.

- [ ] **Step 2: Otherwise, stop and ask Diego** whether to merge `refs/heads/fix/pilot-blockers` into `recorrido-guiado`. Do not merge without his explicit yes.

- [ ] **Step 3: After the merge, check the sample tests**

  Run `.venv/bin/pytest tests/test_demo_project.py -q`. Expected: PASS.

---

### Task 1: Sample identity helpers

**Files:**
- Create: `packages/klave_engine/ejemplo/__init__.py`
- Test: `tests/test_ejemplo_ids.py`

**Interfaces:**
- Produces:
  - `SAMPLE_PREFIX = "obra_de_ejemplo"`
  - `es_obra_de_ejemplo(project_id: str) -> bool`
  - `sample_project_id(workspace_id: str | None, user_id: str | None) -> str`

- [ ] **Step 1: Write the failing tests**

  ```python
  def test_open_mode_keeps_local_id():
      assert sample_project_id(None, None) == "obra_de_ejemplo_local"

  def test_per_user_id_is_stable_and_distinct():
      a = sample_project_id("ws-1", "3f2a…uuid-a")
      assert a == sample_project_id("ws-1", "3f2a…uuid-a")
      assert a != sample_project_id("ws-1", "uuid-b")
      assert a.startswith("obra_de_ejemplo_") and len(a) <= 100

  def test_prefix_check():
      assert es_obra_de_ejemplo("obra_de_ejemplo_local")
      assert not es_obra_de_ejemplo("marina_lote_04")
  ```

- [ ] **Step 2: Run them to verify they fail**

  Run `.venv/bin/pytest tests/test_ejemplo_ids.py -q`. Expected: ImportError.

- [ ] **Step 3: Implement the helpers**

  Build the id as `f"{SAMPLE_PREFIX}_{slugify(ws)[:36]}_{slugify(user)[:36]}"`, reusing the project's existing `slugify` (the one `routes/projects.py` imports). With no workspace and no user, return `obra_de_ejemplo_local`.

- [ ] **Step 4: Run the tests**

  Expected: PASS.

- [ ] **Step 5: Commit**

  Message: `feat(ejemplo): identidad por usuario de la obra de ejemplo`.

---

### Task 2: The teaching obra, its catalog, and its gold test

**Files:**
- Create:
  - `packages/klave_engine/ejemplo/obra.py`
  - `packages/klave_engine/ejemplo/catalogo.py`
  - `packages/klave_engine/ejemplo/precios_didacticos.json`
  - `evals/gold/obra_ejemplo.json`
- Test: `tests/test_obra_ejemplo.py`
- Leave untouched: `evals/fixtures.py` `build_demo_dxf` and `evals/gold/demo.json`.

**Interfaces:**
- Consumes:
  - `run_full_pipeline(root, settings, catalog_store=…, record_history=False, perfil_del_taller=False)` (`pipeline.py:274`)
  - `diagnose(report)` (`costing/hallazgos.py:404`)
  - `comparar_elementos` (`costing/cambios.py:126`)
  - `CatalogStore.upsert_insumo(...)` (`catalog_store.py:1721`)
  - `CONFIDENCE_FIRM = 0.7` (`costing/presentation.py:26`)
- Produces:
  - `build_obra_ejemplo(project_root: Path, revision: Literal["A", "B"] = "A") -> list[Path]`. Writes `project_root/drawings/*.dxf` with INSUNITS=5 (cm). With `"B"` it overwrites the same file names with the Rev B content.
  - `sembrar_catalogo_didactico(store: CatalogStore) -> int`. Prices the insumos listed in `precios_didacticos.json` with `source="Obra de ejemplo — precios didácticos"`, `source_type="referencia"` and `vigencia="2026-10"`, and returns how many it priced.

**Content to draw:** follow spec §4.
- Cimentación: zapatas of two types and contratrabes.
- Estructura: ejes A–C / 1–4, columns in two sections, trabes, and a losa.
- Notas generales declaring **f'c=300**. The seeded concept matrices cost a lower f'c, which yields the `fc_menor_al_plano` bloqueante.
- One deliberately ambiguous element.
- At least one concept that `precios_didacticos.json` leaves unpriced, for the dinero finding.
- Column sections go in their tags (e.g. `K-1 30x40`, `K-2 40x40`), because the R1 variant signature reads labels. Do not rely on a cuadro.
- Rev B:
  - enlarges one zapata (aditiva);
  - adds one column (aditiva);
  - removes one contratrabe or muro (deductiva).

- [ ] **Step 1: Write the failing gold tests**

  Run each revision through the pipeline into `tmp_path` using a store from `get_catalog_store(tmp_path, workspace_id="t")` after `sembrar_catalogo_didactico`.

  ```python
  def test_rev_a_carries_every_planted_teaching_element(rev_a):
      report = rev_a.cost_report
      assert rev_a.units is not None and rev_a.units.reliable
      assert any(d.confidence < CONFIDENCE_FIRM for d in rev_a.detections)            # the visor doubt
      diag = diagnose(report)
      assert any(h.severity == "bloqueante" and h.group == "fc_menor_al_plano" for h in diag.hallazgos)
      assert any(h.severity == "dinero" for h in diag.hallazgos)
      assert any(len(line.variants) >= 2 for line in report.boq.lines)               # mapping step
      priced = [l for l in report.boq.lines if not l.unpriced]
      assert len(priced) >= 0.8 * len(report.boq.lines) and report.boq.direct_cost_total > 0
      assert report.schedule.total_duration_days > 0 and len(report.schedule.phases) >= 3

  def test_rev_b_has_aditivas_and_deductivas(rev_a, rev_b):
      # concept-level differences between the two reports' boq lines
      deltas = {...}  # concept_code -> quantity_b - quantity_a
      assert any(v > 0 for v in deltas.values()) and any(v < 0 for v in deltas.values())

  def test_labels_match_gold(rev_a, rev_b):
      # detection label multisets per type equal evals/gold/obra_ejemplo.json["rev_a"|"rev_b"]
      ...

  def test_no_ai_read_is_involved(rev_a, tmp_path):
      assert not any((tmp_path / "a").rglob("ai_reads*.json"))
  ```

  Notes on the tests:
  - Use the real attribute names: `units.reliable`, `hallazgo.group` and `schedule` may differ slightly. Adapt the names, not the meaning.
  - Also assert that the captura list is non-empty, via `lo_que_el_plano_no_dio` (`costing/captura.py:68`), called the way `GET /projects/{id}/captura` calls it.

- [ ] **Step 2: Run the tests to verify they fail**

  Run `.venv/bin/pytest tests/test_obra_ejemplo.py -q`. Expected: ImportError.

- [ ] **Step 3: Implement `sembrar_catalogo_didactico` and `precios_didacticos.json`**

  Price only the insumos the Rev A concepts need, minus the one you leave unpriced on purpose.

- [ ] **Step 4: Implement `build_obra_ejemplo`, then loop until the tests pass**

  Iterate: draw → run the tests → adjust the drawing, not the reader. If a planted element cannot be produced by the current rules, replace it with a form the rules already read. If that is impossible, stop and report which tour step must change.

- [ ] **Step 5: Capture the gold labels**

  Write the label multisets into `evals/gold/obra_ejemplo.json` (same shape as `demo.json["detections"]`, under keys `rev_a` and `rev_b`). Re-run the tests. Expected: PASS.

- [ ] **Step 6: Confirm the existing gold is untouched**

  Run `.venv/bin/pytest tests/test_gold.py -q`. Expected: PASS.

- [ ] **Step 7: Commit**

  Message: `feat(ejemplo): obra didáctica Rev A/B con su catálogo y su gold`.

---

### Task 3: Sandbox — samples never write into office data

**Files:**
- Modify:
  - `apps/api/tenancy.py` (`store_for_project`)
  - `packages/klave_engine/costing/etiquetas.py` (`append_labels`)
  - `packages/klave_engine/costing/recompute.py` (`apply_taller_history`)
  - the AI-read trigger route in `apps/api/routes/ai.py`
- Test: `tests/test_ejemplo_sandbox.py`

**Interfaces:**
- Consumes: `es_obra_de_ejemplo` (Task 1).
- Produces:
  - `store_for_project(settings, project_id)` returns `get_catalog_store(settings.data_dir, workspace_id=project_id)` for samples. The sandbox file is `data/catalogs/<project_id>.db`; the project id already encodes workspace and user. This is the spec's `<ws>__ejemplo_<user>.db`, named by the sample id.
  - `drop_catalog_store(data_dir: Path, workspace_id: str) -> None` in `catalog_store.py`. It evicts the store from `_STORES` and deletes the db plus its `-wal` and `-shm` files. Used by Task 5.

- [ ] **Step 1: Write the failing tests**

  ```python
  def test_sample_project_gets_its_own_catalog(data_dir):
      office = store_for_project(settings, "marina")
      sample = store_for_project(settings, "obra_de_ejemplo_local")
      assert sample.path != office.path and sample.path.name == "obra_de_ejemplo_local.db"

  def test_labels_are_not_written_for_samples(tmp_path):
      control = tmp_path / "uploads" / "obra_de_ejemplo_local" / "processed"
      assert append_labels(control, [{"x": 1}]) == 0 and not (control / LABELS_FILENAME).exists()

  def test_taller_history_skips_samples(...):  # apply_taller_history(report, store, "obra_de_ejemplo_local") leaves project_indices empty

  def test_ai_read_refuses_samples(client):    # POST to the AI-read route for a sample → 409 {"error_type": "sample_project"}

  def test_drop_catalog_store_removes_file_and_cache(tmp_path): ...
  ```

- [ ] **Step 2: Run them to verify they fail.**

- [ ] **Step 3: Implement**

  - `append_labels` derives the project id from `control_dir.parent.name`.
  - `apply_taller_history` forces `save=False` for samples.
  - The AI route returns 409 with message «La obra de ejemplo se lee sin IA, para que siempre sea igual.»

- [ ] **Step 4: Run the tests**

  Run `.venv/bin/pytest tests/test_ejemplo_sandbox.py tests/test_gold.py -q`. Expected: PASS.

- [ ] **Step 5: Commit**

  Message: `feat(ejemplo): la obra de ejemplo vive en su propio catálogo`.

---

### Task 4: Per-user, private sample

**Files:**
- Modify:
  - `apps/api/routes/projects.py`: `create_demo_project` and `visible_project_filter:139`
  - `apps/api/routes/workspace.py`: overview `:180-230`
  - `apps/web/lib/api.ts`: drop `WorkspaceOverview.onboarding`
- Test: `tests/test_demo_project.py` (extend)

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `POST /projects/demo` returns 202 `{project_id, job_id, fresh}` with `project_id = sample_project_id(ws, user)`.
  - On fresh creation it calls `build_obra_ejemplo(root, "A")` and `sembrar_catalogo_didactico(store_for_project(settings, project_id))`.
  - The project name becomes «Obra de ejemplo».

- [ ] **Step 1: Write the failing tests**

  ```python
  def test_two_users_get_two_samples(...):          # fake users like the existing _Users helper; ids differ
  def test_sample_is_private_even_to_admins(...):   # visible_project_filter(admin)(other_users_sample) is False; own sample True
  def test_open_mode_sees_its_sample(...):          # filter returns True for obra_de_ejemplo_local
  def test_overview_counters_ignore_samples(...):   # a verified+exported sample adds 0 to attention.* and the response has no "onboarding" key
  def test_fresh_sample_is_seeded_with_teaching_prices(...):  # sandbox store has the insumos from precios_didacticos.json priced
  ```

- [ ] **Step 2: Run them to verify they fail.**

- [ ] **Step 3: Implement**

  - In `visible_project_filter`, when there is a user and `es_obra_de_ejemplo(pid)`, return `pid == sample_project_id(user ws, user id)` before the admin/member logic.
  - In the overview, filter samples out of `projects` before computing `attention`, and delete the `onboarding` block.
  - Grep the web for `onboarding` and delete its uses together with Task 11's cleanup. Until then, keep the type optional so the build passes.

- [ ] **Step 4: Run the tests**

  Run `.venv/bin/pytest tests/test_demo_project.py tests/test_workspace_limits.py -q`. Expected: PASS.

- [ ] **Step 5: Commit**

  Message: `feat(ejemplo): una obra de ejemplo por persona, privada`.

---

### Task 5: Reset and Rev B routes

**Files:**
- Modify: `apps/api/routes/projects.py`
- Test: `tests/test_demo_project.py`
- Web: `apps/web/lib/api.ts` (client functions)

**Interfaces:**
- Produces:
  - `POST /projects/{id}/demo/reiniciar` → 202 `{project_id, job_id}`. It drops the sandbox catalog (`drop_catalog_store`), removes the project root, re-creates it exactly like a fresh `POST /projects/demo` (same owner grant), and enqueues.
  - `POST /projects/{id}/demo/revision-b` → 202 `{project_id, job_id}`. It calls `build_obra_ejemplo(root, "B")` and enqueues, so `cambios` sees two runs.
  - Both return 404 for non-sample ids, and 409 `{error_type: "sample_busy", message: "La obra de ejemplo se está procesando; espera a que termine."}` while the job state is `queued` or `running`.
  - Web: `reiniciarObraDeEjemplo(projectId: string)` and `cargarRevisionB(projectId: string)` in `lib/api.ts`, both returning `Promise<{project_id: string; job_id: string}>`.
- The middleware must treat both as owner-level writes on that project: check `_required_project_role`.

- [ ] **Step 1: Write the failing tests**

  ```python
  def test_reset_restores_rev_a_and_clears_reviews(...)
  def test_reset_refused_while_processing(...)   # fake JOB_STORE.get → state "running" → 409 sample_busy, files intact
  def test_rev_b_rewrites_sheets_and_enqueues(...)
  def test_routes_refuse_non_sample_projects(...)  # 404
  ```

- [ ] **Step 2: Run them to verify they fail.**

- [ ] **Step 3: Implement the two routes.**

- [ ] **Step 4: Run the tests to verify they pass.**

- [ ] **Step 5: Commit**

  Message: `feat(ejemplo): reiniciar la obra y cargar su Rev B`.

---

### Task 6: `export_completed` event

**Files:**
- Modify: `apps/api/routes/exports.py:145` (`_mark_exported`)
- Test: `tests/test_exports.py`

**Interfaces:**
- Produces: `BUS.publish("export_completed", project_id=project_id, actor=actor, data={"formato": formato})`, published after the marker is written, inside the existing try.

- [ ] **Step 1: Write the failing test**

  `test_export_publishes_export_completed`: subscribe to `BUS`, download `presupuesto.xlsx?format=klave` (with `motivo` if blocked), and assert one event of that type carrying the format.

- [ ] **Step 2: Run it to verify it fails.**

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run it to verify it passes.**

- [ ] **Step 5: Check the web tolerates the new event type**

  Check that `components/ProjectLive.tsx:170-202` ignores unknown types, or add it with no toast.

- [ ] **Step 6: Commit**

  Message: `feat(api): exportar publica export_completed`.

---

### Task 7: Tour progress in the users DB

**Files:**
- Modify:
  - `apps/api/auth/store.py` (`_SCHEMA` and methods)
  - `apps/api/auth/account.py` (routes)
  - `apps/web/lib/api.ts`
- Test: `tests/test_recorrido_progreso.py`. Use the same skip-if-users-db-down fixture as `tests/test_auth.py`.

**Interfaces:**
- Schema: an append-only table, so a step's history is the funnel.

  ```sql
  CREATE TABLE IF NOT EXISTS recorrido_eventos (
      evento_id BIGSERIAL PRIMARY KEY,
      user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
      paso_id TEXT NOT NULL,
      estado TEXT NOT NULL CHECK (estado IN ('hecho','saltado','no_encontrado','reiniciado')),
      at TIMESTAMPTZ NOT NULL DEFAULT now()
  );
  CREATE INDEX IF NOT EXISTS recorrido_eventos_user ON recorrido_eventos (user_id, at);
  ```

- `UserStore` methods:
  - `record_recorrido(user_id: str, paso_id: str, estado: str) -> None`
  - `recorrido_progreso(user_id: str) -> dict[str, str]`: the latest `hecho` or `saltado` per `paso_id`, ignoring rows older than the latest `reiniciado`.
  - `reiniciar_recorrido(user_id: str) -> None`: inserts a `reiniciado` row; nothing is deleted.
- Routes:
  - `GET /auth/me/recorrido` → `{pasos: {paso_id: estado}}`
  - `PUT /auth/me/recorrido` with body `{paso_id: str (≤80), estado: "hecho"|"saltado"|"no_encontrado"}` → 204
  - `DELETE /auth/me/recorrido` → 204
  - All use `require_user`; DB down → `db_unavailable()`.
- Web (`lib/api.ts`):
  - `getRecorrido(): Promise<Record<string, "hecho"|"saltado">>`
  - `putRecorridoPaso(pasoId: string, estado: "hecho"|"saltado"|"no_encontrado"): Promise<void>`
  - `deleteRecorrido(): Promise<void>`
- Reset also clears progress: `POST /projects/{id}/demo/reiniciar` (Task 5) calls `reiniciar_recorrido` for the signed-in user. Add that call and its assertion here.

- [ ] **Step 1: Write the failing tests**

  - `test_latest_state_wins`
  - `test_no_encontrado_does_not_count_as_progress`
  - `test_reiniciar_hides_older_rows_but_keeps_them`
  - `test_routes_require_a_session`
  - `test_reset_route_restarts_progress`

- [ ] **Step 2: Run them to verify they fail**

  Run `make users-db-up && .venv/bin/pytest tests/test_recorrido_progreso.py -q`.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Run them to verify they pass.**

- [ ] **Step 5: Commit**

  Message: `feat(auth): progreso del recorrido por persona`.

---

### Task 8: Tour core (pure TS) with node tests

**Files:**
- Create:
  - `apps/web/lib/recorrido/tipos.ts`
  - `apps/web/lib/recorrido/motor.ts`
  - `apps/web/lib/recorrido/colocar.ts`
  - `apps/web/lib/recorrido/progreso.ts`
- Modify: `apps/web/tests/run.mjs`. Add `lib/recorrido/*.ts`, and the chapter files from Task 10, to the `tsc` list.
- Test:
  - `apps/web/tests/recorrido-motor.test.mjs`
  - `apps/web/tests/recorrido-colocar.test.mjs`

**Interfaces (produced, used by Tasks 9–11):**

```ts
// tipos.ts
export type CapituloId = "arranque" | "tablero" | "planos" | "revision" | "catalogo"
  | "presupuesto" | "programa" | "revisiones" | "tu-obra";
export type Avance =
  | { con: "siguiente" } | { con: "clic" } | { con: "ruta"; ruta: string }
  | { con: "evento"; tipo: string; si?: (data: Record<string, unknown>) => boolean }
  | { con: "senal"; nombre: string };
export type AccionPaso = "crear_obra" | "cargar_rev_b";
export type Paso = {
  id: string; capitulo: CapituloId; tipo: "mirar" | "hacer";
  ruta?: string;            // relative to /proyecto/{id} when it starts with "/"; "~/x" = workspace route "/x"
  ancla?: string; titulo: string; cuerpo: string; avanza: Avance; accion?: AccionPaso;
};
export type Capitulo = { id: CapituloId; titulo: string; minutos: number; pasos: Paso[]; transferencia: string; requiereObra: boolean };
export type EventoBus = { type: string; project_id?: string | null; data?: Record<string, unknown> };
export type Progreso = Record<string, "hecho" | "saltado">;
export type EstadoRecorrido = {
  activo: boolean; capitulo: CapituloId | null; indice: number; projectId: string | null;
  obraLista: boolean; progreso: Progreso; repaso: boolean; anclaPerdida: boolean; fueraDeRuta: boolean;
};
export type Entrada =
  | { tipo: "iniciar"; capitulo: CapituloId } | { tipo: "siguiente" } | { tipo: "atras" }
  | { tipo: "saltar" } | { tipo: "pausar" } | { tipo: "evento"; evento: EventoBus }
  | { tipo: "senal"; nombre: string } | { tipo: "clic"; ancla: string }
  | { tipo: "ruta"; pathname: string } | { tipo: "ancla_perdida" }
  | { tipo: "obra"; projectId: string; lista: boolean } | { tipo: "progreso"; progreso: Progreso };

// motor.ts
export function avanzar(estado: EstadoRecorrido, entrada: Entrada, capitulos: Capitulo[]): EstadoRecorrido;
export function pasoActual(estado: EstadoRecorrido, capitulos: Capitulo[]): Paso | null;
export function rutaDelPaso(paso: Paso, projectId: string | null): string | null;
export const ESTADO_INICIAL: EstadoRecorrido;

// colocar.ts
export type Rect = { top: number; left: number; width: number; height: number };
export function colocarTarjeta(ancla: Rect | null, tarjeta: { w: number; h: number },
  vista: { w: number; h: number }, margen?: number): { top: number; left: number; lado: "abajo" | "arriba" | "derecha" | "izquierda" | "centro" };

// progreso.ts
export type AlmacenProgreso = { cargar(): Promise<Progreso>; guardar(pasoId: string, estado: "hecho" | "saltado" | "no_encontrado"): Promise<void>; borrar(): Promise<void> };
export function crearAlmacen(remoto: AlmacenProgreso | null, local: Pick<Storage, "getItem" | "setItem" | "removeItem">): AlmacenProgreso;
// key "klave.recorrido"; on any remoto failure, read/write local instead.
```

**Rules `avanzar` must implement:**
- Completing a step writes `progreso[id]`.
- At the end of a chapter, `activo` stays true and the transfer card shows (`indice === pasos.length`). The next `siguiente` deactivates the tour.
- `siguiente` advances `mirar` steps. It advances `hacer` steps only when `repaso`. `saltar` marks the step `saltado`.
- `evento` advances only if the type matches the step's `avanza.tipo`, `si` passes, and `evento.project_id === estado.projectId`. The exception is `run_published` during Arranque, which matches the `projectId` set by the `obra` input.
- `iniciar` behaves as follows:
  - On a chapter with `requiereObra`, when `!obraLista`, it starts `arranque` instead.
  - It sets `repaso = true` when every `hacer` step of that chapter is already in `progreso`.
- `ruta`: if the step has a route and `pathname` does not match it, set `fueraDeRuta = true`. Returning clears it.
- `ancla_perdida` sets `anclaPerdida`. The next step change clears it.

- [ ] **Step 1: Write the failing tests**

  Node test runner. Import from `process.env.KLAVE_TEST_LIB_DIR`, as the existing tests do. Tests, one per rule:
  - `mirar avanza con siguiente`
  - `hacer ignora siguiente`
  - `hacer avanza con su evento`
  - `ignora eventos de otro proyecto`
  - `si filtra la acción`
  - `saltar queda registrado`
  - `sin obra va al arranque`
  - `capítulo hecho entra en repaso`
  - `fuera de ruta`
  - `ancla perdida se limpia al cambiar de paso`
  - `fin de capítulo muestra la transferencia`
  - `progreso cae a local` (the `crearAlmacen` remote throws → local is used)
  - Placement: `abajo por defecto`, `arriba si no cabe abajo`, `nunca fuera de la vista`, `sin ancla va al centro`

- [ ] **Step 2: Run them to verify they fail**

  Run `cd apps/web && npm test`. Expected: compile error or failing tests.

- [ ] **Step 3: Implement the four files.**

- [ ] **Step 4: Run the tests and typecheck**

  Run `npm test && npm run typecheck`. Expected: PASS.

- [ ] **Step 5: Commit**

  Message: `feat(web): motor del recorrido (puro, probado)`.

---

### Task 9: Tour UI — provider, spotlight, card, bridge, signals

**Files:**
- Create:
  - `apps/web/components/recorrido/RecorridoProvider.tsx`
  - `apps/web/components/recorrido/Foco.tsx` (spotlight / ring)
  - `apps/web/components/recorrido/TarjetaPaso.tsx`
  - `apps/web/components/recorrido/RecorridoPuente.tsx`
  - `apps/web/lib/recorridoStore.ts` (React-side module store)
- Modify:
  - `apps/web/app/layout.tsx`: mount the provider beside `CopilotFab`.
  - `apps/web/app/proyecto/[id]/layout.tsx:181`: mount `RecorridoPuente` inside `ProjectLiveProvider`.
  - `apps/web/components/PlanoCanvas.tsx`: signal `visor.mover` on pan/zoom end.
  - `apps/web/app/proyecto/[id]/plano/page.tsx`: signal `visor.seleccion` on selection.

**Interfaces:**
- Consumes: Task 8, Task 5's client functions, Task 7's client functions, `fetchAuthStatus` (`lib/session.ts:70`), `createDemoProject`.
- Produces:
  - `recorridoStore.ts`:
    - `despachar(entrada: Entrada): void`
    - `usarRecorrido(): EstadoRecorrido` (via `useSyncExternalStore`)
    - `iniciarCapitulo(id: CapituloId): void`
    - `senalRecorrido(nombre: string): void` (= `despachar({tipo: "senal", nombre})`)
  - Persistence: every step completion calls `almacen.guardar`. Misses call `guardar(id, "no_encontrado")` and `console.warn`.

**Behavior:**
- The provider navigates with `router.push(rutaDelPaso(...))` when a step's route differs from `usePathname()`, and dispatches `ruta` on pathname change.
- It looks up `[data-tour="…"]` with a `MutationObserver` for up to 4 s, then dispatches `ancla_perdida`.
- It tracks the anchor's rect with `ResizeObserver` plus scroll/resize listeners, and calls `scrollIntoView({block: "center"})` once per step. Under `prefers-reduced-motion`, scrolling is not smooth.
- On `clic` steps it adds a capturing click listener on the anchor.
- `Foco`:
  - `mirar` steps: a fixed full-viewport overlay with a cut-out, an SVG mask or a box-shadow ring around the rect. Use token colors via classes. It is `pointer-events: none` except the dim area.
  - `hacer` steps: an outline ring only. No dim, and pointer and keyboard events pass through.
- `TarjetaPaso`:
  - `role="dialog"`, `aria-modal="false"`, `aria-live="polite"`.
  - Placed with `colocarTarjeta`; a bottom sheet under `md`.
  - Buttons: Atrás, Siguiente (`mirar` only, or `repaso`), «Saltar este paso» (`hacer`), Pausar.
  - The `accion` button calls `createDemoProject` or `cargarRevisionB` and dispatches `obra`.
  - Shows the microlabel `{capítulo} · {n} de {total}`.
  - The fuera-de-ruta state reads «Volver al recorrido»; the ancla-perdida state reads «No encuentro esto en esta pantalla».
  - Esc pauses. →/← work only on `mirar` steps and never while focus is in an input.
- `RecorridoPuente` forwards `latestEvent` from the project live context as `{tipo: "evento"}` and dispatches `obra` with `lista` from the project status.

- [ ] **Step 1: Build it and check it in the browser**

  Use the preview tools: `preview_start` on the web config, open the sample in open mode, and run a temporary two-step chapter. Check:
  - the spotlight in light and dark;
  - the ring step with C/X/Q still working in the visor;
  - the card at 375 px width;
  - Esc pausing;
  - navigating away showing «Volver al recorrido».

  Remove the temporary chapter afterwards.

- [ ] **Step 2: Lint, typecheck and test**

  Run `npm run lint && npm run typecheck && npm test`. Expected: PASS (no effect-lint violations).

- [ ] **Step 3: Commit**

  Message: `feat(web): foco, tarjeta y puente del recorrido`.

---

### Task 10: The nine chapters and their anchors

**Files:**
- Create: `apps/web/lib/recorrido/capitulos/{arranque,tablero,planos,revision,catalogo,presupuesto,programa,revisiones,tu-obra}.ts` and `capitulos/index.ts`, which exports `CAPITULOS: Capitulo[]` in this order.
- Modify: the components named below, adding `data-tour` attributes only.
- Test: `apps/web/tests/recorrido-anclas.test.mjs`. For every `ancla` in `CAPITULOS`, assert that the literal `data-tour="<ancla>"` occurs in some file under `app/` or `components/`. Also assert that step ids are unique and every chapter has a non-empty `transferencia`.

**Copy:** the builder writes it within the Global Constraints.

**Steps per chapter** (route · anchor · type · advance). Anchors live in the file named.

| Capítulo | Pasos |
|---|---|
| arranque (`requiereObra: false`) | `~/` · `inicio.recorrido` (home card, Task 11) · mirar · siguiente → `~/` · `inicio.recorrido` · hacer · `accion: crear_obra`, evento `run_published` → `/` · `tablero.proceso` (job progress text, `proyecto/[id]/layout.tsx`) · mirar · siguiente |
| tablero | `/` · `tablero.nodos` (`Tablero.tsx`) · mirar → `tablero.candado` (a gated node's lock) · mirar → `tablero.sigue` (`Tablero.tsx:406`) · mirar → `shell.paleta` (`ProjectShell.tsx:251`) · mirar |
| planos | `/lectura` · `lectura.unidades`, `lectura.hojas`, `lectura.advertencias` · mirar ×3 → `/plano` · `visor.lienzo` · hacer · señal `visor.mover` → `visor.lienzo` · hacer · señal `visor.seleccion` → `visor.inspector` (`Inspector.tsx`) · mirar → `visor.lienzo` · hacer · evento `review_updated` with `si: d => String(d.action).startsWith("detection_")` |
| revision | `/revision` · `revision.tabla` (mentions Lote in copy) · mirar → `revision.masivo` · mirar → `/riesgos` · `riesgos.niveles` (`Diagnostico.tsx`) · mirar → `riesgos.criterios` · mirar → `/resumen` · `resumen.verificacion` (`resumen/page.tsx:499`) · hacer · evento `review_updated` `si: action==="verification_units"` → same for `verification_detections` → `verification_assumptions` → `resumen.sello` · mirar |
| catalogo | `/revision?tab=catalogo` (use the real tab param) · `variantes.lista` (`VariantesSection.tsx`) · mirar → `variantes.mapear` · hacer · evento `costing_updated` `si: review_action==="mapeo"` → `variantes.memoria` · mirar → `~/catalogo` · `catalogo.procedencia` · mirar → `catalogo.vigencia` · mirar |
| presupuesto | `/presupuesto` · `presupuesto.lineas` · mirar → `presupuesto.variantes` · mirar → `presupuesto.generador` · hacer · ruta `/plano` (the `?bbox=` jump) → `/apus` · `apus.matriz` · mirar → `/presupuesto` · `presupuesto.captura` (`CapturaCallout.tsx`) · mirar → `/convocante` · `convocante.tabla` · mirar → `/presupuesto` · `presupuesto.exportar` (`presupuesto/page.tsx:251`) · mirar (what each format is for) → `presupuesto.exportar` · hacer · evento `export_completed`. The card says the bloqueante will stop the export and ask for a motivo. The `ExportBlockedDialog` opens on top of the ringed anchor, and the step stays live until the export succeeds. |
| programa | `/programa` · `gate.abrir` (`GateGuard.tsx`) · hacer · evento `gate_updated` `si: node==="programa"` → `programa.barras` · mirar → `programa.holguras` · mirar → `programa.plazo` · mirar → `programa.programas` · mirar → `/flujo` · `flujo.curva` · mirar |
| revisiones | `/cambios` · `cambios.vacio` · hacer · `accion: cargar_rev_b`, evento `run_published` → `cambios.resumen` · mirar → `cambios.lista` · hacer · ruta `/plano` (the `?cambios=` link) |
| tu-obra (`requiereObra: false`) | `~/` · `inicio.subir` (home upload button) · mirar → `shell.ayuda` or `workspace.ayuda` (the «?» from Task 11) · mirar |

All chapters except `arranque` and `tu-obra` have `requiereObra: true`. Check each route and query parameter against the real page before writing it; the table names intent where a parameter's exact spelling is unverified.

- [ ] **Step 1: Write the anchor test and check it fails**

  Run `npm test`. Expected: FAIL listing the missing anchors.

- [ ] **Step 2: Write the chapter files and add the `data-tour` attributes**

  Work until `npm test` passes.

- [ ] **Step 3: Walk each chapter in the browser on the sample (open mode)**

  Fix any anchor that resolves to an off-screen or hidden element at 1280 px and at 375 px.

- [ ] **Step 4: Commit**

  Message: `feat(web): los nueve capítulos del recorrido`.

---

### Task 11: Entry points and cleanup

**Files:**
- Create:
  - `apps/web/components/recorrido/MenuRecorrido.tsx` («?» button + chapter menu)
  - `apps/web/components/recorrido/InicioRecorrido.tsx` (home card)
- Modify:
  - `components/ProjectShell.tsx` (beside `ThemeToggle`, `data-tour="shell.ayuda"`)
  - `components/WorkspaceHeader.tsx` (`data-tour="workspace.ayuda"`)
  - `components/CommandPalette.tsx` (one entry per chapter: «Recorrido: {titulo}»)
  - `app/page.tsx`
  - `app/bienvenida/page.tsx`
  - `app/como-funciona/page.tsx`
- Delete:
  - `components/OnboardingChecklist.tsx`
  - `components/HowItWorks.tsx`
  - the «El camino» card and `STEPS` in `app/como-funciona/page.tsx`
  - `WorkspaceOverview.onboarding` (from Task 4)
- Review: `docs/primeros-pasos.md`. Replace step-by-step content that duplicates the tour with a pointer to it.

**Interfaces:**
- `InicioRecorrido`:
  - With no progress: shows «Recorrido guiado · ~30 min» with Empezar / Más tarde. «Más tarde» is remembered in localStorage `klave.recorrido.despues`, with try/catch.
  - Once started: chapter ticks plus Continuar.
  - Hidden after `tu-obra` is done.
  - Carries `data-tour="inicio.recorrido"`. The home upload button gets `data-tour="inicio.subir"`.
- `MenuRecorrido`:
  - Continuar.
  - The chapter list with ticks; each item calls `iniciarCapitulo`.
  - «Empezar de cero con la obra», which opens `ConfirmDialog` with consequence copy and then calls `reiniciarObraDeEjemplo` + `almacen.borrar()`.
  - Links to `/glosario` and `/como-funciona`.

- [ ] **Step 1: Implement and delete**

  Then run `grep -rn "OnboardingChecklist\|HowItWorks\|onboarding\." apps/web/app apps/web/components apps/web/lib`. Expected: no hits.

- [ ] **Step 2: Lint, typecheck, test and build**

  Run `npm run lint && npm run typecheck && npm test && npm run build`. Expected: PASS.

- [ ] **Step 3: Check in the browser**

  Check the empty workspace home, the «?» menu in both headers, the palette entries, and the reset confirm, in light and dark. Take a screenshot as proof.

- [ ] **Step 4: Commit**

  Message: `feat(web): entradas del recorrido; fuera la guía vieja`.

---

### Task 12: End-to-end walk of the whole tour

**Files:**
- Create: `apps/web/e2e/recorrido.spec.ts`

**The test:**
1. Log in with `loginAdmin` (`e2e/fixtures.ts`) on a fresh state and start from the home card.
2. Walk every chapter. Do each `hacer` action for real:
   - pan the visor;
   - click an element;
   - press `c`;
   - mark the three checks;
   - map a variant;
   - export (write a motivo of at least 15 characters in the blocked dialog);
   - open the Programa gate;
   - load Rev B and wait for `processed`.
3. Assert that the card reaches the `tu-obra` chapter and that `GET /auth/me/recorrido` shows every `hacer` step as `hecho`.
4. Then reset from the «?» menu and assert progress is empty.

- [ ] **Step 1: Write the spec**

  Run `cd apps/web && npx playwright test e2e/recorrido.spec.ts`. Expected: FAIL at first; iterate until PASS.

- [ ] **Step 2: Run the whole verification**

  Run the full Python suite (`.venv/bin/pytest -q`), then `npm test`, `npm run lint`, `npm run typecheck`, and the e2e smoke + recorrido specs. Expected: all PASS.

- [ ] **Step 3: Commit**

  Message: `test(e2e): el recorrido completo de punta a punta`.
