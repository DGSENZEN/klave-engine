# Pilot C: Runtime and Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** distinguish a live process from a usable service, produce trustworthy backups, and demonstrate restoration and rollback in an isolated environment.

**Architecture:** extend existing health/deployment/backup components. Keep one API process and persistent volumes; validate real production images through Plan A's owned smoke environment. Production operation remains a documented operator action.

**Tech Stack:** FastAPI, psycopg, SQLite backup API, PostgreSQL 16 pg_dump/pg_restore, Python tarfile/hashlib, Docker Compose and Caddy.

**Spec:** approved 2026-10-19-invited-pilot-readiness-design.md, sections 6–9; shared constraints in 2026-10-19-invited-pilot-readiness.md also apply.

## Global Constraints

- "Retain /health as cheap process liveness."
- "Public responses contain coarse component statuses and version only, with diagnostic details in logs."
- "SQLite snapshot capability is required for a backup taken while the application writes."
- "Retention must not delete the last complete backup after a failed attempt."
- "Never practice a restore by overwriting the active pilot volumes."
- "Restoring a snapshot discards later writes."
- One API process; no queue/pub-sub migration and no unsupported multi-worker deployment.

## Review Focus

- Reachable PostgreSQL with absent schema is not ready and probes must not migrate it (C1).
- Readiness cleanup failure and an unwritable data volume are visible as 503, without modifying project files (C1).
- Spaces, apostrophes, Unicode, and newline characters in stored filenames survive backup/restore (C2).
- A failed dump/archive or corrupt remote copy cannot become a completed backup (C2/C3).
- Reverting images cannot silently reverse a schema migration; use the matching stopped-writer snapshot when required (C3).

## File map

| Files | Responsibility |
|---|---|
| apps/api/readiness.py; routes/health.py; auth/middleware.py; auth/store.py; main.py | Dependency probe, public readiness route, bounded schema initialization, and startup capability reporting |
| tests/test_readiness.py; tests/test_production_config.py | Readiness contract and fail-closed access |
| deploy/backup.Dockerfile; deploy/backup.py; deploy/backup.sh; docker-compose.prod.yml | Installed backup tools and complete, verifiable snapshots |
| tests/test_backup.py | Packaging, SQLite/WAL, integrity and retention cases |
| deploy/recovery_check.py; tests/test_recovery_check.py; deploy/smoke.py | Owned scratch restore and rollback verification |
| docs/despliegue.md; docs/pilot-release-record.md; Makefile; scripts/release_check.py | Operator commands, evidence record and release integration |

### C1: Add bounded dependency readiness and converter capability checks

**Files:** create apps/api/readiness.py and tests/test_readiness.py; modify routes/health.py, auth/middleware.py, auth/store.py, main.py, API Dockerfile, tests/test_production_config.py, and deploy/smoke.py.

**Interfaces**

- Add check_readiness(settings: Settings) -> dict in readiness.py, with response shape:

      {"status": "ready" | "unavailable", "version": str,
       "checks": {"database": "ok" | "unavailable", "storage": "ok" | "unavailable"}}

- GET /ready returns that object with 200 only when both checks are ok, otherwise 503. /health retains its current shape and 200 liveness behavior during dependency outages.
- Use direct psycopg.connect, connect_timeout=2 and statement_timeout=2000ms. Read to_regclass for workspaces, users, sessions, project_access, project_workspace, invitations, auth_tokens, audit_log. The probe never constructs UserStore or executes migrations.
- Check storage with a uniquely named temporary file under data_dir/.health, write/read/remove it, and treat failed cleanup as unavailable. Do not walk or touch uploads/catalog/project artifacts.
- GET /ready is anonymous through an exact method/path middleware exception, not another broad path-prefix exemption. /ready/anything and protected application routes retain their existing authorization behavior.
- Startup initializes the existing UserStore schema once with its normal bounded connection behavior before readiness can become true; failure logs an unavailable dependency and leaves liveness running. Empty schema is initialized by startup, never by the health request.
- Add UserStore.initialize_schema(self) -> None, reusing the existing _connect schema/migration path. Extend _connect with an optional keyword-only options: str | None = None; initialize_schema supplies PostgreSQL statement/lock timeouts and closes the resulting connection. Ordinary callers retain their current defaults. Never copy the migration SQL into readiness.py.
- Startup logs DWG converter capability using existing converter resolution and a bounded --version check. Cache/report coarse capability internally; do not include executable paths in public health responses or invoke it on each /ready.

- [ ] **Step 1 — Write failing tests.** Add test_ready_returns_200_with_initialized_database_and_writable_empty_volume, test_missing_schema_returns_503_without_ddl, test_database_outage_keeps_liveness_up, test_storage_write_or_cleanup_failure_returns_503, test_concurrent_probes_use_distinct_files, and test_readiness_does_not_exempt_other_paths. Assert passwords, DSN, stack traces, and filesystem paths never appear in JSON.

      assert client.get("/health").status_code == 200
      assert client.get("/ready").status_code == 503  # database or storage failed
      assert "/data/" not in client.get("/ready").text
      assert not any("CREATE" in sql or "ALTER" in sql for sql in probe_statements)

  Test absent schema directly through check_readiness and after removing a relation from an isolated started service; startup preparation must not make this case accidentally pass.
