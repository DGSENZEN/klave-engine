# Invited Pilot Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** ship one independently usable invited-customer journey with repeatable deployment and verified recovery.

**Architecture:** retain the single-host Compose topology and existing domain services. Implement three separately reviewable plans, then apply the shared release gates below. No implementation has started under this plan.

**Tech Stack:** Python/FastAPI/pytest/uv, PostgreSQL 16, Next.js 16/React 19/TypeScript, Playwright Chromium, Docker Compose, Caddy, GitHub Actions.

**Spec:** [Approved design](../specs/2026-10-19-invited-pilot-readiness-design.md), sections 1–9.

## Global Constraints

- "The pilot is invitation-only and uses the existing roles and workspace isolation."
- "Deployment uses one host, persistent Docker volumes, Caddy, PostgreSQL, Next.js, and exactly one API process."
- "Spanish product copy and the existing visual language remain the baseline."
- "Email remains optional: administrators can distribute invitation links manually."
- "Existing customer-data fixtures and gold expectations are preserved."
- Preserve the pre-existing dirty checkout. At execution time use the worktree skill to decide isolation; a fresh worktree does not contain those changes. Never reset, stash, or commit unrelated work implicitly.
- Read apps/web/AGENTS.md and installed Next.js documentation before modifying web code.
- Each task has a focused verification gate and a scoped commit; stage only changes belonging to that task, inspecting the index before every commit.
- Every deployment, private-fixture, and customer acceptance result must identify the release source commit and image digests.

## Review Focus

These five failure modes have explicit tests assigned in the child plans:

1. A saved upload receives a queue-full response: open the saved project, preserve its warning, and do not upload twice (B2).
2. Concurrent 401 responses and a malicious return destination: one safe sign-in transition and no mutation replay (B1).
3. API connectivity returns after the terminal processing event was lost: refetch persisted status and leave the processing screen (B3).
4. Database connectivity succeeds but the schema is absent: readiness remains 503 without migrating during the probe (C1).
5. Backup filenames contain spaces or a required tool fails: preserve filenames, fail clearly, and retain the last complete backup (C2).

## Delivery map

| Order | Plan | Independently testable result |
|---|---|---|
| A | [Build and release foundation](2026-10-19-pilot-a-release-foundation.md) | Offline-capable application compilation, isolated browser harness, one release runner and CI |
| B | [Customer journey](2026-10-19-pilot-b-customer-journey.md) | Invitation through real API processing/review to a checked XLSX download, with recovery |
| C | [Runtime and recovery](2026-10-19-pilot-c-runtime-recovery.md) | Readiness, reliable backups, isolated restoration and release/rollback instructions |

A2 supplies the isolated browser environment consumed by B. A3 starts with a basic browser smoke check and automatically discovers the journey cases added by B. C1 upgrades the container smoke gate to dependency readiness. C2/C3 add backup/restore checks to that same runner.

## Shared release and pilot gates

- [ ] Run make release-check ENV_FILE=/absolute/path/to/synthetic-or-pilot.env. It must perform all required stages from A, B, and C and return zero; no missing auth database or required browser/container suite may count as success.
- [ ] Run make eval-gold on the fixture-bearing machine. Record each fixture result and availability; never recapture gold simply to make it pass.
- [ ] Confirm the release commit contains all intended changes; record immutable image digests and recovery/migration notes. The documentation-only design commit is not the release source.
- [ ] On an isolated cloud/staging deployment, execute the real-domain HTTPS/cookies/CORS/SSE/upload/export checks in C3 before exposing the invited pilot.
- [ ] Restore an off-host backup into scratch volumes, then verify account, project access, catalog, drawings, and export using C3.
- [ ] Observe a newly invited customer complete the real-drawing journey without coaching. Record blocking friction and rerun the affected checks after fixing it.
- [ ] Record generator acceptance and the pilot office's actual OPUS/Neodata import outcome in the existing pilot measurement workflow. Do not infer desktop interoperability from our own reader.

## Execution handoff

The written design is approved. These plans await review and selection of execution method. Native execution keeps implementation in this session; subagent-driven execution uses separate implementers and reviewers for individual tasks. Recommend native execution because the plans share one release runner and browser harness, and the checkout already contains substantial work to preserve.

No cloud deployment, external account creation, customer messaging, or destructive restore is included in local plan execution. Prepare concrete artifacts and isolated checks before requesting deployment-specific operator inputs.

## Plan self-review

Spec coverage: sections 1–2 are carried into all constraints and the baseline; sections 3–4 map to B1–B4; section 5 maps to A1–A3; section 6 maps to B1/C1; section 7 maps to C2/C3; section 8 maps to browser/integration tests and the shared manual gates; section 9 maps to the delivery order above. Every Review Focus item has a named owning task.

Interfaces were checked across the three plans: state.json ownership and saved_unprocessed_project_id originate in A2; release-check originates in A3; request IDs/session recovery originate in B1; upload warnings originate in B2; the workbook checker originates in B4; /ready originates in C1; complete backup format/verification originate in C2 and are consumed by C3. Production acceptance remains explicitly outstanding until it is actually exercised.
