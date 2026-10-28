# Role Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Only taller admins change the catálogo; aliases and variant mappings follow "editors add, admins change or remove"; screens never offer what the person's role can't do; a test fails CI when a mutating route has no declared rule.

**Architecture:** Server rules live in two small modules: a router-level rule on `/catalog` with a named exemption list, and one shared-mapping check called from the alias and variant routes. The project role travels to the web on `GET /projects/{id}` and `GET /projects`; one pure `capabilities()` function turns (taller role, project role, mode) into named abilities that every screen reads.

**Tech Stack:** FastAPI + pytest (`uv run pytest`), Next.js 16 / React 19 + Node test runner (`npm --prefix apps/web test`), TypeScript, Tailwind v4.

**Spec:** `docs/superpowers/specs/2026-10-23-role-enforcement-design.md`

## Global Constraints

- Open mode (no accounts; `request.state.user is None`, web `status.mode === "open"`) keeps today's behaviour: everyone can do everything.
- 403 body stays `{"detail": {"error_type": "admin_required", "message": …}}`; message for catálogo: «Esta operación del catálogo requiere un administrador del taller.»
- Example obra (`es_obra_de_ejemplo(project_id)`): its catálogo is the owner's sandbox; mapping writes there need only editor on the project and are not audited.
- Project-level middleware rules (`_required_project_role`) do not change.
- Editors keep `costing-config` (per-project insumo prices) at editor level.
- Screens hide what the role can't do; never disabled-then-refused. A 403 that still happens shows the server's message (`apiMessage`).
- Spanish product copy, es-MX, following `docs/principios-de-interfaz.md`; English in code comments as the surrounding code does.
- Web lint rule: no synchronous `setState` inside effects (`react-hooks/set-state-in-effect`).
- No schema or data migration. No production deployment from this plan.

## Review Focus

1. A role changes mid-session (admin demoted while the catálogo page is open): the next write gets 403 and the page shows the server's message, not a generic failure — Task 11 Step 3 check.
2. An editor re-sends exactly the alias/mapping that already exists (double click, retry): treated as a no-op, 200, no audit entry — Task 3 test.
3. Bulk alias request from an editor mixing new and re-pointed items: nothing written, 403 lists every re-pointed concept with its current target — Task 3 test.
4. `POST /variantes/mapear?rematch` from an editor must never overwrite a human decision (`confirmada`, or `sin_equivalente` whose actor is not `motor`) — Task 4 test.
5. Users DB unreachable while accounts existed: the catálogo rule must not "open" (middleware already 503s before the route; the rule must not swallow `UsersDbUnavailable` into allow) — Task 2 test.

---

### Task 1: Shared role helpers on the server

**Files:**
- Modify: `apps/api/auth/access.py`
- Modify: `apps/api/routes/tablero.py:42-58` (use the moved helper)
- Modify: `apps/api/routes/catalog.py:106-121` (`require_catalog_admin` delegates)
- Test: `tests/test_roles.py` (create)