- [ ] **Step 2 — Run red.** Run uv run pytest tests/test_readiness.py tests/test_production_config.py -q; expect no /ready route and missing probe implementation.
- [ ] **Step 3 — Implement probe and startup.** Add check_readiness and the exact public route exception. Bound database work as above; use context managers and temporary files. Log coarse failure category with the existing request ID; do not expose a psycopg exception containing the DSN. Add startup schema preparation without weakening fail-closed checks or orphan-job repair; enforce statement_timeout=10000ms and lock_timeout=2000ms on that initialization connection. Add a blocked-migration regression so startup cannot wait indefinitely for a schema lock.
- [ ] **Step 4 — Integrate container health.** Change the API container's dependency-health check to /ready, keeping /health available for process diagnosis. In deploy/smoke.py assert readiness starts successfully after initialization, turns 503 when the disposable database is stopped, and recovers after restart while /health remains 200. Allow 15 seconds for the existing negative database cache to expire. Check the container runs one Uvicorn process and validates DWG capability.
- [ ] **Step 5 — Verify and commit.** Run readiness, startup, production-config and auth tests plus isolated image smoke. Record that unhealthy status alone does not restart a Docker container. Commit as feat: report pilot dependency readiness.

### C2: Make backup completion and retention trustworthy

**Files:** create deploy/backup.Dockerfile, deploy/backup.py, tests/test_backup.py; modify backup.sh, production Compose backup service, Makefile and deployment docs.

**Interfaces**

- backup.Dockerfile derives from the same pinned PostgreSQL 16 Alpine base as users-db, installs Python 3 at image build time, and copies backup.py/backup.sh. No runtime apk installation.
- Preserve backup.sh once and backup.sh daemon as service entry points; unknown subcommands fail with exit 2. Preserve restore STAMP as instructions-only, updated in C3. once delegates to Python and propagates its exit status.
- backup.py exports run_backup(data_dir: Path, backup_dir: Path, keep_days: int) -> Path and verify_backup(directory: Path) -> dict. CLI commands once and verify DIRECTORY consume existing DB_HOST/PORT/USER/NAME/PGPASSWORD variables without logging secrets.
- Completed directory contains users.dump, sqlite.tar.gz, data.tar.gz, manifest.json, and COMPLETE. manifest.json has format_version=1, stamp, created_at UTC, each archive's byte size and SHA-256; COMPLETE is written last, then the staging directory is atomically published as STAMP. Incomplete directories never qualify for retention or export.
- Use sqlite3.Connection.backup for every catalog database, including live WAL contents. Preserve relative paths using pathlib/tarfile, not whitespace-separated shell loops. Bound SQLite backup progress to 60 seconds and fail on timeout.
- pg_dump and pg_restore --list use subprocess timeouts of 120 seconds. Required tool/dump failure is fatal; no raw SQLite-copy fallback. Sanitize failure output rather than echo DSNs or provider credentials.
- Verification checks hashes, gzip/tar readability, and pg_restore --list. Retention removes only verified completed backups older than keep_days and never the newest complete backup. No pruning occurs after a failed new backup.

- [ ] **Step 1 — Write failing packaging tests.** In test_backup.py cover a catalog database with committed WAL data, nested paths with spaces/apostrophes/Unicode/newlines, byte corruption after packaging, failure of each required archive/dump, invalid retention, and failed verification before publication. Mock only external dump subprocesses for unit cases; compare restored SQLite rows and every non-SQLite file byte-for-byte.
- [ ] **Step 2 — Pin retention assertions.** Seed an older complete backup plus a new partial failure; assert the old complete directory remains and the partial has no COMPLETE. Assert a successful new backup prunes only eligible completed directories and never arbitrary backup-root children.

      assert (previous_complete / "COMPLETE").exists()
      assert not (failed_attempt / "COMPLETE").exists()
      assert unrelated_backup_root_child.exists()
      assert restored_file.read_bytes() == source_file.read_bytes()
- [ ] **Step 3 — Run red.** Run uv run pytest tests/test_backup.py -q. Confirm missing complete-manifest/verification behavior before replacing the fragile packaging path.
- [ ] **Step 4 — Implement packaging.** Implement run_backup/verify_backup with private staging, context-managed SQLite snapshots and archives, and atomic completion. Keep SQLite journal sidecars out of data.tar.gz; catalogs restore from their snapshots. If the source tree changes during copying, fail a detected inconsistent file read rather than claim a verified snapshot. Document that cross-database/project consistency requires a quiesced pre-upgrade backup.
- [ ] **Step 5 — Verify the actual image.** In Plan A's isolated production services, create PostgreSQL accounts and a WAL-mode SQLite catalog, run the real backup image, verify the completed archives, and restore via C3. Test a missing/unavailable dump tool returns nonzero and leaves the last completed backup intact.
- [ ] **Step 6 — Commit.** Run backup unit tests, sh -n deploy/backup.sh and actual backup-image checks. Commit as fix: publish only verified complete pilot backups.

