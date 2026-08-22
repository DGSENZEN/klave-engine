# Auth loop — design (approved 2026-08-22)

Scope A of the "real auth loop → real home → plan reading" sequence.

## Decisions
- **Workspaces in the schema now.** One taller per deployment by default; the
  schema and every query are scoped by `workspace_id` so several talleres can
  share one server. Extra workspaces are created from the CLI
  (`create-workspace`) and bootstrapped with an admin invitation link. No
  switching UI. An email belongs to exactly one workspace (global unique).
- **Email is wired, never faked.** Provider auto-detected from env: Resend
  (`KLAVE_RESEND_API_KEY`) → SMTP (`KLAVE_SMTP_HOST`…) → local outbox
  (`data/outbox/*.json`). When no provider is configured the UI says so and
  the admin hands over a one-time link; "enviamos un correo" is only shown
  when a provider accepted the message.
- **Invitations** carry role + project grants; accepting (password or
  Google with matching email) creates an *active, verified* account.
- **Recovery**: forgot-password by email (1 h token, all sessions revoked on
  reset) and admin-issued recovery link (24 h) as the no-email path, guarded
  by ConfirmDialog and audited.
- **Email verification** is sent on registration and on email change but does
  not block login (no lockouts when mail is unconfigured).
- **Sessions** slide: 24 h, or 30 d with "Recordarme"; per-session list with
  user agent / last seen and individual revoke.
- **Audit log** (per workspace) for invitations, approvals, role changes,
  disables, recovery links, password resets, sharing, project removal.
- **Last-admin protection**: the last active admin of a workspace cannot be
  demoted or disabled.

## Surfaces
API: `apps/api/auth/{common,store,routes,invitations,recovery,account}.py`,
`apps/api/mail.py`, `apps/api/auth/cli.py`.
Web: `/bienvenida` (remember me, forgot link), `/recuperar`, `/restablecer`,
`/invitacion`, `/verificar`, `/cuenta`, `/equipo` (invitations, recovery
links, activity log).
Tests: `tests/test_auth.py`, `tests/test_auth_loop.py` (outbox mail provider).
