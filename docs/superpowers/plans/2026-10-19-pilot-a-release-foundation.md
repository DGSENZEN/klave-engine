# Pilot A: Build and Release Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** produce a verified application build and a single release runner that exercises real services without production credentials.

**Architecture:** extend scripts/release_check.py and existing Make targets. Add an isolated Playwright environment and an isolated container smoke configuration; CI invokes the same entry point as a developer. Customer-specific cases are added by Plan B.

**Tech Stack:** existing Python and Node stacks, Playwright Chromium, Docker Compose, GitHub Actions.

**Spec:** approved 2026-10-19-invited-pilot-readiness-design.md, sections 2, 5, 8, and 9; shared constraints in 2026-10-19-invited-pilot-readiness.md also apply.

## Global Constraints

- "Once dependencies and assets are installed, application compilation must not need Google Fonts connectivity."
- "Database-backed auth tests are mandatory for release verification."
- "Tests use disposable databases and temporary data directories, never a configured production database or the developer's drawing folder."
- "Do not publish private plans in the CI repository or artifacts."
- Keep existing public API and numerical results unchanged.
- Tool-version baseline observed locally: Node 24.13.0 and uv 0.9.24. Pin these explicit versions for this first verification baseline; resolve and record immutable base-image digests when implementing, rather than inventing them in this plan.

## Review Focus

- Inherited development variables must not override the chosen release configuration (A3).
- A missing auth test database must fail instead of producing a green run with skipped auth modules (A3).
- A browser test must fail rather than attach to an existing developer server (A2).
- An interrupted smoke run must remove only resources it created (A3).
- Compilation must preserve font families/weights while Google Fonts is unreachable (A1).

## File map

| Files | Responsibility |
|---|---|
| apps/web/app/layout.tsx; apps/web/app/fonts/; apps/web/app/fonts/OFL-*.txt | Local font assets and licenses |
| .node-version; apps/web/package.json; apps/web/package-lock.json; apps/api/Dockerfile; apps/web/Dockerfile | Pinned tools/dependencies and container build inputs |
| apps/web/playwright.config.ts; apps/web/e2e/; scripts/pilot_test_env.py; packages/klave_engine/common/config.py; apps/api/main.py; apps/web/next.config.ts | Disposable browser environment, explicit config isolation, and real API setup |
| deploy/compose.smoke.yml; deploy/smoke.py | Isolated smoke topology and image checks |
| scripts/release_check.py; Makefile; .github/workflows/release-check.yml | One release entry point and CI |
| tests/test_release_check.py; tests/test_pilot_test_env.py; tests/test_container_smoke.py | Runner and lifecycle regressions |

### A1: Compile with bundled fonts and pinned build tools

**Files:** modify layout.tsx, both Dockerfiles, web package.json and package-lock.json; create .node-version and apps/web/app/fonts/ with three variable WOFF2 assets and their redistribution licenses.

**Interfaces**

- Consumes: existing CSS variables --font-geist-sans, --font-geist-mono, --font-space-grotesk.
- Produces: the same three variables through next/font/local; standalone web output remains unchanged.
- Build-tool contract: Node 24.13.0; uv 0.9.24; Python 3.12 image; frozen uv and npm lockfiles. Resolve the exact base image digests once with Docker and record them in Dockerfiles.

- [ ] **Step 1 — Confirm the existing failure.** Run npm --prefix apps/web run build in the restricted-network environment. Preserve the Google Fonts fetch failure as the regression evidence; do not add a test that merely searches for an import string.
- [ ] **Step 2 — Bundle assets.** Obtain the three existing font families from their official distributions, retain licenses, and record source/version in the fonts directory. Use a variable asset for each family and preserve Space Grotesk weights 500–700. Do not silently substitute a system font if asset retrieval is blocked.
- [ ] **Step 3 — Change build inputs.** Replace the three Google font imports in layout.tsx with local font declarations. Pin the tool versions and base-image digests above, keep Next.js 16.2.9/React 19.2.4, and regenerate a lockfile only for an intentional dependency change. Use uv sync --frozen and npm ci.
- [ ] **Step 4 — Verify.** Run npm --prefix apps/web run build, run typecheck and lint, then compile the installed web sources in a container build step with network disabled. Expect successful standalone output with no font fetch. Render welcome/home at 1440 and 390 CSS pixels and inspect typography and overflow.
- [ ] **Step 5 — Commit.** Inspect the exact asset/config diff and licenses; commit as build: bundle pilot fonts and pin build tools.

### A2: Add an isolated real-service browser harness

