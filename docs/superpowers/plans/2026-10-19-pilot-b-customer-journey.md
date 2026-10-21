# Pilot B: Customer Journey Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** an invited customer can reach a reviewed, priced XLSX export through the real application and recover from common failures.

**Architecture:** retain the existing pages, API helpers, processing store, review authority, and export services. Add a small common error/session boundary, then polish only the touched states and prove the journey with Plan A's browser environment.

**Tech Stack:** Next.js 16.2.9, React 19.2.4, TypeScript, existing FastAPI routes, Playwright Chromium and Node's test runner.

**Spec:** approved 2026-10-19-invited-pilot-readiness-design.md, sections 3, 4, 6, and 8; shared constraints in 2026-10-19-invited-pilot-readiness.md also apply.

## Global Constraints

- "Server state remains the authority for processing, verification, pricing, permissions, and exports."
- "Spanish product copy and the existing visual language remain the baseline."
- "Preserve saved project work and never automatically replay a failed mutation after authentication."
- "Show actual stages supplied by the server; do not invent percentages or completion estimates."
- Core browser success requests use the real API, database, processing, and downloads. Interception is limited to deterministic failure/reconnection cases.
- Reuse existing ui.tsx, dialog, MoneyGate, and role checks; preserve all price/unit/evidence rules.

## Review Focus

- Multiple expired-session responses cause one transition; rejected passwords stay in the sign-in form (B1).
- Saved upload plus queue-full response retains the saved project and avoids a second upload (B2).
- Unsupported files, server rejection, and network failure preserve the user's open-page form context (B2).
- A missed terminal SSE event is recovered by a status refetch (B3).
- A failed export preserves the page and its filters; success requires an actual downloaded workbook (B4).

## File map

