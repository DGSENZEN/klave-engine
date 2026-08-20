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
