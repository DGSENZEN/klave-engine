# Milestone 0 release record

Decision: **NO-GO — operational and observed acceptance gates remain PENDING.**
Record date: 2026-10-22. Never use synthetic regression results as accuracy or customer acceptance claims.

## Baseline and scope

- Plan baseline and implementation parent: `ee2c33014b27e16e28d4d5799f837e806607724c`.
- Candidate: resolve the full SHA of `codex/milestone-0` after the final commit; attach immutable CI evidence to that SHA.
- Topology: Next.js on Vercel; one EC2 API process, PostgreSQL 16 accounts, workspace SQLite catalogs, persistent source drawings, processing state and immutable run artifacts.
- Numerical fixtures, algorithms, prices, bid semantics and workbook layouts are frozen.
- Production addresses, credentials, customer files and backup destinations belong in the private operator copy.
- Operator response on 2026-10-22: deployment transport and encrypted off-host destination **PENDING**. No live release or restore authorized by this record.

## Deployment incident

[Run 39684018436](https://github.com/DGSENZEN/klave-engine/actions/runs/39684018436), deploy job 119519151910, failed at 2026-10-21 22:21:20 UTC: SSH TCP/22 connection timed out, SCP exited 255 before remote execution. Credential preparation and staged frontend verification succeeded; public API verification and frontend promotion were skipped; credential cleanup succeeded. This proves a transport timeout, not its network cause. Instance state, stable addressing, security group, host firewall/routing and approved runner access require private operator inspection. Do not open SSH globally, disable host-key checks or blindly retry.

## Gate register

| Gate | Status | Evidence / remaining work |
|---|---|---|
| G0 baseline | PENDING | Parent SHA above; capture candidate SHA, lock hashes, exact image IDs and private topology after final build |
| G1 test | PENDING | Parent run verify passed; candidate must pass mandatory full release check and PR CI |
| G2 real drawings | PENDING | Private selected fixtures, independent human quantities and DWG converter validation required |
| G3 deployment | PENDING | Transport timeout unresolved; matching backend SHA/image and promoted frontend required |
| G4 off-host backups | PENDING | Operator destination, encryption, access, retention and delivered alert not configured |
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

## Private evidence to attach

Record candidate SHA; SHA256 of `uv.lock` and `apps/web/package-lock.json`; dependency/tool versions; API/backup/web image IDs and registry digests; elapsed checks and warnings; fixture IDs, hashes, source classification (`engine` vs `human`/`crudo`) and unavailable datasets. Record actual backup stamp/manifest, source SHA, off-host transfer/fetch verification UTC times, restore run IDs, rollback snapshot/image pairing, reviewed outputs, scope limitations and reviewer/date. Do not copy secrets or drawings here.

Customer record must include participant independence, format/converter build, coverage/units, unknown prices, elapsed time, every assistance intervention, failures, actual workbook review/import and explicit acceptance. Keep all fields PENDING until observed.
