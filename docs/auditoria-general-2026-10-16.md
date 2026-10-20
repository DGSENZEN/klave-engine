# General audit — 2026-10-16

Reviewed project access, folder imports, upload failure handling, live event
delivery, application startup, and web documentation. Ran the Python suite,
engine evaluations, linters, and type checks. Existing uncommitted detection,
evaluation, and deployment changes were preserved.

## Confirmed issues fixed

| Trigger | Previous behavior | Corrected behavior |
|---|---|---|
| Upload the 40th sheet | Rejected a valid project because indexing starts at one | Accepts 40 sheets and rejects additions beyond 40 |
| Add sheets to an imported project with root-level drawings | Counted only `drawings/`, allowing the total to exceed 40 | Counts the same source files ingestion reads |
| A later file in an upload batch fails validation | Earlier files remained despite the rejected request | Removes files created by the rejected batch |
| A destination already exists | Exclusive-open failure deleted the existing drawing | Cleanup only removes a destination this request created |
| Upload reading or ingestion raises an I/O error | Left partial new projects or added sheets behind | Removes incomplete uploads and restores the prior drawing set |
| Adding sheets fails after ingestion writes the manifest | Rollback re-ingested and reset processing status | Restores the manifest captured after streaming, preserving metadata edits made during upload |
| Reimport an existing project's server folder without ownership | Overwrote its manifest and upgraded the caller to owner | Checks ownership before any write, including nested folders and retained manifests of soft-deleted projects |
| A member has a stale grant to another workspace's project | Project role could override workspace isolation | Workspace membership is checked before project role for every user |
| Users database fails while assigning a new project | Published an unassigned project that could fall back to the default workspace | Returns 503 before registration; new uploads are removed |
| Publish an event between draining the SSE buffer and reading its sequence | Advanced past the event without delivering it | Captures the sequence before draining, retaining concurrent events for delivery |
| Create the API application | Used deprecated startup hooks and emitted repeated warnings | Uses lifespan while retaining interrupted-job repair and best-effort startup |
| Follow the web README | Described outdated registration behavior and the wrong icon library | Documents production setup, registration modes, and Phosphor icons accurately |

Implementation: `apps/api/routes/projects.py`, `apps/api/auth/access.py`,
`apps/api/routes/events.py`, `apps/api/main.py`, and `apps/web/README.md`.

Added 43 regression cases across `tests/test_uploads.py`,
`tests/test_project_import_access.py`, `tests/test_events_stream.py`, and
`tests/test_api_lifespan.py`. Reproduced the relevant failures before fixing
them. Independent review caught the soft-deleted nested import and upload
snapshot timing cases; both received regressions and corrections.

## Verification

| Check | Result |
|---|---|
| `.venv/bin/pytest` | 8,344 passed; 17 skipped; 2 dependency warnings |
| `.venv/bin/ruff check .` | Pass |
| `.venv/bin/mypy packages/klave_engine` | Pass; 208 source files |
| `npm --prefix apps/web run lint` | Pass |
| `./node_modules/.bin/tsc --noEmit` from `apps/web` | Pass |
| Demo regression evaluation | Pass |
| Gold evaluation | All 8 entries pass; none unavailable |
| Lifespan tests with deprecations treated as errors | 4 passed |
| `git diff --check` | Pass |

The 17 skipped tests require the local users PostgreSQL service. New access
regressions exercise the real route and authorization logic with isolated
user-store doubles; database integration remains unverified here.

The remaining warnings originate in Google GenAI's Python typing imports
and joblib's physical-core detection. Application startup deprecations were
removed without suppressing warnings.

## Production build limitation

`npm --prefix apps/web run build` cannot load the native
`@next/swc-darwin-arm64` compiler: its package metadata exists locally, but
the binary is missing. A dependency installation without manifest or lockfile
changes did not restore it. Fetching the exact compiler package was then
blocked because automatic approval review hit a usage limit, rather than
because it judged the action unsafe. Production compilation remains
unverified until the compiler can be restored and the build rerun.
