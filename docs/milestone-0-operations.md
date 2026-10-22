# Milestone 0 operator handoff

Use with [release gates](pilot-release-record.md), [diagnostics](diagnostics.md), [EC2](ec2.md) and [deployment](despliegue.md). A second operator must rehearse this with synthetic data before signing G8. Live transport, off-host destination and alert recipient are PENDING by owner decision. This document does not authorize production restoration.

## Identify and diagnose

Privately read `.release-current`; inspect the API's immutable image ID with `sudo docker inspect --format '{{.Image}}' klave-api-1`. Compare it with the successful CI SHA and promoted Vercel deployment in the private release record. Use the selected Compose `ps` and `images --format json`, with the original private env file and project `klave`. Never dump container environments or expanded Compose configuration into tickets.

Accepted source lives in `.releases/FULL_SHA/`. Select that directory's `docker-compose.ec2.yml` with the original `.env.prod` for subsequent operations. Do not rebuild the legacy checkout or overwrite private configuration. Keep prior source, API/backup images and matching pre-upgrade backup through acceptance. An accepted SHA's source directory must not be overwritten by a retry.

`GET /health` checks process liveness; `/ready` requires usable PostgreSQL and writable storage. Readiness 503 does not permit bypassing authentication. Docker unhealthy status does not itself restart a container. Verify real-domain TLS, secure cookies, credentialed CORS, SSE and reconnect separately in a browser.

Use response `X-Request-Id`, UTC time, job ID and run ID to inspect a bounded matching log window, the owning workspace's admin error sample and persisted private job state. Never share entire logs, filenames, invite links, cookies, DSNs or drawing artifacts. Diagnostic JSONL retention is 90 days on writes; container logs rotate at 10 MB × 3. Off-host logs/alerts require private operator configuration, not another tracing platform.

| Failure | Safe action |
|---|---|
| Database unavailable | Inspect database health, network and credentials privately; never migrate from a probe or point tests at production |
| Storage unavailable | Inspect disk/inodes, mounts and permissions; preserve drawings/runs; never delete volumes to free space |
| Conversion failure | Identify actual converter build and input support; preserve source; synthetic DXF is not DWG evidence |
| Failed/interrupted job | Inspect authenticated `/projects/ID/status`; retry saved project through `POST /projects/ID/process`; verify reviews/output; never recompute through GET or upload another copy |
| SSH timeout | Inspect instance state/stable address, approved runner source, security group, host firewall/routes and SSH service privately; compare host fingerprint out of band; never open TCP/22 globally or disable host-key checks |

Restricted runner networking or SSM/OIDC requires a separately reviewed infrastructure change.

## Synthetic recovery and game day

Prerequisites: locked dependencies, Node 24, PostgreSQL 16 test service and `pg_restore`, Docker and Chromium. Use an operator-created synthetic env file, never production credentials.

```bash
uv sync --frozen
npm --prefix apps/web ci
make users-db-up
make release-check ENV_FILE=/absolute/path/to/synthetic.env
```

The mandatory production-image stage builds the real backup image, seeds two synthetic workspaces and priced/reviewed projects, stops original writers, takes and verifies an actual backup, and restores it twice into separate fresh PostgreSQL/data resources. It checks login, roles/access, catalog/alias, reviews, drawing SHA256 and a real XLSX through the API, then checks the original application again. It emits synthetic evidence with image IDs. No skipped stage may count as G1/G5 success; failed cleanup is an operator incident.

Archive/readiness mechanics can also run against an existing owned smoke state:

```bash
uv run python deploy/recovery_check.py --state-dir /absolute/owned/smoke --backup /absolute/completed/stamp
```

This rejects unowned state, validates integrity before allocating resources, restores fresh resources, probes readiness and cleans them. It does **not** perform private customer acceptance. Readiness-only restoration does not pass G5. A private backup drill needs matching images, isolated private resources, privately supplied existing-account credentials and independently reviewed project/catalog/drawing/export expectations. Record actual evidence privately.

Rehearse only in scratch/staging: stop database (health stays live, readiness fails then recovers); deny scratch storage writes or fill a bounded scratch filesystem; interrupt a running synthetic job and retry saved source; force backup failure; reject candidate readiness. Focused tests cover checksum/archive/symlink/existing-target/restore failure and release interruption. Record observer, incident reference, detection time, containment, recovery, original-data invariants and forensic resources. Shell simulation does not prove cross-version rollback.

## Off-host storage and alert delivery

First select separate controlled storage, verify encryption in transit/at rest and key recovery, restrict access, choose cadence/retention and assign a real alert recipient. A local path or log line does not prove this. Mount the approved destination privately before using the provider-neutral helper:

```bash
uv run python deploy/offsite_backup.py copy \
  --source /private/completed/STAMP --destination /private/approved-mount/STAMP \
  --state /private/operator/offsite-state.json
uv run python deploy/offsite_backup.py check-age \
  --state /private/operator/offsite-state.json --max-age-hours 36
```

The helper verifies source, destination and a fetched-back copy before recording UTC success. Failed copies retain the last success and existing backups; incomplete directories remain forensic evidence. It does not configure a provider, encryption, scheduling or alert delivery. Connect nonzero copy/age exits to the selected scheduler's alert channel and **observe delivery** after an isolated simulated failure. Also monitor public readiness/frontend, local disk/inodes and remote capacity. Keep credentials and sensitive endpoints out of public probe artifacts.

Default local cadence is nightly; initial copy-age threshold is 36 hours. Confirm actual cadence and accepted data-loss window privately. Key loss can make every encrypted copy unrecoverable. Expire old copies only after another fetched-back copy passes application restore; never delete the sole restorable copy after a failed new backup. Keep matching pre-upgrade snapshots for old binaries. Synthetic restore runs each release; schedule periodic private off-host restores and record actual outcomes. Same-host copies and checksum-only checks cannot pass G4/G5.

## Rollback and go/no-go

Failed build leaves the old API serving. Failed stopped-writer backup/readiness or handled interruption restarts the previous image with its Compose configuration and does not advance `.release-current`. Hard kill/host outage cannot execute a shell trap: the operator must inspect marker, previous image and matching snapshot before recovery. Retain failed candidate source for private diagnosis.

Check schema/control-data compatibility before cross-version revert. Image rollback never reverses a migration. For incompatible data, stop writers and restore the matching pre-upgrade snapshot into **new isolated resources**, validate account/isolation/export there, then obtain a reviewed production cutover decision acknowledging post-snapshot write loss. Never restore over live volumes or run `down -v` on `klave`. Rehearse with two actual releases; same-image restore remains labeled as such.

Before customer acceptance, run all selected private gold inputs, explicitly list unavailable fixtures, compare independent human quantities and run actual DWG/DXF conversion. Disclose unknown units/prices and uncovered families. Observe an independently invited estimator, recording elapsed time and every intervention. Review actual XLSX and test import in their real OPUS/Neodata installation. Cover partial sheets, incorrect scale, missing prices, invalid invitations and lost connection. No unattended paid onboarding until mandatory safety gates pass. Keep NO-GO while any mandatory gate is unresolved.
