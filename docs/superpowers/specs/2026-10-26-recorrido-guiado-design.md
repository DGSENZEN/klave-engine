# Recorrido guiado — the onboarding engine

Date: 2026-10-26 · Status: builder-checked, awaiting Diego's approval · Scope: pre-contract spine

## Intent

A first-time user should come out of onboarding able to run Klave on their
own obra. Today they can't: onboarding is a patchwork that lives *outside*
the work — a five-step checklist on the home page
(`components/OnboardingChecklist.tsx`), three "how it works" cards
(`components/HowItWorks.tsx`, on home and `/bienvenida`), the reading pages
`/como-funciona` and `/glosario`, and the Tablero's «lo que sigue» card. The
checklist sends people *to* a screen and abandons them there; none of the
~25 project screens explains itself, and the sample obra the checklist
offers is broken (`POST /projects/demo` returns 405 on `main`, see
`docs/auditoria-despliegue-2026-10-23.md:55`) and, even when it works, is a
single synthetic sheet with English marks — too thin to teach real work.

Diego's ask, in his words: "a REAL on-boarding engine highlighting a step by
step of the workflow, how to use each thing and what". It runs on an obra de
ejemplo "detailed enough it can be transmitted towards other project
workflows, enough the user understands everything necessary".

## Decisions made in conversation

- **One engine replaces the patchwork** (not a second system beside it — this
  also honours `2026-10-19-invited-pilot-readiness-design.md:52`).
- **Spotlight steps on the real UI**, walking the workflow screen by screen,
  across routes, in chapters that can each be replayed.
