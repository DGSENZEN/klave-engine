# Post-deployment feature audit — 2026-10-23

Scope: which existing features need more work now that the web runs on
Vercel (`www.klave.space`) and the engine on EC2 (`api.klave.space`).
Audited `origin/main` at `ee2c330` (local `main` was 10 commits behind).
Read-only: no production login, form submission, or infrastructure change.
Production was probed with anonymous GETs only.

## Ground truth

| Check | Result |
|---|---|
| `api.klave.space/ready` | 200, database ok, storage ok |
| `www.klave.space` | 200; apex `klave.space` 308 → www |
| Release pipeline on `main` | **Failed on every push since 2026-10-21** (4 runs) |
| Live frontend | Cached build ~62 h old; pipeline promotion always skipped |
| Python suite on `origin/main` | Green (CI: 9,205 passed on PR #3 candidate) |
| Ruff | Pass |
| mypy `packages` + `apps/api` | 2 errors in `apps/api/routes/cambios.py:55-56` (CI checks only `packages`) |
| Web `tsc` / eslint / unit tests | Pass / 0 errors, 3 warnings / 37 of 37 |
| Gold evaluation (local private drawings) | 9 of 9 PASS — but every entry is `baseline` (engine-captured), and expected direct cost is $0 everywhere |

The untracked `tests/test_recovery_check.py` fails locally because its
implementation (`deploy/recovery_check.py`) lives only on the PR #3 branch.

## Tier 0 — Release and operations (blocks every other fix from reaching users)

1. **Deploys are not happening.** GitHub's hosted runners time out on SSH to
   EC2 (port 22 limited to the operator IP). The workflow builds and stages
   the frontend, then fails before `vercel promote`, so neither the API nor the
   web has shipped through CI since 2026-10-21. PR #2 (workspace-scoped
   `/workspace/errores`, token redaction) is merged but not live.
   PR #3 (SSM tunnel) is green but blocked: the AWS managed-project policy
   denies `iam:*Provider*`, so GitHub OIDC can't be set up. A decision is
   needed on an architecture that doesn't need OIDC — e.g. a pull-based
   release agent on the instance, or a self-hosted runner on the box.
2. **Backups live on the same EBS disk** (`backups` volume). Off-host copy is a
   manual `scp`; no restore drill on real data. PR #3 has S3 templates,
   not applied.
3. **No monitoring or alerting.** `/ready` doesn't check free disk or
   `dwg2dxf`; no uptime check, disk/memory alarm, or log shipping. The API
   service has no `mem_limit`; one OOM kills everything, and in-flight jobs
   come back as "Interrumpido" with no re-queue (`apps/api/jobs.py:195-208`).
4. **`/docs` and `/openapi.json` are public in production** (verified 200,
   192 paths). Server-folder import (`POST /projects {root_path}`) is still
   open to any user in production though the UI never calls it.

## Tier 1 — Pilot-breaking product gaps

| Feature | Problem | Evidence | Effort |
|---|---|---|---|
| **Revisions (Rev B → Rev C)** | No way to replace or retire a sheet; only "add files", saved as `NN-stem`. A revised set added to the same project is read alongside the old one (quantities double); `cambios` pairs by file name so every element shows "agregado". In a new project, cambios can't compare at all. | `apps/api/routes/projects.py:277,480` (no delete/replace route); `costing/cambios.py:135` | M |
| **Generadores XLSX** (the deliverable) | "Medida base" per element is the raw drawing-unit value: a cm drawing prints 120000 under a 12.00 M2 line. Section titles use `taller_clave or ''` while Presupuesto shows PL-####. | `costing/exports.py:821,857-859` | S |
| **Lectura estructural** | `routes/estructura.py` is never mounted in `main.py` (verified: 404, absent from prod openapi). No web tab (E0 Task 14). The model already changes steel quantities, but nobody can see its checks or record a decision. E1–E4 not started. | `apps/api/main.py:157-187` | S mount + M tab |
| **Sample obra CTA** | "Explorar una obra de ejemplo" calls `POST /projects/demo`, removed 2026-10-05 → 405. It's the first thing an empty invited workspace offers. | `apps/web/lib/api.ts:568`; `app/page.tsx:480` | S |
| **Prices for a new office** | New workspace: 43 of 44 insumos have no price (intentional since v21). Official sources can't be loaded in SaaS: CDMX tabuladores, SICT costo directo, and the Guanajuato tabulador have no direct file link, so the UI says "colócalo en data/sources/…" (server disk). Custom upload takes XLSX/CSV, not the PDF. `/sources/bootstrap` has no UI caller. | `costing/sources/registry.py:59,70,91,124,175`; `app/catalogo/page.tsx:2485` | M |
| **OPUS import** | FSR, indirectos, financiamiento, utilidad, costos horarios are parsed but only shown in a toast, never saved. Excel matrix import is capped at 1 MB. | `apps/api/routes/catalog.py:76,984-993` | M |
| **OPUS / Neodata export** | One flat XLSX for the import wizard (Neodata = same sheet, renamed headers). Unpriced P.U./Importe cells contain the text "SIN PRECIO". Never verified on a real OPUS or Neodata install; no Neodata reader tested on a real export. | `costing/exports.py:174-189` | M + verification |

