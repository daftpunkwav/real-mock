# RealMock

AI mock interview app: upload a resume to get parsing and an in-depth review, prepare with the Prep interview coach, then practice in a realistic interview room with live Q&A (voice included). Next.js + React frontend, Python modular monolith (FastAPI) backend.

## Directory Layout

| Directory | Purpose |
| --- | --- |
| [`apps/`](apps/README.md) | Deployable applications — see each app's README |
| [`apps/web`](apps/web/README.md) | Frontend (Next.js, runs in dev mode on port 8080) |
| [`apps/api`](apps/api/README.md) | Backend (FastAPI, port 8081): the `realmock` package (src layout); `platform` (platform kernel) / `domains` (seven domains: profile / resume / settings / prep / interview / records / growth), aggregated into a single process by `realmock.asgi`; tests live in [`apps/api/tests`](apps/api/tests/README.md) |
| [`scripts/`](scripts/README.md) | Development and generation scripts (`dev.sh`, `export_openapi.py`) |
| [`protocol/`](protocol/README.md) | WebSocket message protocol schema (`interview_ws.schema.json`) |
| `logs/` | Runtime logs (created and written by `dev.sh`) |

## Local Development

```bash
# Start frontend + backend in one command (runs in background; logs in logs/, PIDs in logs/*.pid)
scripts/dev.sh start

# Stop
scripts/dev.sh stop
```

Manual startup:

```bash
# Backend: install as an editable package once, then start by package name (no PYTHONPATH needed)
pip install -e ./apps/api
python -m uvicorn realmock.asgi:app --host 127.0.0.1 --port 8081

# Frontend: must stay in dev mode
cd apps/web && npm run dev
```

The deep-review concurrency cap (3) is counted **per process** and is not shared across processes. With `uvicorn --workers N`, total concurrency is about N×3. Keep a single worker in local development.

## Tests & Contract

```bash
cd apps/api && pytest    # backend tests (testpaths = tests, grouped by domain / layer)
cd apps/web && npm test  # frontend tests (vitest)
```

API contract pipeline: `scripts/export_openapi.py` → root `openapi.json` → `apps/web/src/types/generated/api.d.ts` (`cd apps/web && npm run generate:api-types`).

## License

[MIT](LICENSE)
