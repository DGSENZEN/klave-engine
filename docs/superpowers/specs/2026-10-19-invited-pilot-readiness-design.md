# Invited pilot: customer experience and production readiness

**Date:** 2026-10-19

**Status:** written specification approved by the user on 2026-10-19.

**Audience:** our team and a few invited pilot customers.

## 1. Outcome and boundaries

A newly invited cost engineer can join a workspace, upload a real drawing,
understand processing and review requirements, inspect quantities and their
evidence, price the result, and export a usable budget without live coaching.
The team can build, deploy, diagnose, back up, restore, and roll back that
release using documented commands.

The user approved a complete pilot journey supported by release tooling and
cloud operations. This specification makes that scope concrete. It builds on
the existing product-v1 and pilot-measurement work; it does not replace their
quantity, provenance, or OPUS/Neodata requirements.

Assumptions for this milestone:

- The pilot is invitation-only and uses the existing roles and workspace
  isolation. The operator bootstraps administration before inviting customers.
- Deployment uses one host, persistent Docker volumes, Caddy, PostgreSQL,
  Next.js, and exactly one API process. The job scheduler and event bus are
  process-local; replicas and multiple Uvicorn workers are unsupported here.
- Spanish product copy and the existing visual language remain the baseline.
- Email remains optional: administrators can distribute invitation links
  manually. Google authentication remains optional.
- A cloud account, domain, off-server backup destination, and credentials are
  operator inputs for deployment. Local implementation and CI need none of
  the production credentials.

Excluded: public signup, billing, Kubernetes, distributed workers, new drawing
disciplines, quantity-calculation changes, a general visual redesign, and
changes to contract-management features outside this journey. Existing
customer-data fixtures and gold expectations are preserved.

## 2. Current evidence

The checkout already includes substantial uncommitted work in uploads,
authorization, live events, onboarding, numerical validation, evaluation,
deployment documentation, and `scripts/release_check.py`. Preserve it and
extend the relevant components instead of creating competing mechanisms.

Observed during this session:

| Area | Evidence | Implication |
|---|---|---|
| Customer entry | Invitations, welcome page, onboarding checklist, demo, and upload validation exist | Walk and polish these flows rather than add a second onboarding system |
| Focused Python checks | 34 tests passed across release configuration, lifespan, and uploads | These checks are a baseline, not proof of full release readiness |
| Client checks | Six upload/client tests passed | Browser interaction and API integration remain separate requirements |
| Production web build | `npm --prefix apps/web run build` failed fetching Geist, Geist Mono, and Space Grotesk through `next/font/google` | Compilation is unverified in this environment; remove the remote font dependency from application compilation |
| Health | `/health` returns status and version without checking dependencies | Add a distinct readiness contract |
| Hosting | Compose, Caddy, persistent volumes, health checks, and backup scripts exist | Verify the existing deployment and recovery path |
| Automation | No `.github` directory was present | Add automated release verification |
| Runtime | Job scheduling and SSE history are process-local | Document and enforce the single-process deployment boundary |

The previous general audit is historical evidence only. Neither it nor the
focused checks above establishes that the current full suite, container
build, database-backed auth tests, or production restoration passes.

## 3. Customer journey

The design uses existing pages and domain services. Server state remains the
authority for processing, verification, pricing, permissions, and exports.
Frontend polish must not weaken the product's evidence rules.

### 3.1 Invitation and entry

An invitation identifies the workspace and leads to account creation or the
appropriate sign-in path. Invalid, expired, revoked, or wrong-account links
explain the problem and how to obtain access. After acceptance, the user
lands on the workspace with an actionable first-project entry point.

Distinguish an unreachable service from a rejected sign-in and a users
database outage. Customer copy offers retry or contact with the workspace
administrator; it does not tell customers to start database containers.
Session expiry offers sign-in and returns to a validated same-origin
destination. Preserve saved project work and never automatically replay a
failed mutation after authentication.

### 3.2 First project and upload

The first screen gives the user a clear primary action to upload drawings,
with the demo and guide available as supporting actions. Existing users keep
their project list and filters.

Before submission, identify supported formats and invalid or empty files.
Expose the server's existing limits consistently in the UI; the server
remains responsible for enforcing them. Preserve the selected files and
project fields after a rejected submission while the page remains open.
Suppress duplicate submissions.

Distinguish uploading, queued processing, active processing, processed with
partial coverage, and failed processing. Show actual stages supplied by the
server; do not invent percentages or completion estimates. If the upload was
saved but processing could not be queued, open that saved project with a
retry-processing action instead of asking for another upload.

### 3.3 Processing, reconnection, and recovery

The project shows its current stage, per-sheet outcome where available, and
the next valid action. A processing failure retains the project and offers
a useful retry or DXF conversion instruction when applicable. Restarted work
uses the existing interrupted-job behavior and never appears to run forever.

Live connection state is visible without replacing the project with an
error screen. Reconnection refetches authoritative state using the existing
connection epoch. A live update alone never implies an unsaved form was
persisted. Retry controls must not duplicate drawing uploads or completed
mutations.

