# Milestone 0 release record

Decision: **NO-GO — operational and observed acceptance gates remain PENDING.**
Record date: 2026-10-22. Never use synthetic regression results as accuracy or customer acceptance claims.

## Baseline and scope

- Plan baseline and implementation parent: `ee2c33014b27e16e28d4d5799f837e806607724c`.
- Candidate: resolve the full SHA of `codex/milestone-0` after the final commit; attach immutable CI evidence to that SHA.
- Topology: Next.js on Vercel; one EC2 API process, PostgreSQL 16 accounts, workspace SQLite catalogs, persistent source drawings, processing state and immutable run artifacts.
- Numerical fixtures, algorithms, prices, bid semantics and workbook layouts are frozen.
- Production addresses, credentials, customer files and backup destinations belong in the private operator copy.
- Operator SSM setup was explicitly approved and verified on 2026-10-22. GitHub OIDC and the proposed encrypted S3 backup setup await approved infrastructure changes and live evidence. No live release or restore is authorized by this record.

## Deployment incident

[Run 39684018436](https://github.com/DGSENZEN/klave-engine/actions/runs/39684018436), deploy job 119519151910, failed at 2026-10-21 22:21:20 UTC: SSH TCP/22 connection timed out, SCP exited 255 before remote execution. Credential preparation and staged frontend verification succeeded; public API verification and frontend promotion were skipped; credential cleanup succeeded. Private operator inspection subsequently confirmed a running instance at the configured address and SSH ingress restricted to one fixed operator IP, excluding the hosted runner. Approved role attachment and an SSM-agent restart established a working browser SSM session. GitHub OIDC inspection is explicitly denied by an organization SCP and needs an approved administrator resolution. Do not open SSH globally, disable host-key checks or blindly retry.

## Gate register

| Gate | Status | Evidence / remaining work |
|---|---|---|
| G0 baseline | PENDING | Parent SHA above; capture candidate SHA, lock hashes, exact image IDs and private topology after final build |
| G1 test | PENDING | Parent run verify passed; candidate must pass mandatory full release check and PR CI |
| G2 real drawings | PENDING | Private selected fixtures, independent human quantities and DWG converter validation required |
| G3 deployment | PENDING | Operator SSM works; organization OIDC restriction unresolved; approved role provisioning, successful main run and release parity required |
| G4 off-host backups | PENDING | S3/encryption/versioning/heartbeat templates and copy verifier prepared; approved provisioning, actual copies, access recovery and delivered alerts required |
| G5 recovery | PENDING | Fresh scratch restore, original login/isolation and canonical workbook evidence required |
| G6 rollback | PENDING | Shell failure tests do not establish live cross-version/data rollback |
| G7 customer journey | PENDING | Independent invited estimator, actual outputs and OPUS/Neodata desktop import required |
| G8 handoff | PENDING | Second operator must execute runbook and failure drills; independent review required |

## Coverage matrix

| Evidence | What it establishes | What it does not establish |
|---|---|---|
| Python/client tests | Contracts and targeted failures | Deployment, customer value or real-drawing accuracy |
| Playwright journey | Real service invitation/upload/review/map/XLSX/isolation | DWG converter, actual desktop import or independent usability |
| Synthetic engine evaluation | Frozen synthetic quantities | Private gold or human truth |
| Production image smoke/recovery | Same-image persistence and archive restore | Cross-version migration rollback or off-host operations |
| Private gold | Regression on explicitly available selected inputs | Baselines are not independently verified quantities |
| Cloud release | Exact candidate delivery and public readiness | Restoreability or observed customer acceptance |
| Customer session | Measured supported workflow and desktop compatibility | Unobserved formats, families or accuracy |

## Implementation evidence (not milestone signoff)

- [PR #3](https://github.com/DGSENZEN/klave-engine/pull/3) is ready for review and remains unmerged. Record the current candidate's actual CI merge-checkout SHA from emitted recovery evidence; it differs from the PR branch head.
- Earlier candidate branch head `4279177ece03cfa97f5dfdd02fbbbad2bbec21c0` passed [full CI run 39837566696](https://github.com/DGSENZEN/klave-engine/actions/runs/39837566696), which tested merge checkout `228c30b64604b3605c90099b210df8972fbce1ca`: 9,191 Python tests passed, 71 skipped, 1 xfailed; five Playwright journeys passed against PostgreSQL 16; real production/backup images completed two fresh synthetic restore/export drills. That proves this earlier candidate, not later changes or production parity.
- Current AWS operations additions require a fresh complete CI run, including the dedicated operations image and real AWS CLI tool validation. Preserve its immutable evidence separately after completion.
- Lock SHA256: `uv.lock` = `33d9f061f8b17bba2005110a9abf94852ffbd46749c9166bad88a0902012cdb6`; `apps/web/package-lock.json` = `1bb65709aa8d6b588942b88ec304508a997ef73eed0570b9c0fffe76ba16b90e`. Neither lock nor numerical fixtures changed.
- The 71 skips comprise 68 unavailable private drawing cases, two optional offline-ML tests without scikit-learn and one missing official CDMX reference PDF. All nine selected private gold entries are unavailable and labeled baseline. `make eval-gold` reports PENDING/nonzero; no accuracy or independent-human acceptance claim is made.
- Existing warnings remain: three frontend navigation lint warnings, five high npm audit findings and the action runtime deprecation notice. No forced dependency upgrade was performed.
- Local Docker Desktop is unavailable (control API HTTP 503); actual Linux image/recovery proof comes from CI. No user containers were restarted or pruned.
- Code review fixed backup ownership/state collisions and added pre-transfer scratch capacity/inode reservation. S3 fetch-back checks encryption, immutable versions and archive integrity; source-age checks prevent an old snapshot from becoming fresh on re-upload. These tests do not prove live AWS provisioning or application recovery.
- Live release parity, private DWG/human quantity checks, off-host application restore, cross-version rollback, delivered alerts, observed estimator/import and second-operator game day remain PENDING.

## Private signoff evidence

Record candidate SHA; SHA256 of `uv.lock` and `apps/web/package-lock.json`; dependency/tool versions; API/backup/web image IDs and registry digests; elapsed checks and warnings; fixture IDs, hashes, source classification (`engine` vs `human`/`crudo`) and unavailable datasets. Record actual backup stamp/manifest, source SHA, off-host transfer/fetch verification UTC times, restore run IDs, rollback snapshot/image pairing, reviewed outputs, scope limitations and reviewer/date. Do not copy secrets or drawings here.

Customer record must include participant independence, format/converter build, coverage/units, unknown prices, elapsed time, every assistance intervention, failures, actual workbook review/import and explicit acceptance. Keep all fields PENDING until observed.