- **Runs on an obra de ejemplo**, not the user's own first project.
- **Hands-on**: the user performs each key action and the step advances only
  when the app observes it happened (same honesty rule as today's checklist).
- **Scope: the pre-contract spine only** — planos → revisión → catálogo →
  presupuesto → programa → export. Contract-side screens are out.
- **Approach A + 1** (see Approaches): an in-house tour engine, and a
  teaching obra generated in code, processed live, pinned by a gold test.

## Goals

1. A new user, starting from an empty workspace, can complete the tour in
   roughly 25–35 minutes and afterwards upload, verify, map, and export their
   own obra without help.
2. Every key screen of the spine is visited, with the controls that matter
   highlighted and explained: what it is, how to use it, why it exists.
3. Each chapter ends with a one-line transfer note («En tu obra, …») so the
   lesson carries over to real projects.
4. The tour is resumable, replayable per chapter, and never traps the user.
5. The tour cannot silently rot: CI fails if a step's anchor disappears from
   the UI or a planted teaching element disappears from the sample's read.

## Non-goals

- Contract-side screens (estimaciones, convenios, bitácora, ajuste de costos,
  finiquito, catálogo del contrato).
- Workspace administration (equipo, invitaciones, roles) and account flows.
- Videos, an AI tutor, or using the copilot as the teacher.
- Tooltips sprinkled across the app outside the tour.
- An English version (product copy stays Spanish es-MX).

## Anti-goals (would be failure even if it "works")

- A Next-Next-Next slideshow a user can click through without doing anything.
- The tour leaking into real office data: the taller's catálogo/aliases/
  mappings, the label harvest (`labels.jsonl`), índices history, or the
  workspace onboarding counters.
- A modal that blocks real work or cannot be left at any moment.
- Leaving the old onboarding pieces in place beside the new one.
- Copy that explains AI reads in prose (doctrine: show the sheet crop, not an
  explanation — `docs/principios-de-interfaz.md`), shows raw confidence %,
  rule codes, or the banned vocabulary («detecciones», «el motor», «corridas»).

## Approaches considered

**Tour engine**

- **A — in-house engine (chosen).** Small React engine; steps declared as
  data, pointing at `data-tour` anchors; spotlight drawn from the element's
  rect; advancement on route / click / app event. Fits the token + dark-mode
  system, Phosphor icons, and the effect-lint rule; adds no dependency
  (`apps/web/package.json` has three). Cost: we own positioning and scroll
  handling.
- B — driver.js for the highlight. Handles the spotlight only; knows nothing
  about cross-route flows or event-gated steps, which is the hard part. Saves
  ~a day, adds a dependency and a restyle. Rejected.

**Teaching obra**

- **1 — generated in code (chosen).** Extend the fixture builder into a
  small realistic obra with planted teaching elements; processed by the real
  pipeline; a gold test guarantees the planted elements survive detector
  changes.
- 2 — anonymised real set (a cut of Marina). Client's drawing; tour anchors
  drift as the reader improves. Rejected.
- 3 — pre-baked processed snapshot. Instant, but silently diverges from what
  the engine produces, so it teaches outputs the app no longer gives.
  Rejected.

## Design

### 1. The tour engine (web)

**Step model** — steps are data in `apps/web/lib/recorrido/` (one file per
chapter), roughly:

```ts
type Paso = {
  id: string;                       // stable, e.g. "planos.visor.seleccion"
  capitulo: CapituloId;
  ruta?: (projectId: string) => string; // navigate here before showing
  ancla?: string;                   // value of a data-tour="…" attribute
  tipo: "mirar" | "hacer";
  titulo: string;                   // es-MX
  cuerpo: string;                   // es-MX, ≤ 2 short sentences: qué · cómo · por qué
  avanza:
    | { con: "siguiente" }
    | { con: "clic" }               // click on the anchor
    | { con: "ruta"; ruta: string }
    | { con: "evento"; tipo: string; si?: (data: unknown) => boolean }
    | { con: "senal"; nombre: string }; // client-side signal, see below
};
```

Each chapter also carries `transferencia: string` — the «En tu obra, …» line
shown on its last card.

**Presentation.**
- `mirar` steps dim the page and cut out the anchor (spotlight).
- `hacer` steps do **not** dim; they ring the anchor and keep the page fully
  live — the visor's ←→/C/X/Q keys, inputs and menus must work untouched.
- The card is a non-modal dialog placed beside the anchor (flip/shift to stay
  on screen), re-positioned on scroll/resize (ResizeObserver + scroll
  listener), scrolls the anchor into view, and becomes a bottom sheet under
  `md`.
- Controls: Atrás, Siguiente (only on `mirar`), «Saltar este paso» (on
  `hacer`, recorded as skipped, never silent), Pausar (Esc), and a chapter
  progress microlabel (`Planos · 3 de 7`).
- Respects `prefers-reduced-motion`, tokens only (no raw colors), Phosphor
  icons, works in light and dark.
- Keyboard: → / ← move only on `mirar` steps; on `hacer` steps the engine
  does not capture keys.

**Replay.** Replaying a chapter whose `hacer` triggers are already spent
(doubt decided, variant mapped, checks verified, Rev B loaded) runs it
**look-only**: `hacer` steps show as `mirar` with «Ya lo hiciste» and a
Siguiente button. To redo the hands-on version, the user picks «Empezar de
cero con la obra» (reset, §3), which also clears the `hacer` progress of
every chapter. No per-chapter snapshots.

**Never stuck.** If the anchor is absent after the route settles (wait up to
~4 s, observing the DOM), the card shows centred with «No encuentro … en esta
pantalla» and offers Saltar / Pausar. Every such miss is reported to the
console and to the activity log (below) so a broken anchor is visible.

**State.** A module-level external store read with `useSyncExternalStore`
(the effect-lint rule forbids sync setState in effects). `TourProvider`
mounts in `app/layout.tsx` beside `CopilotFab`; it renders the overlay and
owns navigation (`router.push` to `ruta`).

**Signals into the engine.**
- *Server events*: project-scoped SSE only reaches the project layout, so a
  small `RecorridoPuente` mounted inside `proyecto/[id]/layout.tsx` (within
  `ProjectLiveProvider`) forwards `latestEvent` into the tour store.
- *Client signals*: for UI-only moments with no server event (an element
  selected in the visor, a menu opened, pan/zoom), components call
  `senalRecorrido("visor.seleccion")`. Keep these few; prefer server events
  where they exist.

**Server events used** (from `apps/api/events.py` publishers):

| Moment | Event |
|---|---|
| sample processed | `run_published` (jobs.py:206) for the sample project |
| visor C/X/Q decision | `review_updated`, `action` `detection_{confirmed,excluded,none}` (reviews.py:182) |
| verification step | `review_updated`, `action` `verification_{units,detections,assumptions}` (reviews.py:723) |
| variant mapped | `costing_updated`, `review_action: "mapeo"` (published from `routes/variantes.py` via `catalog._recompute_project`) |
| gate opened | `gate_updated` (reviews.py:663) |
| export done | **new** — see §3 |

### 2. Chapters (pre-contract spine)

Step counts are indicative; anchors are named for the builder to place.
Order is the workflow order, with one deliberate change: **Cambios moves near
the end** (ch. 7) because loading Rev B reprocesses the obra, and doing it
before Revisión would reset the reads the user just learned to review. It is
also more realistic — revisions arrive after the first budget.

0. **Arranque** (home). What Klave does in one line (plano → generadores
   ligados al dibujo → tu catálogo → OPUS/Neodata). *Hacer*: «Crear tu obra de
   ejemplo» → advances on `run_published`. While it processes, *mirar* the job
   progress text — this is what a real upload looks like.
1. **El tablero.** The six nodes and their flow; estado labels; a lock («con
   candado») — *mirar only* here: what it protects, its «Antes de abrir»
   requisitos, and who can open it; the «lo que sigue» card; ⌘K and the
   breadcrumb map. (Opening a lock is taught where it belongs — after the
   work it guards, at the start of ch. 6.)
2. **Planos.** Lectura del plano: hojas, unidades, advertencias. Visor:
   *hacer* pan/zoom (signal); *hacer* select the planted element → the
   inspector shows evidence and sheet crop (signal `visor.seleccion`); *hacer*
   decide the planted doubt with C or X (`review_updated`). Transfer: «En tu
   obra, empieza siempre por la lectura: si las unidades están mal, todo lo
   demás también.»
3. **Revisión.** The table, filters and bulk decision; Riesgos with the three
   tiers (bloqueante / dinero / revisar) and `criterios` as the assumptions
   register; Resumen's verification path — *hacer* each of the three checks
   (`verification_*`), then *mirar* the SIN VERIFICAR stamp gone.
   (`LoteDeRevision` is not taught: it renders only with ≥200 pending rows —
   mention it in one sentence on the table step.)
4. **Catálogo.** «Tu catálogo» (Revisión tab, `VariantesSection`): what a
   variant is; *hacer* map one variant onto a clave (`costing_updated`
   mapeo); *mirar* that the decision is remembered for future projects. Then
   the `/catalogo` page — *mirar only*: price provenance and vigencia badges.
5. **Presupuesto.** Lines and their variants; a generador row → *hacer* jump
   to the drawing (`?bbox=` route); APUs; the captura list; the convocante
   catálogo (*mirar*); Exportar — *hacer* an export, meet the bloqueante
   refusal (`ExportBlockedDialog`), write a motivo, export
   (`export_completed`). Transfer: what the motivo is for in a real bid.
6. **Programa.** *Hacer* first: open the Programa lock, now that its
   requisitos are met (`programa` is always route-guarded — `ROUTE_GUARDED_NODES`
   in `lib/gates.ts`; advances on `gate_updated`). Then bars and critical path, holguras, plazo in días naturales,
   the four programas; Flujo financiero.
7. **Cuando llega otra revisión.** *Hacer* «Cargar la Rev B de ejemplo»
   (`run_published`); Cambios: aditivas / deductivas; visor `?cambios=`
   highlight.
8. **Tu obra.** What differs with a real upload (time, DWG→DXF fallback,
   multiple sheets as one set); the upload button; the «?» to replay any
   chapter. Ends.

### 3. Backend changes

- **Restore the sample route.** `POST /projects/demo` exists on
  `fix/pilot-blockers` (e738918, not merged). That merge is a prerequisite;
  this work then changes it as below.
- **Per-user sample.** Today the id is per workspace
  (`obra_de_ejemplo_{workspace}`), so a second user would find the first
  user's decisions already made and `hacer` steps would never fire. New id:
  `obra_de_ejemplo_{workspace}_{user}` (open mode keeps `obra_de_ejemplo_local`).
  The `obra_de_ejemplo` prefix rule in `workspace.py:206-208` keeps working.
- **Reset.** `POST /projects/{id}/demo/reiniciar` (sample projects only):
  rewrite Rev A, drop reviews/verification/mappings/runs, reprocess. Offered
  from the tour menu («Empezar de cero con la obra»).
- **Rev B.** `POST /projects/{id}/demo/revision-b` (sample only): writes the
  Rev B sheets as replacements and enqueues a job, so `cambios` compares two
  runs with `inputs.json`. If `feat/reemplazar-hojas` has merged by then, use
  its replace route instead of a bespoke one.
- **Sandbox.** Sample projects must never write into real office data:
  - `tenancy.store_for_project` returns a sandbox catalog for sample projects
    — `data/catalogs/<ws>__ejemplo_<user>.db` (open mode:
    `data/catalogs/local__ejemplo.db`) — so mappings/aliases made in the tour
    land there. Only project-scoped routes are used for `hacer` steps; the
    workspace `/catalogo` page is `mirar` only.
  - The sandbox is seeded from a **fixed teaching catalog**, not a copy of
    the workspace's. Reasons: a new workspace has 43 of 44 insumos unpriced
    (audit 2026-10-23), so a copy would give an unpriced presupuesto; a taller
    that already maps those labels or edited matrices would make the mapping
    step and the f'c bloqueante never fire; and only a fixed seed lets the
    gold test guarantee what real users will see. Teaching prices carry an
    «ejemplo» provenance so they can't be mistaken for reference prices.
  - **Samples are private to their creator**: excluded from other users'
    project lists (including admins' — `visible_project_filter`), from the
    home attention counters, and from `any_verified` / `any_exported` in
    `routes/workspace.py`.
  - `etiquetas.append_labels` and `recompute.apply_taller_history` skip
    sample projects.
- **Export event.** `_mark_exported` (exports.py:148) publishes
  `export_completed` `{format}` on the bus (today exports emit no event; the
  web's `exporting_budget` activity fires on click, not success).
- **Tour progress, per user.** Protected mode: a `recorrido_progreso` table
  in the users DB (`apps/api/auth/store.py`): `user_id, paso_id, estado
  (hecho|saltado), at`, plus `GET/PUT /auth/me/recorrido`. Open mode:
  localStorage `klave.recorrido` (same shape). The users table has no prefs
  column today.
- **Measurement.** The progress table *is* the funnel: each row is a step
  hecho / saltado with its timestamp, plus `estado = no_encontrado` rows for
  anchor misses. It lives in the users DB, so it survives sample resets and
  covers home-level steps. No new view in this work; Diego reads it by query
  across workspaces. (The per-project activity log / «Medición del piloto» is
  the wrong home: per project, wiped by reset, absent before the sample
  exists.)

### 4. The teaching obra

A new builder beside the eval fixture — the eval `build_demo_dxf` and
`evals/gold/demo.json` stay untouched (they pin a unitless eval on purpose).

**Content (Rev A)** — a small two-level concrete building, Spanish office
conventions the current reader already handles on real sets (marks like
K-, T-, Z-, CT-; S-GRID-style layers), declared in centimetres:
- Cimentación sheet: zapatas (two types), contratrabes.
- Estructura sheet: ejes A–C / 1–4, columnas in two sections (→ ≥2 variants
  of one concept for chapter 4), trabes, losa.
- A cuadro de columnas.
- Notas generales with f'c.

**Planted teaching elements** (each is a tour anchor and must be asserted by
the gold test):
- one element the reader doubts, for the visor C/X/Q step;
- one finding of tier **bloqueante** (to meet the export refusal) and at
  least one **dinero** finding;
- ≥2 variants under one concept, unmapped, for the mapping step;
- a priced presupuesto once units are confirmed, a programa that computes,
  a non-empty captura list;
- **Rev B**: one element enlarged and one added → ≥1 aditiva and ≥1
  deductiva in `cambios`.

**The sample bends to the reader, never the reverse** (Diego, 2026-10-26).
Reader changes are out of scope. The obra is drawn only with conventions the
deterministic, rule-based reader produces today, with the optional AI read
(`load_ai_reads`) off. If a planted element can't be produced that way, e.g.
column sections from a cuadro, the builder draws it in a form the rules
already read, such as sections annotated on the plan. If nothing works, the
builder drops or replaces that step. The tour may be a little less
true-to-life; it must be identical on every run.

**Pinned by** `evals/gold/obra_ejemplo.json` + a test that processes Rev A
and Rev B and asserts every planted element above, so a detector change that
erases a teaching anchor fails CI.

### 5. Cleanup and entry points

- **Remove** `OnboardingChecklist` and `HowItWorks`, and their uses in
  `app/page.tsx` and `app/bienvenida/page.tsx`; drop «El camino» from
  `/como-funciona` (keep the principles; link to the tour). Keep `/glosario`;
  tour cards may link a term to it.
- **Home, empty workspace**: one card — «Recorrido guiado · ~30 min» with
  Empezar / Más tarde, and chapter ticks once started. After completion the
  card collapses; real-project nudges are the Tablero's «lo que sigue»
  (already exists).
- **«?» button** in `ProjectShell` (beside `ThemeToggle`) and
  `WorkspaceHeader`: opens the chapter menu (resume, replay a chapter,
  reiniciar la obra).
- **CommandPalette**: «Recorrido: <capítulo>» entries.
- Remove `primeros-pasos` copy that the tour supersedes, if it duplicates it
  (builder's judgement; `docs/primeros-pasos.md`).

### 6. Verification of the tour itself

- **Anchor test** (node test runner, `apps/web/tests/run.mjs`): every `ancla`
  in the step data exists as a `data-tour="…"` literal in the source.
- **Gold test** for the teaching obra (above).
- **Playwright e2e**: one spec walks the whole tour on a fresh sample in open
  mode, performing each `hacer` action, and asserts it reaches «Tu obra».

## Constraints

- Next 16 (read `node_modules/next/dist/docs/` before routing code), React 19,
  Tailwind v4 tokens via `@theme inline`, Phosphor only, es-MX copy, the
  effect-lint rule (`react-hooks/set-state-in-effect`).
- Copy doctrine: `docs/principios-de-interfaz.md` — short, concrete, no prose
  justifications of AI reads, no raw confidence, no rule codes.
- Role enforcement (`2026-10-23-role-enforcement-design.md`, draft): the user
  is owner of their own sample, so every `hacer` step is permitted.
- Prerequisite merge: `fix/pilot-blockers`.

## Calls I made (Diego, check these)

- Cambios moved to chapter 7, after Programa (reprocessing would reset the
  reviews taught earlier).
- Opening a lock is taught at the start of Programa, not in the Tablero
  chapter (signing before reviewing teaches the wrong habit).
- Replay of a spent chapter is look-only; full redo = reset.
- The sandbox catalog starts from a fixed teaching catalog, not the office's.
- Samples are private to their creator and kept out of workspace counters.
- Measurement = the progress table, read by query; no dashboard.
- The sample becomes per-user, with a reset.
- Tour writes are sandboxed (catalog copy per sample; no labels, no índices).
- The workspace `/catalogo` page is look-only in the tour.
- `LoteDeRevision` gets one sentence, not a step.
- Progress lives server-side per user (new users-DB table), localStorage in
  open mode.

## Left to the builder

- Exact geometry, sheet names and marks of the teaching obra, as long as the
  gold test's planted elements hold with the AI read off.
- Which f'c / data conflict produces the bloqueante (any rule that
  `hallazgos.py` rates bloqueante).
- Card copy (within the doctrine and ≤ 2 sentences), exact step split within
  each chapter, anchor names.
- Positioning details, animation, mobile sheet layout.
- Whether Rev B uses a bespoke route or `feat/reemplazar-hojas`.
