# Klave Web

Next.js workspace for inspecting Klave projects: upload, live processing,
plan viewer, budget, unit prices, schedule, cashflow, and risks.

## Run

```bash
npm install
npm run dev
```

The browser uses `/api` on the same origin by default. Under Vercel Services,
the Next.js API route forwards requests to FastAPI using the runtime
`KLAVE_APP_URL` binding. Do not configure that binding variable yourself.

For separate local processes, set `NEXT_PUBLIC_API_URL=http://localhost:8000`
in the repository-root `.env` before running `npm run dev`. For the complete
multi-service setup, run `vercel dev -L` from the repository root and leave
`NEXT_PUBLIC_API_URL` unset. See [Vercel deployment](../../docs/vercel.md).

## Sign-in and accounts

Authentication lives in the FastAPI backend against a dedicated users
PostgreSQL (`make users-db-up`). In development, a server without accounts runs
in **open mode** (local name-only identity). Creating the first account from
`/bienvenida` bootstraps an active admin and flips it to **protected mode**:
sessions are required, and each project enforces lectura/edición/propietario
roles managed from its Configuración screen. With open registration, founding
a new taller activates its admin immediately; joining an existing taller waits
for approval in `/equipo`. Production requires invitation-only registration
after the first account has been created.
Production servers without accounts require setup and keep project data closed.

## Structure

- `app/` — App Router screens (Spanish-language UI, MXN formatting).
- `components/` — design-system primitives (`ui.tsx`), project shell,
  realtime layer (`ProjectLive`), and the CAD canvas.
- `lib/` — typed API client, SSE/collab helpers, theme and identity.

## Conventions

- All colors come from the tokens in `app/globals.css`; both light and dark
  palettes are defined there and switched via `data-theme` on `<html>`.
- Icons use `@phosphor-icons/react`.
- Every data screen renders shape-matched skeletons, an empty state, and an
  error state.

## Checks

Use Node 24. `npm test` runs the client regressions without extra test dependencies;
`npm run lint`, `npm run typecheck`, and `npm run build` check the web workspace.
From the repository root, `make release-check` also checks the engine and the
private pilot configuration. See [deployment](../../docs/despliegue.md).