### 3.4 Review, pricing, and export

The project points to the outstanding verification step with enough context
to act: units, detections, and assumptions. From quantities and budget rows,
the reviewer can reach existing drawing evidence and relevant price input.
Keep unknown units, missing prices, partial coverage, and unverified results
visible according to the existing domain and export contracts.

An export action has pending, successful download, and recoverable failure
states. Success means a file was received, not merely that the menu closed.
Retain provenance, missing-data disclosures, and the existing verification
markings. The pilot's primary automated deliverable is a Klave budget XLSX
with its existing generators/evidence; OPUS and Neodata compatibility is
checked separately with the pilot office's actual tools.

### 3.5 Interaction quality

For the touched journey, controls have accessible names, forms support
keyboard submission, errors associate with their fields, dialogs manage
focus, and pending actions cannot be submitted twice. Check the primary
workflow at desktop width and a narrow viewport for overflow and unreachable
actions. Reuse `ui.tsx`, existing dialogs, and existing loading/error states.

## 4. Component and data boundaries

| Responsibility | Existing owner and intended extension |
|---|---|
| Account state and invitations | `apps/api/auth/`, web `lib/session.ts`, welcome/invitation pages; preserve server authorization |
| Upload request and validation | `apps/api/routes/projects.py`, web `lib/uploads.ts`, `lib/api.ts`, home page; reconcile saved-project warnings |
| Processing and live updates | `apps/api/jobs.py`, `events.py`, `routes/events.py`, `ProjectLive.tsx`, project pages; preserve durable job records and refetch behavior |
| Review and money authority | Existing review services, `MoneyGate`, budget and export routes; preserve quantity and pricing contracts |
| Customer support reference | Existing `RequestIdMiddleware`, client error types, CORS exposure, shared error rendering |
| Release verification | Existing `scripts/release_check.py`, Make targets, new GitHub Actions workflow and browser-test configuration |
| Deployment and recovery | Existing Compose, Dockerfiles, `deploy/`, and `docs/despliegue.md` |

Do not replace the client API library or restructure large screens solely
for consistency. Extract a small shared helper only where the touched flow
needs the same behavior in more than one place.

## 5. Build and release tooling

### 5.1 Repeatable application build

Bundle licensed local font assets for the existing families and use
`next/font/local`, retaining font variables, weights, and visual intent.
Include redistribution licenses. Once dependencies and assets are installed,
application compilation must not need Google Fonts connectivity. Dependency
installation and base-image retrieval may still require network access.

Keep Python and Node dependencies locked. Pin build tool versions used by CI
and container builds so an unbounded tool upgrade does not silently alter a
release. Do not change application dependencies simply to perform a reinstall.

### 5.2 One release entry point

Extend the existing release-check command rather than add a separate runner.
Keep configuration-only validation safe before first deployment. The full
release check must run configuration validation, Compose validation, Ruff,
mypy, Python tests, client tests, ESLint, explicit TypeScript checking, a
production web build, the browser smoke suite, both production image builds,
and an isolated container smoke check. Every failed required stage returns
a nonzero status with its stage identified. Never print secrets.

Database-backed auth tests are mandatory for release verification; a missing
test database must fail the preflight instead of silently skipping those
modules. Tests use disposable databases and temporary data directories,
never a configured production database or the developer's drawing folder.

Synthetic engine evaluation runs in CI. Real-drawing gold evaluation remains
a required recorded pre-release check on a machine with the private fixtures;
missing fixtures are reported explicitly and cannot count as a passing gold
check. Do not publish private plans in the CI repository or artifacts.

### 5.3 CI and release artifacts

GitHub Actions verifies pull requests and the release branch with the same
commands used locally. Provide a dedicated PostgreSQL test service and an
isolated browser environment. CI uses synthetic configuration values; cloud
credentials are unnecessary. Bound test waits and publish useful failure
reports, redacting session and invitation tokens.

Build both production images as a required release check. Tag release images
with the source commit and retain their digests so the operator can select
the previous release. Run an isolated Compose smoke check of the built
services, including database readiness and DWG converter availability. A web
build outside Docker is not sufficient evidence that its image works.

Release records identify the source commit, image digests, verification
results, and migration/recovery notes. Packaging a releasable version must
account for the current uncommitted work; a source commit must contain every
intended change before it identifies a release. This specification's commit
is documentation only.

## 6. Runtime health and support

Retain `/health` as cheap process liveness. Add `/ready` for dependency
readiness: PostgreSQL connectivity and the required schema, plus the ability
to create and remove a temporary probe in the configured data volume. Probes
use bounded timeouts and a dedicated probe location; they never edit project
files. Return HTTP 200 when ready and HTTP 503 otherwise. Public responses
contain coarse component statuses and version only, with diagnostic details
in logs. An empty-but-writable data volume is valid for first deployment.

Verify the DWG converter during release/container smoke checks and startup
capability reporting; do not spawn converter subprocesses on every probe.
Document the difference between serving DXF projects and supporting DWG input.

