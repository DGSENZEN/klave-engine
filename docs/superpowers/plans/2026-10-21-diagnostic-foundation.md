# Diagnostic Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Native execution is recommended here; delegation requires the user's execution-method choice.

**Goal:** Isolate customer diagnostics and correlate processing failures with their initiating authenticated request.

**Architecture:** Extend the existing JSONL reader, request middleware, logging context, and durable job records. Keep correlation metadata private during persistence and bind it explicitly when a thread-pool worker starts. No external telemetry service is introduced.

**Tech Stack:** Python 3.11+, FastAPI/Starlette, standard-library logging/contextvars/threading, pytest, existing PostgreSQL authentication.

**Spec:** `docs/superpowers/specs/2026-10-21-diagnostic-foundation-design.md` (approved 2026-10-21).

## Global Constraints

- Invitation-only production; no new authentication or platform-admin roles.
- No new service, database, dependency, or public endpoint.
- Apply workspace filtering before sorting, limiting, counting, or grouping records.
- Keep the current `X-Request-Id` response contract.
- Existing job/status responses and SSE events must not acquire private user/workspace metadata.
- Old persisted records load with empty diagnostic context.
- Logging and diagnostic-write failures must not change admission, processing, publication, or error responses.
- Preserve existing durable job/artifact persistence errors as operational failures.
- Do not edit the pre-existing untracked `tests/test_recovery_check.py`.
- No production deployment, historical-log deletion, or credential rotation.

## Review Focus

- More than 200 foreign errors must not hide the caller's records (Task 1).
- Unmatched/denied routes and exception messages must not expose token URLs (Task 2).
- Reused worker threads and active-job re-enqueue must not replace attribution (Tasks 3–4).
- Telemetry failure must not conceal a real job-persistence failure (Task 5).
- Post-publication export prewarming failure must not create contradictory completed/failed lifecycle events (Task 5).

## File Responsibilities

| File | Responsibility |
| --- | --- |
| `packages/klave_engine/common/bitacora.py` | Scoped error reads and backward-compatible error-record fields. |
| `packages/klave_engine/common/diagnostics.py` (new) | Immutable context, safe path/text helpers, fixed lifecycle schema and emission. No FastAPI imports. |
| `packages/klave_engine/common/logging.py` | Attach safe diagnostic context to existing log records. |
| `apps/api/observability.py` | Request-ID compatibility, sanitized request completion logs, request-to-context helper. |
| `apps/api/main.py` | Enrich and sanitize existing API exception records. |
| `apps/api/routes/workspace.py` | Enforce session-derived error scope and protected response disclosure. |
| `apps/api/jobs.py` | Private disk serialization, explicit worker binding, lifecycle and failure records. |
| `apps/api/routes/projects.py` | Capture context at all three admission call sites. |
| `apps/web/components/BitacoraCards.tsx` | Replace filesystem-location copy with accurate recent-sample wording. |
| `tests/test_diagnostics.py` (new) | Redaction, context isolation, lifecycle schema tests. |
| `tests/test_workspace_diagnostics.py` (new) | Endpoint authorization, tenant isolation, sample semantics. |
| `tests/test_job_diagnostics.py` (new) | Worker context, serialization, lifecycle, failure tests. |
| Existing backend tests and `docs/diagnostics.md` (new) | Integration regressions and operator lookup instructions. |

### Task 1: Scope diagnostic queries before sampling

**Files:** Modify `common/bitacora.py`, `apps/api/routes/workspace.py`, `apps/web/components/BitacoraCards.tsx`; extend `tests/test_bitacora_y_gasto.py`; create `tests/test_workspace_diagnostics.py`. Here and below, `common/` means `packages/klave_engine/common/`.

**Interfaces:** Extend `errores_recientes(data_dir: Path, dias: int = 7, limite: int = 200, *, workspace: str | None = None) -> list[dict]`. `None` retains the existing local/operator all-records reader. The protected HTTP handler must pass a nonempty session workspace; missing identity/scope fails closed.

