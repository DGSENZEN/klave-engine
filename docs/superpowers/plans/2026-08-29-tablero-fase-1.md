# Tablero de Nodos · Fase 1 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** The project's main view becomes the node canvas — six nodes with real derived state, presence, the activity rail, and admin candados (visible-but-locked, VerificationState-style signatures, audit_log) — with every existing screen preserved and the sidebar surviving until parity (approved decisions 1–3).

**Architecture:** Backend first: `ProjectReviews.gates` + `PUT /projects/{id}/gates/{node}` (authority mirrors `require_catalog_admin`: taller admin u owner del proyecto; open mode passes), audit entry + SSE `gate_updated`; and `GET /projects/{id}/tablero` — one cheap read composing node state from artifacts already on disk (manifest/status, parse_summary coverage, cost_report unpriced/total/units_reliable, risk count, reviews, gates, prefab/acabados counts) — NEVER the heavy recompute paths. Frontend: DOM+CSS canvas (no graph libs), `NodeCard` chips following the density doctrine (one fact per chip, denominators), `ActivityRail` from `useProjectLive`, `nodeGate()` pure function, and a `GateGuard` that replaces a locked node's routes with the lock screen (requisitos + quién puede abrir + the unlock action when `my_role` allows). Old Resumen moves intact to `/proyecto/[id]/resumen`; the root becomes the tablero; sidebar first item renames to «Tablero» with «Resumen» pointing at the moved page.

**Constraints:** mirror existing page patterns exactly (Next 16 — trust the repo's own idioms over training data; peek `node_modules/next/dist/docs` only if something breaks); design tokens/primitives only (`ui.tsx`, microlabel, tabular); es-MX copy; `npm run lint` + `tsc --noEmit` green; python fences (pytest exit code, gold untouched). Browser verification limited by protected-mode auth — verify render paths that don't need a session, state the limit honestly.

**Spec:** [2026-08-28-tablero-de-nodos-design.md](../specs/2026-08-28-tablero-de-nodos-design.md) — decisions 1 (convivencia), 2 (visible con candado), 3 (JSON + audit_log).

**Branch:** `git checkout -b tablero-fase-1`.

---

### Task 1: Los candados — backend

- `costing/reviews.py`: `GateState {approved_at: datetime|None, approved_by: str}`; `ProjectReviews.gates: dict[str, GateState]` (claves válidas: `presupuesto|programa|contrato`).
- `apps/api/routes/reviews.py` (o `gates.py`): `PUT /projects/{id}/gates/{node}` body `{approved: bool}` — authority helper mirroring `require_catalog_admin` (read it; open mode passes with X-Actor); writes reviews under `project_recompute_lock`; `audit()` entry (`action="gate_approved"/"gate_revoked"`, target project); publish SSE `gate_updated` like `review_updated` is published (find the publish call in reviews routes and mirror).
- Tests (`tests/test_gates.py`): approve → persisted with actor+timestamp; revoke → cleared; invalid node → 422; reviews file round-trips.

- [x] failing tests → implement → PASS (`pytest > /dev/null; echo $?`) → gold untouched → commit `feat(api): los candados del tablero — la firma del administrador, asentada y avisada`.

### Task 2: El estado del tablero — un solo GET barato

- `apps/api/routes/tablero.py`: `GET /projects/{id}/tablero` → `{my_role, gates, nodes: {planos, revision, catalogo, presupuesto, programa, contrato}}`; each node: `{estado: "ok"|"atencion"|"bloqueado"|"pendiente", chips: [{label, tone, href?}]}` composed ONLY from on-disk artifacts + reviews + manifest (coverage verdicts, hojas, unpriced n de N, riesgos count, verificación m de 3, gates). `my_role`: from the user store when protected (`owner|editor|viewer|admin`), `None` in open mode — THE known frontend gap, closed here.
- Register router; middleware gives GET viewer-level for free (URL shape `/projects/{id}/...`).
- Test: demo fixture project → shape asserted; missing artifacts → nodes degrade to `pendiente`, never 500.

- [x] failing test → implement → PASS → commit `feat(api): el estado del tablero en una sola lectura barata — cada nodo con sus hechos y su candado`.

### Task 3: El tablero — la vista principal del proyecto

- `apps/web/lib/api.ts`: `Tablero` types + `getTablero(id)` + `putGate(id, node, approved)`.
- `apps/web/lib/gates.ts`: `nodeGate(tablero, node)` pure (generalizes `moneyGate` style) → `"ok"|"atencion"|"bloqueado"|"pendiente"`.
- `apps/web/components/Tablero.tsx`: `Board` (CSS grid over the dotted canvas bg, tokens only), `NodeCard` (name, estado, ≤3 chips with denominators, candado row with quién puede abrir, presence dots from `useProjectLive().viewers` by route), `ActivityRail` (`activities` list, `es-MX` times). Click → `router.push` to the node's primary route (expansion illusion = later phase; navigation now).
- Move `app/proyecto/[id]/page.tsx` → `app/proyecto/[id]/resumen/page.tsx` (content intact); new root page renders the Tablero; `ProjectShell` nav: first item «Tablero» (href b), second «Resumen» (`/resumen`); `projectLocationLabel` gains both.
- Refetch on `connectionEpoch` + events (`job_updated`, `review_updated`, `costing_updated`, `run_published`, `gate_updated`) via the `useProjectReport`-style pattern.

- [x] implement → `npm run lint` + `npx tsc --noEmit` green → commit `feat(web): el tablero de nodos es la vista principal — seis nodos con hechos, candados y actividad en vivo`.

### Task 4: El candado se respeta — GateGuard

- `apps/web/components/GateGuard.tsx`: client wrapper reading the tablero (shared fetch/context or its own light call); when the node is locked → full-pane lock screen: candado icon, requisitos list (verificación m de 3, gate previo), quién puede abrir (`my_role`-aware), «Aprobar nodo» button (`putGate`) for admin/owner, and the doctrine line (visible, nunca oculto). Wrap the Programa group (`programa`, `flujo`, `parametros`) and Contrato group pages (`contrato`, `estimaciones`, `convenios`, `bitacora`, `ajuste-costos`, `finiquito`) — one-line wrap per page.
- Presupuesto node: v1 SIN guard (money gate already governs it) — its gate chip shows state only; enforcing waits for product feedback. Stated in the plan on purpose.

- [x] implement → lint/tsc green → commit `feat(web): el candado se respeta — el nodo bloqueado dice qué falta y quién puede abrirlo, nunca se esconde`.

### Task 5: Verificación y cierre

- [x] `npm run lint`, `npx tsc --noEmit`, `npm run build` (catches Next-16 API drift), python full suite + gold (backend files changed).
- [x] Browser smoke within auth limits: unauthenticated render path + (if the dev API allows any open project) tablero screenshot; otherwise state the limit and hand the user the two-step check (push, log in, open any project).
- [x] Docs: tablero spec «Fase 1 implementada» note; audit bitácora entry; tick plan; commit; finishing-a-development-branch.

## Out of scope (phases 2–3, unchanged)

- Expand-in-place node animation; visor round (medidas editables, ConceptPicker, ida-y-vuelta); upload pre-scan UI; density-audit reworks inside individual screens; backend route enforcement of gates (UI-level v1).