**Files:** create scripts/pilot_test_env.py, tests/test_pilot_test_env.py, apps/web/playwright.config.ts, apps/web/e2e/fixtures.ts, apps/web/e2e/smoke.spec.ts, apps/web/e2e/fixtures/structural-meters.dxf, apps/web/e2e/fixtures/expected.json, and apps/web/e2e/README.md; modify web package/lockfile, .gitignore, packages/klave_engine/common/config.py, apps/api/main.py, and apps/web/next.config.ts.

**Interfaces**

- Produces CLI: uv run python scripts/pilot_test_env.py serve --state-dir ABSOLUTE_TEMP_DIR. It creates disposable PostgreSQL resources, seeds accounts/catalog fixtures, launches one API process on 127.0.0.1:18000, and launches next start on 127.0.0.1:13000.
- Produces CLI: uv run python scripts/pilot_test_env.py seed --state-dir ABSOLUTE_TEMP_DIR, for the container smoke runner to seed its own isolated database/data volume.
- Produces private state file state-dir/state.json: web_url, api_url, admin_email, admin_password, invited_email, second_workspace_project_id, saved_unprocessed_project_id, expected_fixture_path. Restrict permissions; never upload this file as a CI artifact. The saved-unprocessed fixture is real registered project storage with the correct grant; it is used only for deterministic error cases.
- Produces npm scripts test:e2e (playwright test) and test:e2e:smoke (playwright test e2e/smoke.spec.ts). Playwright reads PILOT_TEST_STATE_DIR and starts the serve command with reuseExistingServer=false, workers=1.
- Fixed browser origins are loopback only; serve must receive NEXT_PUBLIC_API_URL=http://127.0.0.1:18000 in the web build and runtime. Release runner rebuilds with the production API URL separately. The harness uses invitation-only registration and normal cookie auth, with development transport only for HTTP loopback.
- Setup uses a disposable PostgreSQL container with a dynamically allocated host port; Python auth unit/integration tests continue to use their existing dedicated :5433 service. Never run them against the browser database.
- Add KLAVE_LOAD_DOTENV=0 as an explicit opt-out in get_settings, API main's load_dotenv call, and the web root-env loader. When set, skip every repository .env read; all other behavior keeps its current default. Harness children always set it and clear provider keys.
- The seed subcommand consumes a backend descriptor in the private state file: host-backed tests use their explicit disposable DSN/data path; container smoke invokes the same setup through a read-only mounted script and fixture directory in the owned API container. Never expose setup as an HTTP endpoint.

- [ ] **Step 1 — Add lifecycle regressions.** In test_pilot_test_env.py write test_rejects_nonempty_unowned_state_dir, test_does_not_reuse_busy_ports, test_cleans_up_only_owned_resources_on_failure, and test_ignores_inherited_production_settings. Assert no external database/data directory is modified and the startup command fails clearly on port collision.

      assert result.returncode != 0  # occupied port or unowned directory
      assert unrelated_file.read_bytes() == original_bytes
      assert child_env["KLAVE_LOAD_DOTENV"] == "0"
      assert child_env["KLAVE_USERS_DATABASE_URL"] == disposable_database_url
- [ ] **Step 2 — Run red.** Run uv run pytest tests/test_pilot_test_env.py -q; expect missing harness behavior. Add a basic browser test that loads /bienvenida and checks its accessible heading; npm run test:e2e:smoke initially has no runnable harness.
- [ ] **Step 3 — Implement lifecycle.** Implement main() -> int in pilot_test_env.py and the dotenv opt-out at the three loaders above. Use explicit environment construction, a run-owned temporary data directory, Docker resource labels, bounded startup waits of 60 seconds, and signal cleanup. Never run global docker compose down or delete an unowned directory. Pin the Playwright version in package/lockfile at installation.
- [ ] **Step 4 — Implement synthetic setup.** Generate a tiny committed DXF with explicit meter units, a simple structural shape already supported by the engine, and a provenance note. Inspect its raw geometry and store expected concept code, quantity, price, and disclosure in expected.json. Seed a deterministic catalog and an administrator via UserStore; create a second workspace/project as the access-isolation control. No production test routes or authentication bypasses.
- [ ] **Step 5 — Verify.** Run the lifecycle tests and the basic browser smoke against next start and the real API. Assert the API is reached, a valid session cookie works after UI login, and an uninvited user cannot register. At teardown prove the run's resources are removed and the developer's :3000/:8000/data directory are untouched.
- [ ] **Step 6 — Commit.** Commit the harness, fixture/provenance, dependency lockfile, and tests as test: add isolated pilot browser harness.