- [ ] Write `test_workspace_filter_precedes_limit`: write one `ws-a` error and 201 newer `ws-b` errors; assert `errores_recientes(..., workspace="ws-a")` returns the one owned error. Include empty/absent historical workspace fields and assert exclusion.
- [ ] Write endpoint tests `test_admin_sees_only_own_errors`, `test_workspace_cannot_be_overridden`, `test_member_and_anonymous_denied`, `test_production_db_failure_does_not_open_diagnostics`, and `test_open_development_retains_local_view`. Use a synthetic user-store double modeled on `tests/test_events_authorization.py`; exercise the actual middleware, not only direct handler calls. Assert 200 only for the permitted cases, and 401/403/503 as appropriate for the existing auth contract.
- [ ] Run `uv run pytest tests/test_workspace_diagnostics.py tests/test_bitacora_y_gasto.py -q`; confirm new isolation tests fail for the intended reason.
- [ ] Implement filtering before sort/slice and session-derived scope. Retain the response keys and sample/top-group limits. Protected `donde` returns `uso="uso"`, `errores="errores"`, `retencion_dias="90"`; open local mode retains existing path values. Update the card's unconditional “Detalle completo en …” wording so logical categories do not pretend to be filesystem locations. Add assertions that protected JSON contains neither the configured data directory nor foreign error content.
- [ ] Rerun focused tests; run `npm --prefix apps/web run lint` and `npm --prefix apps/web run typecheck` for the copy edit. Commit only this task's files as `fix: isolate workspace diagnostic queries`.

### Task 2: Sanitize diagnostic paths and text

**Files:** Create `common/diagnostics.py` and `tests/test_diagnostics.py`; modify `apps/api/observability.py`, `common/bitacora.py`, `apps/api/main.py`.

**Interfaces:** `sanitize_path(path: str) -> str`; `sanitize_text(text: str, limit: int = 600) -> str`. Keep `apps.api.observability.redact_request_path(path: str) -> str` as a compatibility wrapper. Keep `bitacora.redactar` as a wrapper using the shared text sanitizer, avoiding circular imports.

- [ ] Add parametrized redaction tests for `/auth/reset/TOKEN`, `/auth/verify/TOKEN`, `/auth/invitations/by-token/TOKEN/accept`, and `/compartido/TOKEN`. Assert `TOKEN` and query values are absent, action suffixes survive, and `/auth/verify/send` is unchanged. Test URLs embedded in exception text alongside existing key/email redaction.
- [ ] Add real ASGI capture tests for matched success, rejected token request, unmatched token-bearing path, and raised exception. Assert no raw token in captured logs or error JSONL; inspect completion logs and exception records, not only sanitizer return values. Use synthetic routes and no external network.
- [ ] Run `uv run pytest tests/test_diagnostics.py -q`; confirm failures expose the current omissions.
- [ ] Implement shared sanitizers. Prefer the matched route's `.path` template; sanitize a query-free fallback when routing did not resolve. Sanitize persisted messages and traces as well as request completion paths. Audit additional logging call sites identified by `rg -n 'logger\.|log_stage|request.url|scope.*path' apps/api` for bypasses within these request/exception paths.
- [ ] Rerun new tests plus `uv run pytest tests/test_vercel_auth_routing.py tests/test_api_lifespan.py -q`. Commit as `fix: redact authentication tokens from diagnostics`.

### Task 3: Define safe correlation and lifecycle contracts

**Files:** Modify `common/diagnostics.py`, `common/logging.py`, `common/bitacora.py`, `apps/api/observability.py`, `apps/api/main.py`; extend `tests/test_diagnostics.py`.

**Interfaces:** Frozen `DiagnosticContext` dataclass with string fields defaulting to `""`: `request_id`, `workspace_id`, `user_id`, `project_id`, `job_id`, `run_id`. `bind_context(context: DiagnosticContext) -> ContextManager[None]`; `current_context() -> DiagnosticContext`; `context_from_request(request: Request, *, project_id: str = "") -> DiagnosticContext` lives in `apps/api/observability.py`.

