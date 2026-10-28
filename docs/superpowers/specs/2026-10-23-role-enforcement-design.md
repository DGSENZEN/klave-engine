# Role enforcement: admin-only catálogo, role-aware screens, route-policy test

Date: 2026-10-23 · revised 2026-10-27

Status: decisions approved in conversation (2026-10-23 and 2026-10-27); the
written document awaits the user's approval. Part of the "protection"
milestone, alongside `2026-10-21-diagnostic-foundation-design.md` (diagnostic
isolation) and the restore check that `tests/test_recovery_check.py` expects.
This document covers roles only. It is the first of four tracks the user asked
for on 2026-10-27, in this order: access control, movement between nodes,
workspace clean-up (catálogo, equipo, taller), project management.

## Intent

Klave is live with invited offices (talleres). The user reports that role-based
access "feels unenforced". A source check on 2026-10-23 confirmed why:

- **Project rules hold on the server.** `apps/api/auth/middleware.py` enforces
  viewer < editor < owner on every `/projects/{id}/...` path by HTTP method, and
  `project_access_problem` (`apps/api/auth/access.py`) blocks other talleres'
  projects. No cross-taller leak was found.
- **The catálogo is open to every member.** About 20 catálogo write routes in
  `apps/api/routes/catalog.py` only require a signed-in member: unit prices,
  APUs, rendimientos, concepts, matrix generation/validation settings,
  parametric rules, reference-price adoption, clearing a concept price,
  inventory mappings. By design, according to the `require_catalog_admin` docstring
  ("daily estimator work … stays open to every active member"). Because the
  catálogo is the whole taller's baseline, a member who is only a *viewer* on
  every project can still move every budget in the office.
- **The copilot is a second way in.** `POST /copilot/aplicar` with
  `adoptar_precio_publicado` requires only project *editor*, then writes the
  taller catálogo (`adopt_concept_reference`, `update_concept`).
- **Screens mostly ignore roles.** The web app checks a role only for stage
  approval on the tablero (`my_role` + `canApproveGate`) and for the admin
  pages (Equipo, Taller). Elsewhere a viewer sees edit controls and is told
  only after the request fails.
- **Nothing proves coverage.** No test walks the routes against the rules,
  which is how the catálogo gap shipped.

Re-checked 2026-10-27 on `main`, `ux/acabado` and `feat/acceso-pond`: nothing
here has been built. `routes/catalog.py` has 47 mutating routes and 26 mentions
of `require_catalog_admin`; there is no web capabilities helper and no
route-policy test.

Success: the server refuses every catálogo change from a non-admin, the
screens never offer an action the person's role can't perform, and a new route
without a declared rule fails CI.

## Decisions (the user's)

1. **Only taller admins change the catálogo.** That covers every write under
   `/catalog`: prices, APUs, rendimientos, concepts, matrices, adoption of
   reference prices, sources, imports, labor/FSR, equipment, indices,
   plantillas, parametric rules, inventory mappings.
2. **Approach B:** one default rule for the whole catálogo router plus a test
   that checks every route against a declared policy.
3. **Aliases and variant mappings (2026-10-27):** both are the taller's shared
   memory of "this drawing label means this concept", and both follow one rule.
   Project editors *add* what is not yet mapped (single or bulk) during review.
   *Changing* an existing one (re-pointing an alias to another target,
   re-deciding a stored variant mapping) or *removing* one is admin-only,
   behind the existing `ConfirmDialog`. In the example obra (its own sandbox
   catálogo) the owner keeps full control. Every add, change and removal in a
   taller catálogo is written to the taller audit log with its author.
   Reason: adding is repeated many times per session (the user's friction
   rule: repetitive work stays frictionless), while changing or removing one
   silently changes quantities in every project of the taller (authority
   actions are hard to press). (Rejected: A, adding the
   admin check route-by-route, because it repeats how the gap arose. C, moving
   all rules into the middleware, because it reworks working project
   enforcement on a live app for no extra protection.)

## Role model after this change (approved in conversation)

| Who | Catálogo | Project (their role there) |
| --- | --- | --- |
| Taller admin | Read and change | Everything, every project in their taller (unchanged) |
| Member, project owner | Read only | Rename, delete, files, sharing, plus editor rights |
| Member, project editor | Read only | Review, quantities, and that project's own insumo prices (`costing-config`, which already exists and stays editor-level) |
| Member, project viewer | Read only | Read only |