**Interfaces:**
- Produces: `is_taller_admin(request: Request) -> bool` = `user is not None and user["role"] == "admin"` (False in open mode; callers that must allow open mode check `request.state.user is None` themselves, as `require_taller_admin` does); `require_taller_admin(request: Request, message: str = CATALOG_ADMIN_MESSAGE) -> None` (no-op when `request.state.user is None`; else 403 `admin_required`); `viewer_project_role(request: Request, project_id: str) -> Literal["admin","owner","editor","viewer"] | None` (moved from `tablero._my_role`, same semantics: None in open mode or without a users DB); constant `CATALOG_ADMIN_MESSAGE`.
- Produces for tests: `tests/test_roles.py` fixture class `Usuarios` modelled on `tests/test_estructura_api.py:975-1000` with users `admin` (role admin, ws-a), `ana` (member, editor), `beto` (member, viewer), `olga` (member, owner), and helper `como(client, quien)` setting `middleware.SESSION_COOKIE`. Later tasks import these from `tests/test_roles.py` (move to `tests/roles_fixtures.py` if pytest import order complains; builder's call).

- [ ] **Step 1: Write failing tests** `test_require_taller_admin_open_mode_passes`, `test_require_taller_admin_member_403` (asserts `detail["error_type"] == "admin_required"`), `test_viewer_project_role_matches_tablero` (admin → "admin", ana → "editor", open → None).
- [ ] **Step 2:** Run `uv run pytest tests/test_roles.py -v` — expect ImportError/FAIL.
- [ ] **Step 3:** Implement the three helpers in `access.py`; make `catalog.require_catalog_admin` call `require_taller_admin`; make `tablero._my_role` call `viewer_project_role` (keep the name as a thin alias or replace call sites).
- [ ] **Step 4:** Run `uv run pytest tests/test_roles.py tests/test_tablero*.py -v` — PASS.
- [ ] **Step 5:** Commit `feat(auth): helpers de rol compartidos (admin del taller, rol en el proyecto)`.

### Task 2: Catálogo default rule (decision 1)

**Files:**
- Create: `apps/api/routes/catalog_rules.py`
- Modify: `apps/api/routes/catalog.py:75` (`router = APIRouter(prefix="/catalog", tags=["catalog"], dependencies=[Depends(catalog_write_rule)])`)
- Test: `tests/test_roles.py`

**Interfaces:**
- Consumes: `require_taller_admin` (Task 1).
- Produces: `CATALOG_EXEMPT: dict[tuple[str, str], str]` keyed by `(METHOD, route.path)` → one-line reason; `SHARED_MAPPING_ROUTES: frozenset[tuple[str, str]]` = `{("POST","/catalog/aliases"), ("POST","/catalog/aliases/bulk"), ("DELETE","/catalog/aliases/{code}"), ("POST","/projects/{project_id}/variantes/mapear"), ("PUT","/projects/{project_id}/variantes/{variant_key}"), ("DELETE","/projects/{project_id}/variantes/{variant_key}")}`; `catalog_write_rule(request: Request) -> None` — for POST/PUT/PATCH/DELETE, reads `request.scope["route"].path`; returns if the pair is in `CATALOG_EXEMPT` or `SHARED_MAPPING_ROUTES`; else `require_taller_admin(request)`.
- Initial `CATALOG_EXEMPT`: `("POST","/catalog/labor/preview")` "calcula, no guarda"; the two `validar` routes **only if** reading their handlers shows no write (if either writes, leave it out and note it in the commit message).

- [ ] **Step 1: Write failing tests:** `test_member_cannot_write_catalog_any_category` — with `ana` (editor on a project), POST/PUT/DELETE one route from each category in spec decision 1 (prices, APU, rendimientos, concepts, matrix generation, reference adoption, sources/import, labor/FSR, equipment, indices, plantillas, parametric rules, inventory mappings) all return 403 `admin_required`, and `CatalogStore.load_concepts()` / relevant loads are byte-identical before and after; `test_admin_can_write_same_sample` → 2xx; `test_open_mode_writes_catalog` → 2xx; `test_users_db_down_does_not_open_catalog` (store raises `UsersDbUnavailable` with `last_known_has_users=True` → 503, catálogo unchanged).
- [ ] **Step 2:** Run `uv run pytest tests/test_roles.py -k catalog -v` — FAIL on member cases.
- [ ] **Step 3:** Implement `catalog_rules.py` and attach the dependency. Leave existing per-route `require_catalog_admin` calls in place (harmless).
- [ ] **Step 4:** Run `uv run pytest tests/test_roles.py tests/test_catalog*.py tests/test_aliases.py -v` — PASS (existing catálogo tests run in open mode).
- [ ] **Step 5:** Commit `feat(catalogo): solo un administrador cambia el catálogo del taller`.

### Task 3: Shared-mapping rule for aliases (decision 3)

**Files:**
- Create: `apps/api/auth/shared_mappings.py`
- Modify: `apps/api/routes/catalog.py:1805-1865` (`set_alias`, `set_aliases_bulk`, `clear_alias`)
- Test: `tests/test_roles.py`

**Interfaces:**
- Consumes: `is_taller_admin`, `require_project_role` (existing), `es_obra_de_ejemplo`, `auth.common.audit`, `get_user_store`.
- Produces:
  - `alias_target(row: dict | None) -> tuple[str | None, int | None, str | None] | None` → `(kind, ref_id, target_code)` or None.
  - `check_alias_writes(request: Request, project_id: str, catalog: CatalogStore, items: list[tuple[str, tuple]]) -> None` — `items` are `(concept_code, new_target)`; example obra → return; admin → return; collects every code whose existing target differs from `new_target`; if any, raises 403 `{"error_type": "admin_required", "message": …, "cambios": [{"concept_code", "actual": {...}}]}`. Same target → allowed (no-op).
  - `check_mapping_removal(request: Request, project_id: str) -> None` — example obra → return; else `require_taller_admin`.
  - `audit_mapping(request: Request, project_id: str, action: Literal["alias_added","alias_changed","alias_cleared","variant_mapped","variant_remapped","variant_forgotten"], target_id: str, previous: dict | None, new: dict | None) -> None` — no-op in open mode or example obra; else `audit(users, user, action, target_type="concept" | "variant", target_id=…, detail={"project_id", "previous", "new"})`.
- Route behaviour: `set_alias`/`set_aliases_bulk` call `check_alias_writes` **before** any write (bulk = all-or-nothing); an item whose target equals the existing one is skipped (no write, no audit, still returned). `clear_alias` calls `check_mapping_removal`. Each actual write calls `audit_mapping` once.
- Message: «Ese alias ya existe en el catálogo del taller; cambiarlo o quitarlo lo decide un administrador.»

- [ ] **Step 1: Write failing tests:** `test_editor_adds_new_alias`; `test_editor_cannot_repoint_alias` (403, `cambios[0]["concept_code"]`, catálogo unchanged); `test_editor_resends_same_alias_is_noop` (200, zero new audit rows); `test_bulk_mixed_is_all_or_nothing` (2 new + 1 re-pointed → 403 listing the 1, none of the 3 written); `test_editor_cannot_clear_taller_alias`; `test_admin_repoints_and_clears`; `test_example_obra_editor_can_repoint_and_clear` (no audit rows); `test_each_taller_alias_write_audits_once`. Audit rows observed through a fake `record_audit` on the `Usuarios` fixture.
- [ ] **Step 2:** Run `uv run pytest tests/test_roles.py -k alias -v` — FAIL.
- [ ] **Step 3:** Implement `shared_mappings.py` and wire the three routes.
- [ ] **Step 4:** Run `uv run pytest tests/test_roles.py tests/test_aliases.py -v` — PASS.
- [ ] **Step 5:** Commit `feat(catalogo): los alias se agregan en revisión; cambiarlos o quitarlos es del administrador`.

### Task 4: Shared-mapping rule for variant mappings (decision 3)

**Files:**
- Modify: `apps/api/auth/shared_mappings.py`
- Modify: `apps/api/routes/variantes.py:85-180` (add `request: Request` to the three handlers)
- Modify: `packages/klave_engine/costing/mapeo.py:169-210` (`mapear` gains `keep: Callable[[dict], bool] | None = None`)
- Test: `tests/test_roles.py`, `tests/test_variantes_api.py` (existing must stay green)

**Interfaces:**
- Consumes: Task 3's `check_mapping_removal`, `audit_mapping`, `is_taller_admin`.
- Produces: `is_human_decision(row: dict | None) -> bool` = `row is not None and (row["status"] == "confirmada" or (row["status"] == "sin_equivalente" and (row.get("actor") or "") not in ("", "motor")))`; `mapping_target(row) -> tuple[str, str | None, str | None, int | None] | None` = `(status, target_kind, target_code, ref_id)`; `check_variant_write(request, project_id, previous: dict | None, new: tuple) -> None` — example obra or admin → return; `is_human_decision(previous)` and `mapping_target(previous) != new` → 403 `admin_required` with message «Esa variante ya tiene una decisión en el catálogo del taller; cambiarla lo decide un administrador.»
- Route behaviour: PUT computes `fields` as today, then `check_variant_write(request, project_id, previous, (fields["status"], fields.get("target_kind"), fields.get("target_code"), fields.get("ref_id")))` before writing; audit `variant_mapped` (previous not human) or `variant_remapped`. DELETE: `check_mapping_removal` only when `is_human_decision(previous)` (forgetting an engine proposal stays editor-level); audit `variant_forgotten`. `mapear`: pass `keep=is_human_decision` when the caller is a non-admin on a real obra (`request.state.user is not None and not is_taller_admin(request) and not es_obra_de_ejemplo(project_id)`), else `None`; rows where `keep(existing)` is True are preserved even with `rematch`. The engine never imports `apps.api`; the predicate travels as the callable.

- [ ] **Step 1: Write failing tests:** `test_editor_confirms_engine_proposal`; `test_editor_cannot_change_confirmed_mapping`; `test_editor_cannot_flip_human_sin_equivalente`; `test_editor_forgets_engine_proposal_but_not_decision`; `test_editor_rematch_keeps_human_decisions` (seed one `confirmada` + one human `sin_equivalente`, `POST …/mapear` with `{"rematch": true}` as `ana`, both unchanged); `test_admin_changes_and_forgets`; `test_example_obra_editor_free`.
- [ ] **Step 2:** Run `uv run pytest tests/test_roles.py -k variant -v` — FAIL.
- [ ] **Step 3:** Implement; `mapear`'s existing check at `mapeo.py:186` becomes `if existing and (existing["status"] == "confirmada" or not rematch or (keep is not None and keep(existing)))`.
- [ ] **Step 4:** Run `uv run pytest tests/test_roles.py tests/test_variantes_api.py tests/test_mapeo*.py -v` — PASS.
- [ ] **Step 5:** Commit `feat(variantes): mapear variantes nuevas en revisión; cambiar una decisión es del administrador`.

### Task 5: Copilot can't be a side door

**Files:**
- Modify: `apps/api/routes/copilot.py:81-200`
- Test: `tests/test_copilot_acciones.py`

**Interfaces:**
- Consumes: `is_taller_admin`, `require_taller_admin`.
- Produces: `CATALOG_ACTIONS: frozenset[str] = {"adoptar_precio_publicado"}`; `/copilot/acciones/{id}` omits actions whose `tipo` is in `CATALOG_ACTIONS` when `request.state.user` is a non-admin; `/copilot/aplicar` calls `require_taller_admin` for those tipos after the existing editor check.

- [ ] **Step 1:** Failing tests `test_editor_cannot_apply_catalog_action` (403 `admin_required`, catálogo unchanged), `test_acciones_omit_catalog_actions_for_member`, `test_admin_still_gets_and_applies_them`.
- [ ] **Step 2:** Run `uv run pytest tests/test_copilot_acciones.py -v` — FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the same — PASS.
- [ ] **Step 5:** Commit `feat(copiloto): las acciones que escriben el catálogo son del administrador`.

### Task 6: Project role in project payloads

**Files:**
- Modify: `apps/api/routes/projects.py:607-624` (`get_project` adds `payload["my_role"] = viewer_project_role(request, project_id)`) and the `GET /projects` list builder (each entry gains `my_role`)
- Modify: `apps/web/lib/api.ts:592` (`ProjectInfo.my_role: "admin" | "owner" | "editor" | "viewer" | null`) and the list entry type
- Test: `tests/test_roles.py`

**Interfaces:**
- Consumes: `viewer_project_role` (Task 1).
- Produces: `ProjectInfo.my_role` on the web.

- [ ] **Step 1:** Failing tests `test_get_project_carries_my_role` (ana → "editor", admin → "admin", open → None) and `test_project_list_carries_my_role`.
- [ ] **Step 2:** Run — FAIL. **Step 3:** Implement (one users-DB lookup per list, not per row, if the store offers a bulk method; else accept N lookups and leave a comment). **Step 4:** Run `uv run pytest tests/test_roles.py tests/test_projects*.py -v` — PASS.
- [ ] **Step 5:** Commit `feat(proyectos): cada proyecto dice el rol de quien lo mira`.

### Task 7: Route-policy test

**Files:**
- Create: `apps/api/route_policy.py`
- Create: `tests/test_route_policy.py`

**Interfaces:**
- Consumes: `CATALOG_EXEMPT`, `SHARED_MAPPING_ROUTES` (Task 2).
- Produces: `POLICIES = Literal["project","catalog_admin","workspace_admin","self","project_in_body","shared_mapping","exempt"]`; `ROUTE_POLICY_EXCEPTIONS: dict[tuple[str,str], tuple[str, str]]` (method, path) → (policy, reason) for everything not derivable by rule; `policy_for(method: str, path: str) -> str | None` — order: `SHARED_MAPPING_ROUTES` → `shared_mapping`; `CATALOG_EXEMPT` → `exempt`; prefix `/catalog` → `catalog_admin`; prefix `/projects/{project_id}` → `project`; `/workspace` → `workspace_admin`; then `ROUTE_POLICY_EXCEPTIONS`; else None.

- [ ] **Step 1:** Write `test_every_mutating_route_has_a_policy`: build `apps.api.main.create_app()` (or the module's app factory), iterate `app.routes` with methods ∩ {POST, PUT, PATCH, DELETE}, assert `policy_for` is not None; failure message lists each unclassified `METHOD path`. Add `test_shared_mapping_routes_are_not_classified_as_project` asserting the three `/projects/{project_id}/variantes…` writes resolve to `shared_mapping`.
- [ ] **Step 2:** Run `uv run pytest tests/test_route_policy.py -v` — FAIL listing the unclassified routes.
- [ ] **Step 3:** Fill `ROUTE_POLICY_EXCEPTIONS` from the failure list: `/auth/*`, `/account/*`, invitations, recovery → `self`; `/copilot/*` → `project_in_body`; `/projects/upload` (creates a project) and public share → `exempt` with reason. Every entry gets a reason string.
- [ ] **Step 4:** Run — PASS. Then temporarily add a dummy `@router.post("/catalog/zz")`-style route outside any rule in a scratch test app to confirm the test fails, and remove it.
- [ ] **Step 5:** Commit `test(rutas): toda ruta que escribe declara su regla`.

### Task 8: `capabilities()` on the web

**Files:**
- Create: `apps/web/lib/capabilities.ts`
- Create: `apps/web/tests/capabilities.test.mjs`
- Modify: `apps/web/tests/run.mjs` (add `'lib/capabilities.ts'` to the compile list)
- Modify: `apps/web/lib/gates.ts` (`canApproveGate` delegates to `capabilities`)

**Interfaces:**
- Produces:
  ```ts
  export type ProjectRole = "admin" | "owner" | "editor" | "viewer" | null;
  export type Capabilities = { editCatalog: boolean; editProject: boolean; manageProject: boolean; approveGate: boolean };
  export function capabilities(input: { mode: "open" | "protected" | "unavailable"; tallerRole: "admin" | "member" | null; projectRole?: ProjectRole }): Capabilities;
  ```
  Rules: `mode === "open"` → all true. `tallerRole === "admin"` → all true. Else `editCatalog` false; `editProject` = projectRole ∈ {editor, owner, admin}; `manageProject` = projectRole ∈ {owner, admin}; `approveGate` = `manageProject`. `mode === "unavailable"` → all false.

- [ ] **Step 1:** Write `capabilities.test.mjs` with one test per row of the spec's role table plus open and unavailable modes (assert exact objects).
- [ ] **Step 2:** Run `npm --prefix apps/web test` — FAIL (module missing).
- [ ] **Step 3:** Implement; `canApproveGate(myRole)` becomes `myRole === null || capabilities({ mode: "protected", tallerRole: myRole === "admin" ? "admin" : "member", projectRole: myRole }).approveGate`.
- [ ] **Step 4:** Run — PASS.
- [ ] **Step 5:** Commit `feat(web): una sola regla de capacidades por rol`.

### Task 9: Capabilities reach every screen

**Files:**
- Modify: `apps/web/lib/session.ts` (add `getAuthStatusOnce(): Promise<AuthStatus>` — module-level cached promise, reset by `login`/`logout`)
- Create: `apps/web/components/Capabilities.tsx` (`CapabilitiesProvider`, `useCapabilities(): Capabilities & { ready: boolean }`)
- Modify: `apps/web/app/proyecto/[id]/layout.tsx:91-95` (keep `p.my_role`; wrap `ProjectShell` children in `<CapabilitiesProvider projectRole={myRole}>`)
- Modify: `apps/web/components/WorkspaceHeader.tsx:25-40`, `apps/web/app/taller/page.tsx:57` (replace ad-hoc admin checks with `capabilities({mode, tallerRole}).editCatalog` where the check means "is admin")
- Modify: `apps/web/lib/api.ts` — `apiMessage` already surfaces server text; ensure catálogo/mapping callers show it on 403

**Interfaces:**
- Consumes: `capabilities` (Task 8), `ProjectInfo.my_role` (Task 6).
- Produces: `useCapabilities()`; outside a project route `projectRole` is undefined (workspace pages only read `editCatalog`). While loading, `ready: false` and all abilities false (controls appear once known, never flash then vanish).

- [ ] **Step 1:** Add a unit test for `getAuthStatusOnce` caching in `tests/session-return.test.mjs` style only if `session.ts` compiles in the Node harness; otherwise verify in Step 4 by network panel (one `/auth/session` per page load).
- [ ] **Step 2:** Implement provider + hook (`useSyncExternalStore` or a promise resolved into state via callback, not sync setState in an effect).
- [ ] **Step 3:** Replace the ad-hoc checks.
- [ ] **Step 4:** `npm --prefix apps/web run typecheck && npm --prefix apps/web run lint && npm --prefix apps/web test` — clean. In the preview (protected mode, signed in as a member), `/auth/session` is requested once per navigation.
- [ ] **Step 5:** Commit `feat(web): las pantallas conocen tus capacidades`.

### Task 10: Catálogo read-only for members

**Files:**
- Modify: `apps/web/app/catalogo/page.tsx` (thread `editCatalog` through a `CatalogEditContext`; every control that calls a `/catalog` write in `lib/api.ts` renders only when true)
- Modify: `apps/web/components/AliasesSection.tsx`, `PlantillasSection.tsx`, `VigenciaSection.tsx`, `BaseSheet.tsx`, `PerfilTallerSection.tsx`, `IntegracionSection.tsx`, `MapeosSugeridos.tsx` (same context)

**Interfaces:**
- Consumes: `useCapabilities().editCatalog`.
- Produces: `CatalogEditContext` (boolean) exported from `apps/web/components/CatalogEdit.tsx`.
- Read-only note (one quiet line under the page header, `text-[13px] text-muted`): «Solo un administrador del taller cambia el catálogo. Puedes consultarlo y exportarlo.» Export stays available.
- Matrix cells: when false, render the value as text (no input), keep `tabular`.

- [ ] **Step 1:** List every `lib/api.ts` function that sends POST/PUT/PATCH/DELETE to `/catalog` (`grep -n '"/catalog' lib/api.ts` plus method) and every component that calls one; paste the list into the commit message.
- [ ] **Step 2:** Gate each call site's control with the context.
- [ ] **Step 3:** Verify in the preview signed in as a member: no import menu, no «Generar», no «+ concepto», no editable cells, no delete/adopt/costo-horario save; export works; as admin everything is back; in open mode everything is back.
- [ ] **Step 4:** typecheck, lint, tests — clean.
- [ ] **Step 5:** Commit `feat(catalogo): un miembro consulta el catálogo; lo cambia un administrador`.

### Task 11: Role-aware project screens and mappings

**Files:**
- Modify: `apps/web/components/ConceptPicker.tsx`, `SuggestionsBar.tsx`, `Copilot.tsx` (catálogo-writing actions follow `editCatalog`; alias *add* follows `editProject`)
- Modify: `apps/web/components/VariantesSection.tsx` (rows with a human decision: read-only for non-`editCatalog` on real obras, with one line «Esta variante ya tiene una decisión del taller; la cambia un administrador.»; the example obra follows `editProject`)
- Modify: `apps/web/components/AliasesSection.tsx` remove control → `editCatalog` (example obra → `editProject`)
- Modify: `apps/web/app/proyecto/[id]/presupuesto/page.tsx`, `plano/page.tsx`, `revision/page.tsx`, `parametros/page.tsx`, `estimaciones/page.tsx`, `convenios/page.tsx`, `ajuste-costos/page.tsx`, `bitacora/page.tsx`, `finiquito/page.tsx` (edit controls → `editProject`)
- Modify: `apps/web/app/proyecto/[id]/configuracion/page.tsx` and `apps/web/app/page.tsx` ProjectRow kebab (rename, client, archive, delete, files, sharing → `manageProject`; reprocess → `editProject`)

**Interfaces:**
- Consumes: `useCapabilities()`; `isHumanDecision(row: VariantMapping): boolean` added to `apps/web/lib/capabilities.ts` mirroring the server predicate (`status === "confirmada" || (status === "sin_equivalente" && actor && actor !== "motor")`), with a unit test in `capabilities.test.mjs`.

- [ ] **Step 1:** Add `isHumanDecision` test cases (confirmada; sin_equivalente by "motor"; by "Ana"; propuesta) — FAIL, implement, PASS.
- [ ] **Step 2:** Gate the controls file by file.
- [ ] **Step 3:** Verify in the preview with three accounts on one project — viewer: no edit controls anywhere, review keys C/X/Q do nothing and show no hint; editor: reviews, adds aliases and new mappings, sees decided mappings read-only, no owner controls; owner: rename/sharing present; admin: everything. Then a mid-session demotion (admin → member in another tab) makes the next catálogo write show «Esta operación del catálogo requiere un administrador del taller.» (Review Focus 1).
- [ ] **Step 4:** typecheck, lint, `npm --prefix apps/web test`, `uv run pytest` (full) — clean.
- [ ] **Step 5:** Commit `feat(web): cada pantalla del proyecto ofrece solo lo que tu rol permite`.

### Task 12: Release note for admins

**Files:**
- Create: `docs/notas/2026-10-roles.md`

- [ ] **Step 1:** Write a short Spanish note: members lose catálogo editing; editors keep project insumo prices, adding aliases and new variant mappings; changing or removing an existing alias or mapping is the administrator's; how an admin grants admin in Equipo.
- [ ] **Step 2:** Commit `docs(notas): qué cambia con los roles`.