**Lifecycle schema:** `emit_job_event(event: str, context: DiagnosticContext, *, outcome: str, stage: str = "", duration_ms: float | None = None, error_code: str = "") -> None`. Logger `klave.jobs`; JSON message with `schema_version=1`, UTC `ts`, context fields, and these explicit arguments. Allow events `job_admitted`, `job_started`, `job_stage_changed`, `job_completed`, `job_failed`, `job_interrupted`; outcomes `queued`, `running`, `succeeded`, `failed`. No arbitrary payload fields. Emission is best-effort, including logging-handler failures.

- [ ] Test nested context binding/reset and two interleaved contexts. Assert `current_context()` returns its prior value after a raised exception. Test `context_from_request` against forged actor/workspace headers: IDs must come from `request.state.user`, request ID from state, project from its explicit authorized argument.
- [ ] Test lifecycle JSON field allowlist, UTC timestamp, version, invalid event rejection without impacting the caller, and handler failure containment. Test that the existing request log still carries `rid` when no diagnostic context is present.
- [ ] Run `uv run pytest tests/test_diagnostics.py -q`; confirm the new APIs are missing before implementation.
- [ ] Implement contracts and logging filter enrichment while retaining `request_id_var` compatibility. Add optional default-empty `user_id`, `job_id`, `run_id`, `operation`, and `error_code` fields to `ErrorRegistrado`. Enrich API exception records from authenticated request state at handling time; do not depend on an inner middleware binding surviving stack unwinding. Validate/sanitize fields on new writes.
- [ ] Rerun diagnostic, isolation, and bitacora tests. Commit as `feat: add scoped diagnostic correlation context`.

### Task 4: Persist private origin context and bind workers

**Files:** Modify `apps/api/jobs.py`, `apps/api/routes/projects.py`; create `tests/test_job_diagnostics.py`; extend `tests/test_projects_api.py`.

**Interfaces:** `Job.diagnostic_context: DiagnosticContext` with an empty default. `Job.to_record() -> dict[str, Any]` adds a `diagnostic_context` object to the existing public dictionary for disk persistence only. `Job.to_json()` remains public and unchanged. `Job.from_json` accepts both old public-shaped and new disk-shaped records. Extend `JobStore.enqueue(project_id, root, settings, *, context: DiagnosticContext | None = None) -> tuple[Job, bool]`.

- [ ] Write old/new serialization round-trip tests; assert `diagnostic_context` is absent from `to_json()` and all captured `job_updated` SSE payloads. Persisted context must include the originating reference and generated job/run IDs. Malformed private metadata loads as empty context rather than corrupting an otherwise valid old job.
- [ ] Test active-job reuse under a different user/context: assert same job ID and original context. Test two jobs through one worker thread: inspect `current_context()` inside the stub pipeline and after completion/failure; assert no inherited identity.
- [ ] Extend route tests to capture `enqueue` keyword context for upload, explicit processing, and adding sheets. Assert the request reference/project reach each call and authenticated IDs cannot be forged. Use the isolated test app/store pattern from Task 1.
- [ ] Run `uv run pytest tests/test_job_diagnostics.py tests/test_projects_api.py -q` and confirm intended failures.
- [ ] Implement private persistence at both job-file writes; explicitly bind context around the worker body with guaranteed reset. Capture request context at the three HTTP call sites. Keep other callers working with no context and keep duplicate admission idempotent.
- [ ] Rerun focused tests and `tests/test_events_authorization.py`; commit as `feat: correlate processing jobs with initiating requests`.

### Task 5: Record lifecycle and worker failures consistently

**Files:** Modify `apps/api/jobs.py`; extend `tests/test_job_diagnostics.py`, `tests/test_api_lifespan.py`, and `tests/test_diagnostics.py`.

**Interfaces:** Consume Task 3's context and event contracts. Fixed stage codes: `queued`, `processing`, `converting`, `reading`, `completed`, `failed`, `interrupted`. Map known progress prefixes `Convirtiendo planos` and `Leyendo el dibujo` to converting/reading; other progress remains `processing`. Never include source filenames in lifecycle stages. Error codes: `conversion_failed`, `processing_failed`, `processing_interrupted`.

