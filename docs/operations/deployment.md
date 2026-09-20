# Deployment

Container images and CI/CD. Workflows: [.github/workflows/ci.yml](../../.github/workflows/ci.yml) and [.github/workflows/cd.yml](../../.github/workflows/cd.yml); Dockerfiles: root [Dockerfile](../../Dockerfile) (backend api) and [apps/web/Dockerfile](../../apps/web/Dockerfile) (web).

## CI (`.github/workflows/ci.yml`)

Triggers: push to `main` and all pull requests. Concurrency group `ci-<ref>` with `cancel-in-progress: true`; the backend and frontend jobs run in parallel.

| Job | Runner / toolchain | Steps |
| --- | --- | --- |
| `backend` (Backend (ruff / mypy / pytest / audit)) | ubuntu-latest, 20 min cap; Python 3.12 with pip cache keyed on `apps/api/pyproject.toml` | install `apps/api` editable plus pinned `ruff==0.15.20`, `mypy==2.1.0`, `pytest-cov==7.1.0`, `pip-audit==2.10.1`; `ruff check apps/api`; `mypy src` (blocking); pytest full regression with coverage gate `--cov-fail-under=40` over `realmock.platform` and the profile / resume / settings / prep / interview domains; `pip-audit --ignore-vuln PYSEC-2026-311` (chromadb 1.5.9 known issue, no fixed release yet) |
| `frontend` (Frontend (tsc / lint / test / build / audit)) | ubuntu-latest, 20 min cap; Node 24 with npm cache keyed on `apps/web/package-lock.json` | `npm ci`; `npx tsc --noEmit`; `npm run lint`; `npm test`; `npm run build`; `npm run audit` (fails on high+ unless allowlisted in `apps/web/npm-audit-allowlist.json`) |

The backend job sets `TEST_MODE`, `ENV=dev`, `LLM_API_KEY`, `LLM_API_BASE`, and `CORS_ORIGINS` as job env.

## CD (`.github/workflows/cd.yml`)

Triggers: push to `main` (edge tag) and `v*` tags (semver). Auth uses the built-in `GITHUB_TOKEN` (`packages: write`); no extra secrets are required.

| Item | Value |
| --- | --- |
| Job | `release` — "Build and publish images", ubuntu-latest, 30 min cap |
| Matrix | `web`: context `apps/web`, dockerfile `apps/web/Dockerfile`; `api`: context repo root, dockerfile `Dockerfile` |
| Registry | GHCR; image names `ghcr.io/<repository>-web` and `ghcr.io/<repository>-api` |
| Tags | `edge` on the default branch; `{{version}}` and `{{major}}.{{minor}}` for `v*` tags; `sha-<sha>` |
| Cache | GitHub Actions cache, one scope per component (`cache-from` / `cache-to type=gha`) |

## Images

### Backend api image (root `Dockerfile`, build context = repo root)

| Aspect | Value |
| --- | --- |
| Base | `python:3.12-slim` |
| Extra runtime | Node.js installed via apt (Debian bookworm ships Node 18.x) — used by the agent `code_exec` tool for JavaScript snippets |
| Install | `pip install ./apps/api` (`ARG PIP_INDEX_URL` provides an optional mirror for weak networks) |
| Port / entry | 8081; `uvicorn realmock.asgi:app --host 0.0.0.0 --port 8081` |
| Runtime data | DB / Chroma / uploads live under `/app/apps/api/src/realmock/platform/data` inside the container — mount a volume there at runtime |

Besides the Node.js row above, the Dockerfile installs no other extra apt packages on purpose: the agent sandbox shells out to `setpriv` / `runuser` / `unshare` (shipped by bookworm's essential util-linux package) and `nobody` (from base-passwd). Full sandbox enforcement additionally needs runtime privileges the image cannot grant itself (e.g. `docker run --cap-add SYS_ADMIN` plus a writable `/sys/fs/cgroup`); without them snippets still run and every unenforced control is reported back as an explicit isolation note.

### Web image (`apps/web/Dockerfile`, build context = `apps/web`)

| Aspect | Value |
| --- | --- |
| Base / stages | `node:24-slim`; multi-stage `deps` → `builder` → `runner` |
| Build args | `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_WS_URL`, `NEXT_PUBLIC_STREAM_API_BASE` — injected at build time; defaults (`http://localhost:8081`, `ws://localhost:8081`) match a single-host deploy; `env.ts` requires all three in production |
| Port / entry | 8080; `npm start -- -p 8080` with `NODE_ENV=production` |
