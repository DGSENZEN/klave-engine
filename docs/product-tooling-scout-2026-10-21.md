# Product experience and internal tooling scout

Date: 2026-10-21. Status: source audit and proposed scope, not an approved implementation spec.

## Outcome

Make Klave usable by invited cost engineers without continuous coaching, and
give the product team enough operational evidence to explain failures and
improve the workflow. The user confirmed that this milestone stays
invitation-only. Spanish product copy and the existing evidence-first costing
rules remain the baseline.

This work has three related but separate deliverables: a coherent application
journey, a public entry and account journey, and internal engineering operations.
Each needs a focused design and implementation plan rather than one large rewrite.

## What was checked

- Source at `93ac099`, including web routing/navigation, authentication, mail,
  logging, error records, AI usage records, background jobs, and EC2 configuration.
- Existing interface principles, density audit, and the October 19 pilot spec.
- The public deployed entry at `https://www.klave.space`: the browser reached
  `/bienvenida`, displaying invitation-only login, recovery, and explanatory copy.
- No production login, email send, infrastructure mutation, or customer-data
  inspection was performed. Authenticated UX and host health remain unverified.
- Existing untracked `tests/test_recovery_check.py` was left untouched.

Historical audits are leads to recheck, not proof that their findings still exist.
For example, the current project shell already uses a compact top bar and node
tabs; the earlier sidebar overflow finding cannot simply be carried forward.

## Inventory and gaps

| Area | Existing foundation | Remaining work / evidence limit |
| --- | --- | --- |
| Public entry | Welcome/login and explanation pages | `/` is the workspace; anonymous production visitors reach login. No dedicated product landing page was found. |
| Identity | PostgreSQL accounts, sessions, invitations, recovery, verification, optional Google linking, project roles | Exercise the full invitation-to-first-project journey and make its states coherent. Reuse the existing account system. |
| Transactional mail | SMTP, Resend, templates, explicit local outbox fallback | Checked-in EC2 Compose forwards Resend settings but no SMTP settings or mail-provider selection. Actual production mail configuration and deliverability were not inspected. |
| Navigation | Workspace header, project breadcrumbs, node tabs, command palette | Catalog is global but linked from project navigation. Verify return-to-project behavior, back navigation, query/filter persistence, keyboard access, and small screens. |
| Information density | Written principles and a prior quantitative audit | Recheck actual review/budget/catalog screens with representative data; prioritize decisions and exceptions, then disclose detail on demand. |
| Requests | Request ID, path/status/duration logging, browser support references | No complete correlated browser → API → background job → provider trace was found in the inspected paths. |
| Failures | Daily JSONL exception records, grouped workspace error endpoint, durable failed-job state | Tenant filtering and token redaction need correction. Frontend error boundary offers retry/reference but no reporting pipeline; worker failures are recorded separately from API exceptions. |
| Usage | AI tokens/estimated cost by workspace/project, auth audit records, collaboration activity, pilot measurements | These do not establish feature adoption, navigation friction, action failures, or per-user workflow funnels. |
| Infrastructure | Liveness/readiness, Compose health checks, rotating container logs, backup/release tooling | No host metrics collection or external alerting configuration found in inspected deployment files. Externally configured monitors may exist. |

## Priority findings

### P0: scope diagnostic data correctly

`apps/api/routes/workspace.py` exposes `/workspace/errores` after checking for a
workspace administrator, but calls `errores_recientes` without restricting the
results to that administrator's workspace. The reader in
`packages/klave_engine/common/bitacora.py` reads the shared error directory.
Records carry a workspace field, but the endpoint does not filter it.

Source-level consequence: with multiple workspaces, one workspace admin can
receive grouped diagnostics belonging to another. This was not exercised against
production. Add an isolation regression with two workspaces and define treatment
of unattributed/system failures. Those belong to internal operators.

Customer workspace administration and Klave engineering access must be distinct
authorization boundaries. A customer admin must not inherit platform-wide
diagnostic privileges.

### P0: redact all token-bearing routes before collecting more telemetry

`apps/api/observability.py:redact_request_path` currently masks `/by-token/` and
`/compartido/` paths. Existing routes also put reset and verification tokens in
`/auth/reset/{token}` and `/auth/verify/{token}`. Their paths can therefore reach
request logs unmasked. Inventory every token-bearing route and prefer normalized
route names in telemetry; test redaction on success, rejection, and failure paths.

### P1: make mail a deployed capability

