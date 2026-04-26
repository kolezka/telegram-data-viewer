# tg-viewer web

React + Bun frontend for the tg-viewer FastAPI backend.

## Scripts

- `bun run dev` — start dev server on http://localhost:5173 (proxies API to localhost:5000)
- `bun run build` — produce `web/dist/` for production
- `bun run codegen` — refresh `src/api/types.ts` from a running `/openapi.json`
- `bun run typecheck` — `tsc --noEmit`

For development, run `tg-viewer dev` from the repo root — it starts FastAPI on 5000 and Bun on 5173 together.

For production, `tg-viewer webui DIR` runs `bun run build` (if needed) and starts FastAPI on 5000 with `web/dist/` mounted.