Members keep a way to fix a wrong price for their own budget: the
per-project insumo price list (`CostingOverrides.insumo_prices`). Concept-level
P.U. edits become admin-only, with no per-project equivalent in this increment.

Open (local, no accounts) mode keeps today's behavior: everyone can do
everything.

## Server design

**Catálogo default rule.** Add a router-level dependency on the `/catalog`
router. It applies `require_catalog_admin` to every mutating method (POST,
PUT, PATCH, DELETE) unless the route is in a named exemption list kept next to
the router. Initial exemptions, each with a one-line reason:

- `POST /catalog/labor/preview`: computes, saves nothing.
- `POST /catalog/matrices/validar` and `POST /catalog/concepts/{code}/validar`:
  the builder confirms they only compute. If either writes, it is not exempt.
- `POST /catalog/aliases` and `POST /catalog/aliases/bulk`: policy
  `shared_mapping` (below): editor on the project named in the body may add;
  an existing alias whose target would change needs admin.
- `DELETE /catalog/aliases/{code}`: `shared_mapping`, removal: admin in a
  taller catálogo; editor in the example obra.

**Shared mappings (decision 3).** Aliases (`routes/catalog.py`) and variant
mappings (`routes/variantes.py`: `POST /projects/{id}/variantes/mapear`,
`PUT /projects/{id}/variantes/{variant_key}`, `DELETE
/projects/{id}/variantes/{variant_key}`) write the taller catálogo — via
`_catalogo_para` / `store_for_project`, which resolve to the taller's store for
every real obra and to `catalogs/<project_id>.db` for the example obra. One
shared check decides each write:

- Example obra (`es_obra_de_ejemplo`): editor on the project, for everything.
- Taller catálogo, key not yet mapped: editor on the project (add).
- Taller catálogo, key already mapped and the write would change its target or
  decision, or the write removes it: taller admin, else 403 `admin_required`
  naming the concept/variant and its current target. Re-sending the same
  target is a no-op, not a change.
- Bulk alias requests: all-or-nothing. If any item would change an existing
  alias and the caller is not admin, the whole request is refused and the 403
  lists every such concept with its current target; nothing is written.
- `POST /variantes/mapear` (engine proposals): stores proposals only for
  variants with no stored mapping; it never overwrites an existing decision
  for a non-admin. Builder confirms from `variantes.py` whether it can
  overwrite today; if it can, it skips existing keys for non-admins rather than
  refusing the batch, because it is a machine pass, not a person's choice.

**Mapping audit.** Every add, change and removal of an alias or a variant
mapping in a taller catálogo records a taller audit entry (`auth.common.audit`)
when accounts exist: actions `alias_added`, `alias_changed`, `alias_cleared`,
`variant_mapped`, `variant_remapped`, `variant_forgotten`; target the concept
code or variant key; detail with the project, the previous target (for
changes and removals) and the new target. Example-obra writes are not audited
(sandbox).

The existing per-route `require_catalog_admin` calls may stay (harmless) or be
removed once the router rule covers them; builder's call.

**Copilot.** `/copilot/aplicar` must require taller admin for any action that
writes the catálogo (`adoptar_precio_publicado` today). The action list
(`/copilot/acciones/{id}`) should not offer a catálogo-writing action to a
non-admin; it may still offer it read-only with the reason, matching the
screens. Actions applied through existing endpoints from the client inherit
those endpoints' rules.

**Error shape.** Keep the existing 403 `{"error_type": "admin_required",
"message": …}` so current clients handle it.

## Route-policy test

A single test enumerates `app.routes` and assigns every mutating route
exactly one policy:

- `project`: under `/projects/{project_id}/...`, enforced by the middleware.
- `catalog_admin`: under `/catalog`, enforced by the router rule.
- `workspace_admin`: `/workspace` writes (already `_require_admin_if_protected`).
- `self`: auth/account routes acting on the caller's own account or a token.
- `project_in_body`: routes outside `/projects` that call `require_project_role`
  (copilot).
- `shared_mapping`: the six alias and variant-mapping routes listed above,
  wherever their path lives. The test must classify these by an explicit list,
  never by path prefix: the variant routes sit under `/projects/{id}/` and
  would otherwise pass as `project` while writing the taller catálogo.
- `exempt`: named, with a reason (previews, `/projects/upload` creating a new
  project, public share).

A mutating route with no policy fails the test. The test also runs behavioural
checks with a synthetic user store (pattern: `tests/test_events_authorization.py`):