`apps/api/mail.py` already implements SMTP with optional STARTTLS and a Resend
adapter. Wire the selected provider through `docker-compose.ec2.yml` and its
operator configuration, validate settings, and retain honest failure behavior.
Provider acceptance is not inbox delivery: verify sender/domain setup and test
receipt of invitations, recovery, and verification using a controlled mailbox.
Credentials and DNS changes are operator inputs; never put them in source.

## Recommended delivery order

### 1. Diagnostic safety and correlation foundation

Fix the two P0 findings first. Define a versioned event schema with timestamp,
environment, release, request/trace ID, workspace/user IDs when authenticated,
project/job/run IDs where applicable, operation, outcome, duration, and error code.
Resolve identity on the server; client events are observations, not audit proof.
Carry context explicitly into background workers and provider calls. Capture
expected operational failures as well as unhandled exceptions.

Acceptance: an induced processing failure can be traced from the initiating
request to the job and failed stage; another tenant cannot read it; token values
do not enter logs. Instrumentation failure must not block product operations.

### 2. Public entry, invitation, login, and mail

Create a server-rendered public product page and a deliberate authenticated app
entry. Keep the existing implementation in this Next.js application. Explain
what Klave does, show the drawing → evidence → budget journey, and provide clear
sign-in and pilot-access paths. Any access-request mechanism needs a real
destination and operator ownership before being presented as functional.

Separate login from the marketing page. Cover invitation acceptance, expired
invites, recovery, verification, session expiry, and return to the intended
destination. Moving the workspace away from `/` requires updating existing links,
session-return behavior, and browser tests, not just relocating one page.

Acceptance: an invited user receives an email, joins the correct workspace,
reaches the workspace, creates a project, signs out, recovers access, and resumes
an intended protected destination. Public signup remains closed.

### 3. Navigation and density pass on the core workflow

Start with projects → upload/process → review → drawing evidence → budget →
export. Keep the node model unless observed task completion demonstrates a need
to replace it. Preserve project, selected object, filters, and scroll position
where needed during round trips. Make cross-scope catalog navigation explicit.

For each screen, identify one primary task, put its main content early, group
repeated findings by cause, show denominators, and move secondary controls into
contextual detail. Follow `docs/principios-de-interfaz.md`; reduce repetition
without hiding uncertainty or inventing prices.

Acceptance: complete the core workflow at laptop and narrow widths with keyboard
navigation; return from catalog/evidence without losing the relevant project and
selection; compare before/after controls and scroll distance on the same fixture.
Set latency targets after measuring a representative fixture.

### 4. Internal operations and product usage

Build a restricted internal operations surface, independently authorized from
customer workspace administration. Keep four views connected by correlation IDs:

- Errors: grouped failures, affected users/workspaces, first/last occurrence,
  release, trend, and linked requests/jobs.
- Processing: queue depth/age, active jobs, stage durations, retries, failures,
  interrupted runs, and converter availability.
- Product usage: route transitions and named actions such as upload, review,
  price edit, and export, with attempts/outcomes and workflow drop-off. Measure
  meaningful clicks rather than recording every DOM interaction.
- Health/cost: API latency/error rate, database connectivity, host CPU/memory/disk,
  container restarts, backup age/failure, email failures, and AI usage by user and
  workspace. Estimates remain labeled as estimates.

Use allowlisted event fields. Exclude drawing contents, passwords, session and
invitation tokens, raw form text, and full URLs with query strings. Define
retention, sampling, access, and deletion before enabling collection. Introduce
external exporters only with an explicit data boundary and provider decision.

Acceptance: alert delivery is exercised for unavailable API, failed/stale backup,
disk pressure, and stuck/failed processing; internal operators can find a failure
by support reference and attribute usage to the authenticated actor.

## Approach choices

1. **Extend the current app in small increments (recommended).** Preserve the
   auth, mail, job, and deployment foundations; introduce shared event contracts
   and an internal access boundary. Lowest migration burden, with later exporter
   integration possible.
2. **Adopt managed observability immediately.** May shorten dashboard setup but
   still requires instrumentation, tenant boundaries, redaction, cost review,
   and explicit decisions about what leaves the host. No vendor selected here.
3. **Rebuild identity/navigation first.** Largest disruption and postpones
   diagnostic visibility; current source does not justify replacing these systems.

The first focused implementation design should cover diagnostic isolation,
token redaction, and request-to-job correlation. Landing/auth/mail and the UX
pass can then be designed as separate reviewable changes. Infrastructure access,
the current mail provider, and internal operator identities remain to be resolved
before their respective deployment steps.