## Tier 2 — Needs work

**Platform**
- Upload failures: Caddy caps the whole multipart *request* at 120 MB (all
  sheets in one request) and FastAPI caps each file at 100 MB. FastAPI's 413
  has no `message`, and Caddy's 413 has no CORS headers, so the browser shows
  a generic "No se pudo confirmar la subida". There's no client-side size check
  and no progress bar. (`projects.py:103-107`, `config.py:27`, `Caddyfile.ec2`)
- AI budget: checked only at start and recorded only after the whole run
  (`routes/ai.py:169,209-221`), so a run can overshoot the cap. Usage records
  provider "auto". The fallback model `claude-fable-5-1` has no price, so its
  cost counts as $0 (`tarifas.py:67-73`). The AI read thread runs outside the
  job concurrency limit (`ai.py:236`).
- Mail is half-wired: compose forwards only the Resend key and `KLAVE_MAIL_FROM`.
  The From default is `no-reply@localhost`. SMTP and Google sign-in vars aren't
  forwarded. Undelivered mail goes to `/data/outbox` with live tokens, and
  those land in backups. Production currently runs without mail, and the
  hand-delivery flows are honest about it.
- SSE through Caddy is unverified: `encode gzip` also covers `text/event-stream`.
  Check with `curl -N` behind login.
- Tenancy: `recompute.py:115,176` and `pipeline.py:624` fall back to the shared
  `data/catalog.db` when no store is passed. All callers pass one today, but
  there's no cross-workspace API test. The lector trainer (`lector/entrenar.py`,
  run from the CLI) pools every project on the data dir; decide consent before
  ever running it on production data.

**Product**
- Rule codes: exports are clean (PL-/office claves), but screens still show
  EST-001-style codes (presupuesto `page.tsx:677,990,1108`, apus, plano), so
  screen and document don't match.
- Contract node (contrato, estimaciones, convenios, bitácora, ajuste, finiquito):
  the backend is real and tested, but it's outside the pilot. Hide it per
  workspace. The bitácora calls itself «el medio oficial» but has no integrity
  or counterparty (wording risk). Parámetros sits behind the *programa* lock
  while verification step 3 links to it. Locks are browser-only (GateGuard
  lets the page through on API error; the backend doesn't enforce locks).
- `?bbox` links carry no sheet, so on multi-file sets "Ver" may open the wrong
  sheet. The visor is mouse-only (no touch, no tablet).
- Still open from the September audit: stair detector not wired into the
  pipeline (EST-015 never quantified), no concept inspector, cambios
  "supuesto → leído" labeling. Fixed since: undo from Importaciones.
- Generic job failure message with no stage for non-conversion errors
  (`jobs.py:364`).

**Frontend states and polish**
- Finiquito: load and save have no `catch`, so on error the skeleton spins
  forever and a failed save is silent (`finiquito/page.tsx:109,125`).
- Raw `err.message` ("API 422 on /projects/…") shown in convenios and
  OmittedSection. Convenios' "today" uses UTC, so it shows tomorrow's date
  after 18:00 in Mexico.
- A 403 on a project says "¿Está activo el servidor?". Shared-link page says
  "caducó" for any failure, including network/500. `/recuperar` subtitle says
  "Te enviamos un enlace" while production has no mail.
- One `<title>` for every route. Only a root error boundary exists.
  `--faint` text is 2.3–3.1:1 contrast (fails AA) across 138 uses. Modal has
  no focus trap.
- The copilot button shows on public pages; using it logged out triggers a
  "sesión terminó" redirect.

**Accuracy evidence**
- The gold set only proves "no regression": all 9 entries are engine-captured
  baselines, and none checks money. Before the pilot claims accuracy it needs
  at least one entry with quantities confirmed by an engineer
  (`make eval-compare` against a human presupuesto).

## Solid (no action needed now)

Login/logout, host-only cookies + CSRF origin check, session-expiry return;
invitations/recovery without mail; share links; per-workspace catalog storage;
Revisión (labels, «Tu catálogo», pagination); Presupuesto; completitud,
captura, convocante, índices, piloto measurement; vigencia/cotización/index
roll-forward; FSR and costo horario (2026 constants, need a yearly update);
programa/flujo; job status states in the project layout.

## Suggested order

1. Pick a release path that works under the AWS policy, ship `main`
   (including PR #2), then off-host backups + uptime/disk alerts + `mem_limit`,
   and close `/docs`.
2. Pilot blockers: generadores units, sample-obra CTA, mount estructura (or
   stop it changing costs until it has a UI), sheet replace for revisions.
3. New-office pricing path: PDF upload of official sources + bootstrap in
   onboarding, persist OPUS FSR/indirectos, raise the Excel limit, export
   unpriced cells blank.
4. Verify OPUS/Neodata import on real installs; one engineer-confirmed gold entry.
5. Hide the contract node for the pilot; then the frontend state/polish list.
