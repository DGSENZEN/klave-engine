# Klave Web

Next.js workspace for inspecting Klave projects: upload, live processing,
plan viewer, budget, unit prices, schedule, cashflow, and risks.

## Run

```bash
npm install
npm run dev
```

The app expects the FastAPI backend on `http://localhost:8000`; override with
`NEXT_PUBLIC_API_URL`.

## Sign-in and accounts

Authentication lives in the FastAPI backend against a dedicated users
PostgreSQL (`make users-db-up`). The workspace starts in **open mode** (local
name-only identity); creating the first account from `/bienvenida` bootstraps
an active admin and flips it to **protected mode**: sessions required, new
registrations wait for admin approval in `/equipo`, and each project enforces
lectura/edición/propietario roles managed from its Configuración screen.
Google sign-in activates when `KLAVE_AUTH_GOOGLE_ID`/`KLAVE_AUTH_GOOGLE_SECRET`
are set for the API (redirect URI `http://localhost:8000/auth/google/callback`).
Resetting the users database volume returns the workspace to open mode.

## Structure

- `app/` — App Router screens (Spanish-language UI, MXN formatting).
- `components/` — design-system primitives (`ui.tsx`), project shell,
  realtime layer (`ProjectLive`), and the CAD canvas.
- `lib/` — typed API client, SSE/collab helpers, theme and identity.

## Conventions

- All colors come from the tokens in `app/globals.css`; both light and dark
  palettes are defined there and switched via `data-theme` on `<html>`.
- Icons are `lucide-react` only.
- Every data screen renders shape-matched skeletons, an empty state, and an
  error state.