- A member who is viewer/editor/owner on a project gets 403 `admin_required`
  on a sample of catálogo writes covering every category above, and the
  catálogo is unchanged afterwards.
- An admin succeeds on the same calls.
- A project editor cannot make the copilot write the catálogo.
- An editor can add a new alias and a new variant mapping on a real obra; the
  same editor gets 403 `admin_required` re-pointing an existing alias,
  re-deciding an existing variant mapping, or removing either, and the
  catálogo is unchanged afterwards. An admin succeeds on all of them.
- A bulk alias request mixing new and re-pointed items from an editor writes
  nothing and lists the re-pointed concepts.
- In the example obra, the same editor (as owner) can add, change and remove.
- Each taller-catálogo mapping write leaves exactly one audit entry.
- Open mode still allows everything.

## Screen design

**Where the role comes from.**
- Taller role: already in the session (`session.ts`, `status.user.role`).
- Project role: today only the tablero returns `my_role` (`tablero.py:_my_role`).
  Return it from the project payloads the project pages already load (the
  project overview / manifest response), using the same helper moved to a
  shared place, so every project page has it without an extra request.
  `GET /projects` list entries also carry it, for the multi-project work that
  follows.

**One helper.** A single `capabilities` helper in `apps/web/lib/` turns
(taller role, project role, open mode) into named abilities:
`editCatalog`, `editProject`, `manageProject`, `approveGate`. It replaces
`canApproveGate` and the ad-hoc admin checks in `WorkspaceHeader` / `taller`
/ `equipo`. Open mode (`my_role` null with no session) means all true.

**What people see.**
- Members on `/catalogo`: the catálogo reads normally; edit, import, adopt,
  delete and generate controls are hidden. One quiet line near the top says only
  an administrator can change the catálogo. Name the taller's admins if the
  session already has them; otherwise, generic wording.
- Catálogo-writing controls embedded in project pages (ConceptPicker and
  SuggestionsBar "dar precio"/adopt actions on `presupuesto` and `plano`,
  copilot catálogo actions) follow `editCatalog`.
- Project viewers: no edit controls on any project page.
- Editors: no owner controls (rename, delete, files, sharing).
- Hidden, not disabled-then-refused. The server stays the authority; a 403 that
  still happens (a role changed mid-session) shows the server's message.
- **Screens for aliases and variant mappings.** Editors keep the add controls
  where they review (`presupuesto`, `plano`, and `VariantesSection` on
  Revisión → «Tu catálogo»). On a real obra, a row that is already mapped shows
  its mapping read-only for non-admins, with one quiet line that only an
  administrator changes a mapping the taller already has; the change, «sin
  equivalente» re-decision and remove controls appear only with `editCatalog`.
  In the example obra everything follows `editProject`.
- **Guided tour.** Checked: the only tour step that writes is «Mapea una
  variante», and it runs on the person's own example obra, whose mappings live
  in its sandbox catálogo, so a member can still finish the tour. Gate approval
  stays owner-or-admin, which the example obra's owner is.

Spanish product copy follows the existing interface principles
(`docs/principios-de-interfaz.md`).

## Non-goals

- New roles (e.g. a "catálogo editor" between member and admin), a platform
  operator role, or a request-approval flow for price changes.
- Changing project-level rules or the middleware's project enforcement.
- Per-project concept/P.U. overrides.
- Cross-workspace or operator diagnostics (covered by the diagnostics spec).

## Anti-goals

- Members locked out of finishing a budget they edit: project insumo prices
  must keep working for editors.
- Silent behaviour change in open/local mode.
- A screen that offers an action and then fails because of the role.

## Rollout

No schema or data migration. Deploy through the existing verified pipeline
after review; this document authorizes no production deployment. Current
members lose catálogo write access when it ships. Release notes or an in-app
note for admins should say so.

## Open questions for the user

None. (Aliases were settled on 2026-10-27, decision 3.)

## Where it is built

Branch `feat/roles`, stacked on `ux/densidad` (PR #15), because the screens this
touches (`catalogo`, `presupuesto`, `plano`, `taller`, `equipo`) were just
reworked there. Builder's call stated, not the user's: if #15 changes shape,
rebase.

## Left to the builder

Exact placement of the exemption list and helper; whether to delete redundant
per-route admin calls; which project payload carries `my_role`; test fixture
structure; the exact Spanish wording of the read-only note and of the admin
release note.