- [ ] Test successful publication event order: admitted → started → stage changes → completed. A synchronous fake executor must still observe admission first. Repeated same mapped stage produces no duplicate stage-change event. Terminal events include nonnegative monotonic elapsed duration for live runs; recovery omits unavailable monotonic duration.
- [ ] Test forced conversion and unexpected pipeline failures: each produces durable failed job state, one `ErrorRegistrado` with request/workspace/user/project/job/run fields and stable error code, and one failed lifecycle event. Capture the failing mapped stage before overwriting the UI stage with `Error`.
- [ ] Test restart recovery twice: only the first active-to-failed transition emits `job_interrupted`; it records one associated diagnostic error. Existing completed jobs remain completed. Historical missing context remains unattributed.
- [ ] Test diagnostic writer/emitter failures leave processing/publication behavior intact; a mocked actual job-record persistence failure must still surface rather than being swallowed. Test prewarming failure after publication: preserve the published successful run and report a separate safe warning, without changing the completed job to failed. Keep this adjustment confined to prewarming's exception boundary.
- [ ] Run new tests to confirm intended failures; implement lifecycle placement, worker error recording, and one-time recovery emission. Bind the initiating request ID for existing worker log lines too. Preserve existing business logic and public error wording.
- [ ] Rerun all new suites and existing project/startup tests. Commit as `feat: record correlated processing lifecycle and failures`.

### Task 6: Verify the complete support-reference path

**Files:** Create `docs/diagnostics.md`; update this plan's checkboxes and approved spec implementation status after actual completion. Extend existing integration tests only where the full flow is not already proved.

- [ ] Add/run an integrated synthetic request → admission → controlled worker failure → private disk record → scoped `/workspace/errores` lookup. Assert the response's `X-Request-Id` matches job origin and error record, and another workspace cannot retrieve it. Drain/shut down test executors so tests cannot leave live workers behind.
- [ ] Run `uv run pytest tests/test_diagnostics.py tests/test_workspace_diagnostics.py tests/test_job_diagnostics.py tests/test_bitacora_y_gasto.py tests/test_projects_api.py tests/test_events_authorization.py tests/test_api_lifespan.py tests/test_workspace_limits.py tests/test_vercel_auth_routing.py -q`; expect zero failures.
- [ ] Run `uv run pytest tests/test_auth.py tests/test_auth_loop.py -q` against the dedicated test PostgreSQL database if available. A skip is an unavailable integration check, never a pass. Do not use production credentials or customer databases.
- [ ] Run `uv run ruff check .`, `uv run mypy packages/klave_engine`, and `uv run pytest -q`. Record baseline/unrelated failures without changing unrelated files. Run `uv run python -m klave_engine.evals.regression_suite` if worker integration changes pipeline invocation. Report private gold-fixture availability explicitly.
- [ ] Write operator instructions for locating a request reference in API logs, private job records, and JSONL errors; explain protected sample semantics and unattributed failures. Include private metadata/retention boundaries, historical-token-log limitation, no external exporter, and the single-process deployment constraint. Use synthetic IDs only.
- [ ] Inspect the final diff for public metadata leaks, arbitrary exception/context serialization, and changes beyond this scope. Use the code-review workflow before integration. Commit verified documentation as `docs: describe correlated diagnostic operations`; report checks and any unavailable evidence. No deployment is part of this plan.

## Execution Recommendation

Use native execution in the current chat: these six tasks share a small number
of interfaces and mostly modify the same backend boundary. Sequential execution
keeps schema, middleware, and worker changes coherent. Subagent-driven execution
is an alternative if the user prefers separate task reviews and their added cost.

Before execution, read the approved spec and this plan, establish isolation with
the worktree skill, preserve untracked user work, and run the relevant baseline
checks. Plan approval and execution-method selection are still pending.