| Files | Responsibility |
|---|---|
| apps/web/lib/httpErrors.ts; lib/sessionReturn.ts; components/SessionRecovery.tsx | Common API errors, support ID, and safe sign-in recovery |
| apps/web/lib/api.ts; lib/session.ts; app/layout.tsx; app/bienvenida/page.tsx; app/invitacion/page.tsx | Integrate errors/session handling without replacing clients |
| apps/web/app/page.tsx; components/OnboardingChecklist.tsx; lib/uploads.ts; apps/api/routes/workspace.py | First-project selection, server-reported limits, upload, and saved-project warnings |
| apps/web/app/proyecto/[id]/layout.tsx; components/ProjectLive.tsx; components/ProjectShell.tsx | Processing, interruption, and reconnection |
| apps/web/components/Tablero.tsx; app/proyecto/[id]/resumen/page.tsx; app/proyecto/[id]/presupuesto/page.tsx | Next review action, evidence/pricing links, export feedback |
| apps/web/e2e/*.spec.ts; apps/web/tests/*.test.mjs; apps/web/tests/run.mjs | Browser journeys and focused pure-client checks |

### B1: Recover sessions and distinguish invitation/service errors

**Files:** create lib/httpErrors.ts, lib/sessionReturn.ts, components/SessionRecovery.tsx, tests/http-errors.test.mjs, tests/session-return.test.mjs, e2e/entry.spec.ts; modify api.ts, session.ts, tests/run.mjs, root layout, welcome/invitation pages, apps/api/main.py; create tests/test_support_reference.py.

**Interfaces**

- Move ApiError to httpErrors.ts with constructor(status: number, path: string, detail?: unknown, requestId?: string); re-export the same class from api.ts so existing instanceof checks keep working.
- Add errorFromResponse(response: Response, path: string, notifySession: boolean = true): Promise<ApiError>. Parse JSON best-effort, retain a validated X-Request-Id matching /^[A-Za-z0-9._-]{4,64}$/, and signal session expiry only for 401 when notifySession is true. Never retry a request.
- Add safeReturnPath(candidate: string | null, origin: string): string in sessionReturn.ts. Resolve with URL, require the same origin and a leading single slash, reject authentication-page loops, and otherwise return pathname + search + hash; fallback is /.
- SessionRecovery listens for klave:session-expired, saves the current safe destination under sessionStorage key klave.session.return, and routes once to /bienvenida?reason=session_expired. Successful login consumes/removes that key and uses safeReturnPath again.
- Login, registration, invitation-info/acceptance, recovery, and session-status calls set notifySession=false. Protected account/project/catalog requests set true. Invalid credentials never trigger global navigation.
- Expose X-Request-Id in main.py CORS expose_headers alongside Content-Disposition. Unexpected errors in this journey display a copyable reference only when an actual validated server ID exists.
- Keep fetchAuthStatus's mode union intact; add optional failure: "network" | "service" | "users_db" for unavailable results. Only explicit users_db_unavailable response detail identifies a users database outage.

- [ ] **Step 1 — Add focused failing tests.** Compile the new pure modules in tests/run.mjs and discover every *.test.mjs under tests. Pin these assertions:

      assert.equal(safeReturnPath('//outside.example/x', 'https://app.taller.mx'), '/');
      assert.equal(safeReturnPath('https://outside.example/x', 'https://app.taller.mx'), '/');
      assert.equal(safeReturnPath('/proyecto/p/resumen?q=1', 'https://app.taller.mx'), '/proyecto/p/resumen?q=1');
      assert.equal(safeReturnPath('/bienvenida', 'https://app.taller.mx'), '/');

  Add cases for malformed URLs, backslashes, multiple simultaneous 401s, a non-JSON 503 response, invalid request IDs, and a network error with no response. Assert protected mutation call count remains one after login.
- [ ] **Step 2 — Run red.** Run npm --prefix apps/web test and the new entry browser cases in Plan A's environment. The new module assertions and safe session return must fail before implementation.
- [ ] **Step 3 — Implement the error boundary.** Replace duplicated error construction in the shared fetch helpers with errorFromResponse. Preserve existing server-message fallbacks and ApiError identity. Mount SessionRecovery once; expose CORS response IDs and add TestClient assertions that error responses carry browser-readable IDs without leaking credentials.
- [ ] **Step 4 — Polish entry states.** In invitation state add a distinct service-error case with a retry action, preserving token/name inputs in memory; do not treat a network outage as an invalid invitation. In welcome distinguish service failure, unreachable network, and users database unavailable, with retry/contact-admin copy. Add explicit labels and field-linked errors to the touched invitation/login forms.
- [ ] **Step 5 — Verify browsers.** Through /equipo, a real admin creates an invitation; a fresh browser accepts it and reaches the correct workspace. Verify revoked/expired/missing invitation states and wrong-account recovery. For Google wrong-account handling, exercise the existing callback error notice without automating external OAuth. Revoke the test session server-side, trigger two protected requests, sign in again, and assert one safe return without replaying the rejected mutation. Assert cross-workspace direct navigation is denied.
- [ ] **Step 6 — Verify and commit.** Run client tests, pytest tests/test_support_reference.py tests/test_auth.py tests/test_auth_loop.py, lint/typecheck, and e2e/entry.spec.ts. Commit as feat: clarify pilot entry and session recovery.

### B2: Make first upload and saved-project recovery actionable

**Files:** modify home page, OnboardingChecklist.tsx, uploads.ts, api.ts, and apps/api/routes/workspace.py; extend tests/uploads.test.mjs and create e2e/upload.spec.ts and tests/test_workspace_limits.py.

**Interfaces**

- Preserve uploadProject(files: File[], actor?: string, meta?: { project_name?: string; client?: string }) -> Promise<{ project_id: string; warnings: string[] }>.
- Add upload_limits: { max_files: number; max_file_bytes: number } to GET /workspace/overview and WorkspaceOverview, reading MAX_FILES_PER_PROJECT and settings.max_upload_bytes. Existing defaults are 40 files and 100 * 1024 * 1024 bytes per file.
- Extend validateDrawingFiles(files, limits?: DrawingUploadLimits): string | null, with DrawingUploadLimits = { max_files: number; max_file_bytes: number }. Preflight uses the server-reported limits; when unavailable, retain format/empty-file checks and let the server enforce configurable limits. Never reject a valid customized limit using a stale hardcoded value.
- After upload, navigate to the returned project ID. Keep warnings in a one-use sessionStorage entry klave.upload.warning.<project_id>, consumed by the project layout. The authoritative project status still determines the available retry action.
- Do not retry an ambiguous network-failed upload automatically; the UI advises checking the project list before resubmission because a server may have saved it.

- [ ] **Step 1 — Add regression assertions.** Extend the existing upload tests for the exact byte boundary and 429 saved-project return. Add browser cases that fill project name/client, submit a server-rejected batch, and assert the inputs/file selection remain available. Double-click submission and assert one upload request.

      assert.equal(validateDrawingFiles([{ name: 'plan.dxf', size: 104857600 }], { max_files: 40, max_file_bytes: 104857600 }), null);
      assert.notEqual(validateDrawingFiles([{ name: 'plan.dxf', size: 104857601 }], { max_files: 40, max_file_bytes: 104857600 }), null);
      assert.equal(uploadRequestCount, 1);

  In test_workspace_limits.py add test_overview_reports_configured_limits; set a nondefault settings.max_upload_bytes and assert response.json()["upload_limits"]["max_file_bytes"] equals it.
- [ ] **Step 2 — Run red.** Run npm --prefix apps/web test and e2e/upload.spec.ts. Confirm missing warning display, byte-size preflight, and form-recovery behavior fail where not already implemented; preserve existing passing cases.
- [ ] **Step 3 — Implement the smallest UI changes.** Keep the existing modal and primary upload action. Announce uploading as an indeterminate status; preserve fields on failure; use the common error/support reference. Consume warnings after navigation and show saved/queued distinction plus the existing processProject action for an unstarted project. Dismissing an onboarding guide cannot remove the primary upload action.
- [ ] **Step 4 — Verify failures deterministically.** Intercept only the selected upload request for 422 and network-failure cases. For the queue-full UI case, return 429 with A2's saved_unprocessed_project_id; all subsequent project reads and the processing retry use the real API. Assert one upload attempt and no second upload, then real processing via /projects/{id}/process. Existing Python upload route tests prove the actual save-then-queue-full server behavior. Keep an uninterrupted real upload as a separate browser success case.
- [ ] **Step 5 — Commit.** Run focused client/browser tests, pytest tests/test_uploads.py tests/test_workspace_limits.py, lint/typecheck, and diff checks. Commit as feat: make pilot uploads recoverable.

### B3: Keep processing and live reconnection honest

**Files:** modify project layout, ProjectLive.tsx and ProjectShell.tsx only where failing cases require it; create e2e/processing.spec.ts and extend tests/test_api_lifespan.py.

**Interfaces**

- Consume existing ProjectStatus from api.ts and existing processProject(id). Do not introduce a competing job state model.
- Preserve queued/running/processed/failed, stage text, artifacts_available, job_id, and run_id. Terminal status is always re-read from the server after reconnect.
- Consume the one-use upload warning from B2. A queued-full saved project with no active job exposes processing start; a failed project with older readable artifacts keeps those artifacts visible with a warning.

- [ ] **Step 1 — Add failing transitions.** In processing.spec.ts assert an SSE disconnect cannot permanently strand a processed project, an interrupted job offers retry, and readable prior artifacts remain usable after a failed rerun. Add test_restart_reports_interrupted_job_and_preserves_published_run in test_api_lifespan.py using persisted records; assert the active run is unchanged.

      assert repaired["state"] == "failed"
      assert repaired["stage"] == "Interrumpido"
      assert active_run_after == active_run_before

  In the browser assert the actual project review link becomes visible after reconnection and the processing POST count does not increase.
- [ ] **Step 2 — Run red.** Run pytest tests/test_api_lifespan.py and e2e/processing.spec.ts. Establish which transitions already work before changing them.
- [ ] **Step 3 — Implement only uncovered recovery.** Use existing SSE onopen/status polling and ProjectLive connectionEpoch. Display disconnected/reconnecting state accessibly, retain readable content, and show server stages without simulated progress percentages. Disable processing retry while the request is pending; use server error detail for queue/conversion failures.
- [ ] **Step 4 — Verify lost events.** In the browser disable the stream, let the real server finish, then reconnect and assert the real final state appears within 15 seconds without a second processing POST. Use a persisted interrupted fixture for the browser retry case; test actual process restart against disposable services in Plan C3.
- [ ] **Step 5 — Commit.** Run processing browser cases plus lifespan/event authorization/stream tests. Commit as fix: recover pilot processing after disconnects and restarts.

### B4: Prove review, pricing, evidence, and downloaded output

**Files:** modify Tablero.tsx, resumen/page.tsx, presupuesto/page.tsx, and existing review/pricing components only where acceptance fails; create e2e/journey.spec.ts, e2e/accessibility.spec.ts, and e2e/check_workbook.py; extend tests/test_exports.py only for newly exposed export defects.

**Interfaces**

- Consume A2's real fixture and expected.json, B1's invitation/session flow, B2's upload path, and B3's authoritative processing state.
- Produce CLI: uv run python apps/web/e2e/check_workbook.py PATH_TO_XLSX EXPECTED_JSON. Assert expected sheets, concept code, quantity, unit, price, arithmetic, and existing evidence/disclosure fields; exit nonzero on mismatch. Reuse openpyxl already installed by the project.
- Preserve the existing export_blocked 409 workflow and written override reason. Never bypass a blocking finding to make the test green.

- [ ] **Step 1 — Write the real journey.** Admin invites through the UI; customer accepts, uploads the synthetic DXF, reaches drawing evidence, signs off units/detections/assumptions through current controls, and selects/edits the deterministic price through the UI. Reload and assert persisted review/price. Use page.waitForEvent('download') around the Klave export and inspect the saved workbook with check_workbook.py.

      assert workbook["Presupuesto"] is not None
      assert actual_concept_code == expected["concept_code"]
      assert actual_quantity == expected["quantity"]
      assert actual_price == expected["unit_price"]
      assert actual_amount == expected["quantity"] * expected["unit_price"]

  The checker locates rows using existing workbook headers, not fixed incidental row numbers, and asserts the existing Generadores and Lo que el plano no dio sheet content.
- [ ] **Step 2 — Write failure and access cases.** Assert unknown units cannot display invented money, missing prices remain explicitly unpriced, an export 500 retains page/filter state and offers retry, and a blocked export requires the existing documented reason. Check an unauthorized workspace project and a viewer mutation both fail using real API authorization.
- [ ] **Step 3 — Run red and inspect actual friction.** Run journey.spec.ts. Record each failing customer action and its owning component; amend this task's file list only for those necessary changes. Do not rewrite costing or recalibrate expected quantities.
- [ ] **Step 4 — Polish navigation and export feedback.** Make the outstanding review step reachable from the project; retain existing evidence and pricing links. Show export pending until the download is received and errors inline with a support reference. Prevent duplicate export submissions and keep filters stable.
- [ ] **Step 5 — Verify interaction quality.** In accessibility.spec.ts test keyboard labels/submission, dialog focus entry/return, and visible field errors for touched forms at 1440×900 and 390×844. Assert no page-level horizontal overflow and the primary action is reachable. Inspect screenshots; avoid brittle whole-page pixel snapshots.
- [ ] **Step 6 — Verify and commit.** Run all client/browser suites, affected Python export/review tests, lint, typecheck, and the release command. Commit as feat: complete the invited pilot review-to-export journey. Manual real-drawing and desktop OPUS/Neodata acceptance remains a named shared release gate.
