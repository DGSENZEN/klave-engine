# Diagnostic isolation and request-to-job correlation

Date: 2026-10-21

Status: approved by the user on 2026-10-21; implemented and locally verified on
2026-10-21. Not merged or deployed.

## Outcome and scope

The approved product direction is an invitation-only pilot with better UX,
product entry, and internal engineering visibility. This first increment makes
existing diagnostics safe to query and connects a processing failure to the
request, user, workspace, project, and run that caused it.

Success means an operator can follow a support reference into a failed job,
while a customer workspace administrator can retrieve only that workspace's
errors. Authentication tokens must not appear in newly generated request logs
or diagnostic records.

Reuse the existing FastAPI middleware, standard-library logging, daily JSONL
records, PostgreSQL identities, and single-process job scheduler. No new service,
database, dependency, or public endpoint is required. Landing/auth/mail polish,
click analytics, provider tracing, host metrics, alerts, and an internal console
remain separate increments. This is correlation within the current deployment,
not a distributed tracing implementation.

## 1. Diagnostic access boundary

Keep `/workspace/errores` and its administrator requirement. In protected mode,
derive its workspace filter from the authenticated session. Apply that filter
before sorting, limiting, counting, or grouping records. Do not accept a client
workspace override. Exclude records with absent, empty, or different workspace
IDs. Mixed historical files remain readable without backfilling ownership.

Preserve explicitly open local-development mode as a local all-records view.
Production remains subject to the existing authentication middleware and must
never fall back to open access when the users database is unavailable.

Keep the response keys compatible. `total` continues to mean the number of
records in the bounded recent sample, now scoped before its existing 200-record
limit. The existing top-20 grouping remains. Document these sample semantics;
this response is not a complete error-rate metric. Remove filesystem locations
from the protected response's `donde` values; retain its object shape using
logical record categories and the retention value.

System and unattributed failures remain in operator-accessible server files.
This increment introduces no platform-admin role or cross-workspace web access.
Existing customer admins gain no internal engineering privileges.

## 2. Safe paths and diagnostic payloads

Use a shared sanitizer at logging and persistence boundaries. Cover existing
invitation, public-share, password-reset, and verification token paths,
including child action paths. Avoid masking static routes such as
`/auth/verify/send` as if they were tokens. Discard query strings from any
diagnostic path input. Use matched route templates when available; retain a
sanitized fallback for middleware denials and unmatched routes.

Apply sanitization before writing request completion logs and API exception
records. Audit the inspected logging call sites for alternate token-bearing
paths. Do not log authorization headers, cookies, request bodies, or URL queries.
New lifecycle records use fixed operation/event names and allowlisted fields.
Exception details use the existing redaction mechanism extended for the known
token paths; new records never serialize arbitrary context dictionaries.

Existing logs are not rewritten by this change. Operators should treat historical
logs as potentially containing token URLs and follow their retention/access
procedures. No deletion or credential rotation is part of this implementation.

## 3. Correlation context

Define an immutable diagnostic context with optional `request_id`, `workspace_id`,
`user_id`, `project_id`, `job_id`, and `run_id`. Values originate from request
state, authenticated identity, authorized project routing, or generated job IDs.
Never use `X-Actor` or client-supplied workspace/user fields as authenticated identity.
The existing validated incoming request ID remains a correlation hint, not an
authorization credential or guaranteed-unique identity.

Bind context to logging with context variables and reset every binding in
`finally`, including failure paths. Request logging must continue to work for
unauthenticated and rejected requests. Missing context uses empty/null fields,
not guessed workspace ownership. Keep the current `X-Request-Id` response contract.

Pass the captured context explicitly to `JobStore.enqueue` from all three HTTP
paths: initial upload, explicit process, and adding sheets. Enrich it with the
new job/run IDs after admission. Duplicate admission preserves the existing
active job's context; it must not overwrite its originating user or request.
Non-HTTP callers can omit context for backward compatibility.

Persist context with private job metadata so restart recovery can identify the
originating run. Separate disk serialization from public serialization: existing
job/status responses and SSE events must not acquire private user/workspace
metadata. Old persisted records load with empty diagnostic context.

Bind the persisted context explicitly inside the thread-pool worker and reset it
on exit. Do not rely on thread-pool propagation of request context. Concurrent
requests, reused worker threads, and restart recovery must remain isolated.

## 4. Lifecycle and failure records

Emit structured, versioned lifecycle records to the existing application log
stream: admitted, started, stage changed, completed, failed, and interrupted.
Each includes the available correlation fields, UTC timestamp, outcome, and
elapsed monotonic duration where the event has one. Stage labels come from a
fixed mapping; arbitrary pipeline progress text is not copied into new records.
Do not log a separate record for every entity or drawing element.

Keep durable job state as the source of truth. Log admission before submitting
the worker so a fast worker cannot precede its admission record. Emit completion
only after the run is published. Failure events distinguish conversion failure
from an unexpected processing exception using stable codes. Recovery emits an
interrupted event only when it changes an active persisted job into failed state.

Add optional user/job/run/operation/error-code fields to `ErrorRegistrado` with
backward-compatible defaults. Both known conversion failures and unexpected
processing failures write a redacted diagnostic record with their correlation
context. API errors retain their existing behavior and gain available identity
context. Do not count one exception twice in the same diagnostic error store.

Logging and diagnostic-write failures must not change admission, processing,
publication, or error responses. Existing artifact/job persistence failures remain
real operational failures; they are not suppressed as telemetry errors.

## 5. Verification

Use synthetic records and fixtures; no real customer drawings or production
mail are required.

- Two protected workspaces: each admin sees only its errors; editor/anonymous
  requests are rejected; unattributed records stay hidden. More than 200 newer
  foreign records must not crowd out the caller's own recent sample.
- Open development retains its explicit local behavior, and protected/production
  database failure never enables it.
- Reset, verification, invitation, and share token values are absent from captured
  request logs and persisted error records on success, rejection, and exception
  paths. Query strings and secrets in fixture messages are redacted.
- Upload, process, and add-sheets requests preserve their origin in private job
  metadata. Active-job reuse does not replace attribution.
- Two users/workspaces on a reused worker thread do not inherit one another's
  context. Bindings reset after success and exception.
- A forced conversion failure and a forced unexpected exception produce a failed
  job and exactly one associated error record each, with the initiating reference.
- Old job JSON still loads. Recovery records the interrupted run once; completed
  records retain their prior terminal state.
- Public job/status/SSE payloads exclude private metadata. Diagnostic write failure
  leaves normal processing behavior intact.

Run focused API/auth/job/diagnostic regressions, then the repository's Python
lint and type checks and relevant broader backend tests. No engine quantity
behavior changes are intended; run the synthetic pipeline regression if worker
integration changes its invocation. Report unavailable private gold fixtures
explicitly rather than treating them as passing.

## 6. Rollout and compatibility

Deploy through the existing verified release pipeline after implementation and
review. This document authorizes no production deployment. No schema migration
or new credential is needed. Existing JSONL/job records remain readable, and the
new optional fields are ignored by older public serializers. Verify old/new job
record compatibility in tests before claiming rollback compatibility.

First local demonstration: initiate processing as an authenticated synthetic
user, force a controlled worker failure, follow the returned request reference
to the persisted job and diagnostic record, and show that another workspace
cannot retrieve the record. Production verification should use a designated test
workspace and a harmless synthetic fixture after deployment is authorized.
