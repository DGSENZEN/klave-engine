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

## Sign-in

`/bienvenida` establishes the workspace identity. Two paths:

- **Nombre local** — always available; the display name feeds change
  attribution and presence.
- **Google** — enabled when `AUTH_GOOGLE_ID`/`AUTH_GOOGLE_SECRET` are set
  (see `.env.example`). The OAuth code flow runs server-side in
  `app/api/auth/*` and stores an HMAC-signed, HTTP-only session cookie; no
  database is required. Set `AUTH_SECRET` outside development.

Sign-in currently gates the web identity only: the local FastAPI backend on
this branch has no server-side authentication (hosted OIDC lives with the
cost-data platform).

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