### C3: Prove isolated restore, rollback, and operator release checks

**Files:** create deploy/recovery_check.py, tests/test_recovery_check.py, docs/pilot-release-record.md; modify deploy/smoke.py, backup.sh restore instructions, release_check.py, Makefile, docs/despliegue.md and production Compose image selection.

**Interfaces**

- CLI: uv run python deploy/recovery_check.py --state-dir ABSOLUTE_SMOKE_STATE --backup ABSOLUTE_COMPLETED_BACKUP. It accepts only A3's owned disposable resources, creates a new scratch database and volumes, restores there, then validates through the real API.
- CLI: backup.py verify DIRECTORY is also the off-host integrity check. Copy the completed directory to an operator-selected private destination using their transport; verify on the destination and again after fetching it into scratch storage.
- Extend make release-check with the isolated backup/restore gate using synthetic data only. The runner receives no production DB URL or cloud account.
- docs/pilot-release-record.md is a fill-in operational record with source SHA, image repository digests, dependency lock hashes, test/gold results, backup stamp/checksums, compatibility/migration notes, recovery evidence, cloud checks and observed customer outcome. Pending fields are clearly outstanding gates, never default pass marks.
- Release/rollback commands use the selected immutable images and explicit Compose/env file/project name. They never run a broad volume deletion. The automated drill uses only its owned resources; production restore remains a concrete, reviewed operator operation.

- [ ] **Step 1 — Write failing safety/integrity tests.** Reject an unowned state directory, a backup without COMPLETE, checksum mismatch, symlink or path-traversal archive member, existing target volumes, and a live/non-scratch database target. Assert rejected input performs no restore or deletion. Test that cleanup touches only the generated resource IDs.

      assert result.returncode != 0
      assert restore_calls == []
      assert original_database_rows == rows_after_rejection
      assert original_volume_ids == volume_ids_after_rejection
- [ ] **Step 2 — Write the real recovery drill.** In the disposable original deployment seed an account, workspace/project access, catalog/aliases, synthetic drawing artifacts, and a priced/reviewed budget; stop API/web writers and run C2 backup. Restore PostgreSQL and archives into fresh labeled resources, preserving the original deployment for comparison.
- [ ] **Step 3 — Verify restored behavior.** Start the same images against scratch storage, assert /ready, UI/API login, exact workspace/project membership, catalog values, drawing bytes, and a downloaded XLSX checked by B4's workbook checker. Compare canonical pre/post export cell values, not ZIP bytes or generated timestamps.
- [ ] **Step 4 — Exercise interruption and rollback.** In disposable services persist a queued/running job, restart the API, verify an actionable interrupted state, and retry through the existing route. Record previous image IDs, stop writers, switch to the prior locally recorded images plus the matching snapshot when data compatibility requires it, and rerun readiness/export checks. A same-version restore proves recovery mechanics only; record cross-version rollback as outstanding until two actual releases are available.
- [ ] **Step 5 — Write exact deployment instructions.** Document internal-only startup with users-db/api/web, CLI workspace/admin-invitation bootstrap before starting Caddy, source/image selection, production config validation, backup before upgrade, readiness checks, and rollback with the data-loss window. Keep manual invitation links out of general logs. Explain nightly backups versus quiesced pre-upgrade backups and demonstrate copying/validating a completed directory off-host without choosing a provider.
- [ ] **Step 6 — Add real-domain checklist.** Require HTTPS and secure cookie inspection; browser credentialed CORS; live SSE delivery/reconnect; actual DWG converter capability; upload, review and export; external uptime alert delivery; off-host restore; and operator-recorded image digests. HTTP loopback smoke is explicitly insufficient evidence for these gates.
- [ ] **Step 7 — Verify and commit.** Run uv run pytest tests/test_recovery_check.py tests/test_backup.py tests/test_readiness.py, then the full release command with the synthetic environment. Exercise the restore drill twice to prove ownership-safe cleanup and fresh-resource reuse. Commit as ops: verify isolated pilot restore and document release recovery.

## Operator-only acceptance after local implementation

- [ ] Obtain the chosen cloud host, domain/DNS access, and private backup destination when preparing deployment; no credentials are needed to implement the plan.
- [ ] Fill the release record with actual source/digests and all automated results.
- [ ] Prepare the exact target deployment and review it before publishing or changing live state.
- [ ] Run the real-domain and alert tests, off-host restoration drill, private gold evaluation, and observed invited-customer journey.
- [ ] Record actual OPUS/Neodata desktop import results through the pilot office, and retain unresolved limitations in the release record.
