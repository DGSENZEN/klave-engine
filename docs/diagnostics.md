# Diagnosing requests and processing jobs

Klave keeps diagnostics on the API host. Customer workspace administrators can
read their own recent error sample; they do not gain platform-wide access.
Unattributed and system failures are available only through operator access to
server files/logs. No external telemetry exporter is enabled by this change.

## Follow a support reference

A browser API response carries `X-Request-Id`. Unexpected API errors also return
`request_id` in their JSON body. The reference is a correlation hint, not an
identity credential or a guarantee of uniqueness. Combine it with time and
job/run IDs when a proxy or client reuses a reference.

1. Search API container logs for `rid=<reference>` or the lifecycle JSON field
   `"request_id": "<reference>"`. Use the existing Compose project and private
   operator configuration; do not paste credentials into support tickets.
2. Look for `klave.jobs` lifecycle records: admitted, started, stage changed,
   completed, failed, or interrupted. They contain `schema_version: 1`, UTC `ts`,
   stable event/stage/outcome values, and available request/workspace/user/project/
   job/run IDs. Live elapsed durations use a monotonic clock; restart recovery
   does not invent elapsed time.
3. Under the configured data directory, inspect the project's processed control
   directory: `jobs/<job_id>.json` and `latest_job.json`. Their private
   `diagnostic_context` stores the origin. Public status and SSE payloads exclude
   that object. Existing records without it remain readable and unattributed.
4. Error details are daily JSONL under `bitacora/errores/YYYY-MM-DD.jsonl` in the
   data directory. Match `request_id`, `job_id`, and `run_id`. Worker failures use
   stable codes `conversion_failed`, `processing_failed`, or
   `processing_interrupted`. The fixed `stage` preserves the failure location. Terminal failure diagnostics
   follow durable failed-state persistence. If that actual persistence fails,
   the operational exception remains real; terminal diagnostics may be absent.

Do not send entire log files, private job records, or drawing artifacts to a
customer or external service. Give them the support reference and a relevant
explanation. User/workspace IDs are internal diagnostic data.

## Workspace error sample

`GET /workspace/errores` requires an authenticated workspace admin in protected
mode. The workspace comes from the session; query parameters cannot override it.
Records from other workspaces and records without ownership are excluded before
sorting and limiting. The response retains at most 200 records from its recent
seven-day reader window, grouped into at most 20 route/type groups.

`total` counts that bounded sample, not all failures or an error-rate denominator.
A zero result means no matching recorded incidents, not proof that a browser or
network failure never happened. The protected `donde` object contains logical
categories (`uso`, `errores`) and retention days, never host filesystem paths.
Explicit open local-development mode retains the operator view and local paths.
Production database failure never enables open mode.

## Retention and data boundaries

The existing JSONL retention is 90 days, pruned on writes. Container log rotation
and job/run retention remain governed by existing deployment settings. Backup
copies follow their own retention. This change does not rewrite or delete old
logs; historical request logs may contain reset or verification token URLs.
Keep their access restricted and apply existing operator retention procedures.

Application logs and Uvicorn exception tracebacks are sanitized before their
handlers render them. Existing application log calls are best-effort so a
throwing handler cannot turn successful processing into a failed job.
New request logs prefer route templates and redact token-bearing fallback paths.
Query strings, passwords, cookies, authorization headers, and request bodies are
not collected by the new instrumentation. Error text uses bounded token/key/email
redaction; it is still internal diagnostic text rather than a public data feed.
New lifecycle records accept only fixed fields and stage labels, not arbitrary
progress text or drawing filenames. Exception context dictionaries are excluded
from new persisted error records.

The scheduler remains single-process and single-host. Diagnostic write failures
must not block processing; actual job/artifact persistence failures remain real
operational failures. A failed export prewarm after publication leaves a
successfully completed run intact and produces a warning.

## Verification and release

Use synthetic projects for controlled failures. Test the path from an
authenticated processing request, through persisted private origin metadata, to
the caller's workspace error sample; then confirm another workspace cannot see
it. Test thread reuse and interrupted recovery too. Never induce a failure in
customer work to demonstrate diagnostics.

Deploy only through the existing verified release procedure. No new dependency,
PostgreSQL migration, provider credential, or infrastructure service is required.
This increment does not provide frontend click analytics, host metrics, external
alerts, a platform-admin web interface, or distributed provider tracing.