Use readiness for post-deploy checks and dependency health reporting. Docker
marks unhealthy containers but does not by itself restart them; do not claim
an automatic recovery mechanism that is not configured. The operator sets
an external uptime check and tests its failure notification before the pilot.

Expose the existing `X-Request-Id` response header through CORS and carry it
in client errors where available. Unexpected service errors offer retry and
a copyable support reference. Network failures without a response have no
server reference. Logs and browser reports must not include passwords,
session cookies, invitation URLs, provider keys, or drawing contents.

## 7. Deployment, backup, restore, and rollback

Use the existing two-subdomain TLS topology. PostgreSQL and application
containers stay on the internal Docker network; only Caddy exposes public
ports. Keep production settings validated and invitation-only. Bootstrap
administration through the existing operator CLI before exposing the app
publicly: start the internal services, create the workspace and administrator
invitation, then start the public proxy. Avoid reliance on winning the
first-account registration race.
Validate HTTPS, secure cookies, browser CORS, authenticated requests, SSE,
uploads, and downloads on the real domain after deployment.

Before upgrades, record the running image digests and create a complete
backup. Backup output must clearly distinguish complete success from partial
failure. SQLite snapshot capability is required for a backup taken while
the application writes; a best-effort raw database copy is not a successful
online backup. Completion metadata is written only after all required
archives pass integrity checks. Retention must not delete the last complete
backup after a failed attempt.

Provide a documented export path for copying a completed backup off the host
to an operator-supplied private destination. Verify integrity there. Do not
select a cloud storage provider or install credentials in the repository.

Restore into fresh volumes and a separate database, with application writers
stopped for the restore. Verify account access, workspace/project membership,
catalog data, drawing artifacts, and a budget export. Never practice a
restore by overwriting the active pilot volumes.

Rollback selects the prior image digests. If an upgrade changes stored data
in a backward-incompatible way, rollback also restores the compatible
pre-upgrade data snapshot with writers stopped. Document the data-loss window
explicitly: restoring a snapshot discards later writes. Preserve the failed
state for diagnosis, and validate readiness and the customer smoke journey
before reopening access. Do not present image rollback as reversing database
migrations automatically.

## 8. Verification and acceptance

Use Playwright against the production web build and the real API, with
isolated PostgreSQL and project storage. Use a small committed synthetic DXF
and deterministic test catalog setup; bootstrap an administrator through
existing server-side setup, then exercise customer actions through the UI.
Keep test setup out of public production routes. Use actual HTTP, session
cookies, processing, review persistence, and file download for the core test.

| Gate | Required evidence |
|---|---|
| Invitation | Admin creates invitation; a fresh browser accepts it; customer reaches only the permitted workspace; invalid links explain recovery |
| First project | Customer uploads a synthetic DXF, sees queued/running/terminal state, and reaches an actionable project screen |
| Recovery | Invalid selection retains form context; saved-but-not-queued upload reopens the saved project; failed processing can be retried without duplicate upload |
| Review and pricing | Customer reaches evidence, signs off the required review steps, and supplies or selects a deterministic price; reload retains the saved state |
| Export | Browser receives an XLSX; inspect workbook structure, expected concept/quantity and price, and existing evidence/disclosure content |
| Sessions and live state | Expired session leads to sign-in without replaying mutations; reconnect refetches state; server restart leaves interrupted jobs actionable |
| Release | Full release checks, database-backed auth checks, synthetic evaluation, production image builds, and isolated container smoke checks pass |
| Real drawing | A representative pilot drawing completes the journey and the resulting quantities/disclosures are reviewed by the cost engineer; private gold evaluation is recorded |
| Cloud | Real-domain HTTPS, cookies, CORS, SSE, processing, and download smoke checks pass |
| Recovery drill | Off-host backup is restored into an isolated environment; restored account, project, catalog, artifacts, and budget export are verified |
| Compatibility | Pilot office imports the relevant OPUS/Neodata export in its actual installation; record any unsupported layout explicitly |

Test error transitions at the smallest meaningful layer. Use browser network
interception for deterministic service failures and disconnections; core
success-path requests are not mocked. Cover dependency failure and restart
behavior with targeted API/process integration tests. Browser CI artifacts
use synthetic users and drawings only.

For manual pilot acceptance, observe one new invited customer complete the
workflow without coaching. Record any point that required explanation and
fix blocking friction before treating the milestone as accepted. Use the
existing pilot measurement page for review time, accepted generators, and
export-import outcome; do not invent a time-savings baseline.

## 9. Delivery order and completion boundary

Implement in this order: reliable build and release foundation; entry/upload
and recovery polish; review-to-export browser coverage; runtime readiness and
support references; backup/restore/rollback verification; isolated deployment
and observed pilot acceptance. Keep changes reviewable and preserve the
existing numerical and tenancy regression coverage throughout.

The implementation plan must distinguish locally verified work from checks
requiring a running Docker daemon, private drawings, the pilot office's
desktop software, or the cloud account. Implementation may be complete while
deployment acceptance remains outstanding; report those states separately.
This design authorizes no production deployment, external account creation,
messages to customers, or destructive restore operation. Hosting details and
operator inputs are resolved when preparing the actual deployment.