### A3: Connect release stages, container smoke, and CI

**Files:** modify scripts/release_check.py, tests/test_release_check.py, Makefile, both Dockerfiles, docker-compose.prod.yml, docs/despliegue.md; create deploy/compose.smoke.yml, deploy/smoke.py, tests/test_container_smoke.py, and .github/workflows/release-check.yml.

**Interfaces**

- Preserve validate(values: dict[str, str | None]) -> list[str] and config-only CLI behavior.
- Add release_check.run_stage(name: str, argv: list[str], *, env: dict[str, str], cwd: Path) -> int: log stage name, run without shell interpolation, return failure without secret output.
- Full entry point stays make release-check ENV_FILE=ABSOLUTE_ENV_FILE. Add --require-gold to the script for the private-fixture release gate; default CI records gold as outstanding rather than passing it.
- Add deploy/smoke.py CLI build|check|cleanup --state-dir ABSOLUTE_TEMP_DIR. State records the run's Compose project, image IDs/tags, and resources; cleanup refuses resources outside that ownership record.
- Image tags use the source SHA plus a unique smoke suffix; final release records use immutable repository digests after publication. Local smoke never claims an unpublished image ID is a remote digest.
- Compose production services accept image overrides KLAVE_API_IMAGE and KLAVE_WEB_IMAGE for already-built releases, retaining explicit local build support. The smoke file uses throwaway volumes, dynamically allocated loopback ports, and no public Caddy/TLS or backup daemon. It starts the actual production images with production API configuration, then seeds via the existing CLI/setup before authenticated checks.
- The browser harness's loopback production web build is separate from the configured-domain web build. Never reuse a build with the wrong baked API URL.

- [ ] **Step 1 — Add runner regressions.** Extend test_release_check.py with tests asserting stage order, first-failure exit, no secret output on subprocess failure, pinned env-file precedence, missing database failure, missing Docker failure, and propagation of browser/image-smoke failure. Assert both auth modules actually execute; missing :5433 is a failed prerequisite.

      assert result.returncode != 0  # required browser/container stage failed
      assert production_password not in result.stdout + result.stderr
      assert "typecheck" in executed_stages
      assert executed_stages.index("typecheck") < executed_stages.index("browser")
- [ ] **Step 2 — Add resource regressions.** In test_container_smoke.py assert interrupted startup cleans up only its labeled project and a child process failure returns nonzero. Run these new tests and confirm red before implementing the new entry points.
- [ ] **Step 3 — Implement release stages.** Run configuration and Compose validation, Ruff, mypy, full pytest, client tests, ESLint, explicit typecheck, synthetic demo evaluation in a temp data directory, loopback build + Playwright, configured-domain web build, both image builds, and isolated container checks. Add release_check.run_synthetic_eval(state_dir: Path) -> int using the existing run_regression_suite(project_root=state_dir / "demo", reports_dir=state_dir / "reports"); return nonzero unless summary["all_passed"] is true. With --require-gold call the existing gold.run and require both all_passed and an empty unavailable list. Use explicit child environments and KLAVE_LOAD_DOTENV=0 so root .env/provider credentials cannot leak into tests.
- [ ] **Step 4 — Implement container checks.** Verify /health, real PostgreSQL auth, DWG converter --version, a persisted data-volume marker across an API container restart, web HTTP response, and production fail-closed access. Use a bounded subprocess timeout per stage; report the actual failing stage. Plan C1 adds /ready checks and Plan C3 adds recovery verification.
- [ ] **Step 5 — Add CI.** On pull_request and push to the repository's actual default branch, provision PostgreSQL 16 at the test port 5433, Node 24.13.0, uv 0.9.24, Python 3.12, and Chromium dependencies. Install locked dependencies; write a temporary synthetic invite-only env file; invoke make release-check. Require all implemented stages. Use read-only repository permissions, a 45-minute job timeout, and no deployment credentials. Determine the default branch from Git rather than guessing main.
- [ ] **Step 6 — Protect artifacts.** Keep Playwright traces/video off on invitation/login tests; retain sanitized screenshots and reports from synthetic cases only. Do not upload state.json, cookie state, raw service logs with tokens, root data/, or actual customer drawings.
- [ ] **Step 7 — Verify.** Run the runner/resource tests, make release-check with a synthetic env file, and inspect successful container cleanup. Inject a browser failure and a container failure once each; both must fail the top-level command. Record any unavailable Docker/network prerequisites as unverified.
- [ ] **Step 8 — Commit.** Commit only release tooling, CI, and its documentation/tests as ci: verify pilot builds and real-service smoke checks.
