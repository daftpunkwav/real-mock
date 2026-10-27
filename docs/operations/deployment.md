# Deployment

Container images and CI. Workflow: [.github/workflows/ci.yml](../../.github/workflows/ci.yml); Dockerfiles: root [Dockerfile](../../Dockerfile) (backend api) and [apps/web/Dockerfile](../../apps/web/Dockerfile) (web).

## CI (`.github/workflows/ci.yml`)

Triggers: push to `main` and all pull requests. Concurrency group `ci-<ref>` with `cancel-in-progress: true`. A `changes` job classifies the diff, each area job runs only when its area changed, and the `gate` job aggregates the results into the single required check.

| Job | Runner / toolchain | Steps |
| --- | --- | --- |
| `backend` (Backend (ruff / mypy / pytest / audit)) | ubuntu-latest, 20 min cap; Python 3.14 with pip cache keyed on `apps/api/pyproject.toml` and `apps/api/requirements-ci.lock` | install the backend dependencies from the hash-locked `apps/api/requirements-ci.lock` (`pip install --only-binary :all: --require-hashes -r apps/api/requirements-ci.lock`; runtime dependencies plus the `dev` extra — pytest / pytest-asyncio plus the pinned gate toolchain `ruff==0.16.10`, `mypy==2.4.0`, `pytest-cov==7.1.0`, `pip-audit==2.10.1`, `httpx2` — every version pinned and hash-verified); the project itself is not installed as a distribution — the job runs the backend from the checked-out working tree, with `apps/api/src` on `PYTHONPATH`; lock-sync gate (`python scripts/ci/check_python_lock_sync.py`); OpenAPI contract sync check (`export_openapi.py` must leave `openapi.json` unchanged); `ruff check apps/api`; `ruff format --check apps/api`; `mypy src` (blocking); pytest full regression with whole-package coverage gate `--cov=realmock --cov-fail-under=90` |
| `frontend` (Frontend (tsc / lint / test / build / audit)) | ubuntu-latest, 20 min cap; Node 24 with npm cache keyed on `apps/web/package-lock.json` | `npm ci`; `npx tsc --noEmit`; `npm run lint`; `npm test` (vitest with coverage thresholds from `apps/web/vitest.config.mts`); `npm run build`; `npm run format:check`; i18n usage audit (`apps/web/scripts/check-i18n-usage.mjs`, ghost and dead keys) |
| `docker` | ubuntu-latest, 25 min cap | build the backend image (root `Dockerfile`) and the web image (`apps/web/Dockerfile`) |
| `workflow-lint` | ubuntu-latest, 10 min cap | lint the workflow files themselves (syntax / shellcheck, and a workflow security review) |
| `repo-hygiene` | ubuntu-latest, 5 min cap | committed files match `.editorconfig`; no case-insensitive path collisions; documentation bilingual pairs; internal documentation links |
| `gate` | ubuntu-latest, 5 min cap | the one required check: green iff every job that ran was green |

The backend job sets `TEST_MODE`, `ENV=dev`, `LLM_API_KEY`, `LLM_API_BASE`, `CORS_ORIGINS`, and `PYTHONPATH` (pointing at `apps/api/src`) as job env.

The dependency audits and the secret scan are not part of `ci.yml`: they live in `.github/workflows/security.yml`, which runs on push, on pull requests, and on a weekly schedule. Its python job installs the same hash-locked backend environment (`apps/api/requirements-ci.lock`) before `pip-audit`.

## Images

### Backend api image (root `Dockerfile`, build context = repo root)

| Aspect | Value |
| --- | --- |
| Base | `python:3.14-slim` (Debian trixie) |
| Extra runtime | Node.js installed via apt (trixie ships Node 20.x) — used by the agent `code_exec` tool for JavaScript snippets |
| Install | `pip install --retries 5 --timeout 120 --index-url "$PIP_INDEX_URL" ./apps/api` (`ARG PIP_INDEX_URL` provides an optional mirror for weak networks; the retries/timeout guard large wheels like opencv) — runtime install without the `dev` extra |
| Runtime user | `root` — the agent sandbox drops snippets to an unprivileged user via `setpriv` / `runuser`, which requires root |
| Port / entry | 8081; `uvicorn realmock.asgi:app --host 0.0.0.0 --port 8081` |
| Runtime data | DB / Chroma / uploads live under `/app/apps/api/src/realmock/platform/data` inside the container — mount a volume there at runtime |

Besides the Node.js row above, the Dockerfile installs no other extra apt packages on purpose: the agent sandbox shells out to `setpriv` / `runuser` / `unshare` (shipped by trixie's essential util-linux package) and `nobody` (from base-passwd). Full sandbox enforcement additionally needs runtime privileges the image cannot grant itself (e.g. `docker run --cap-add SYS_ADMIN` plus a writable `/sys/fs/cgroup`); without them snippets still run and every unenforced control is reported back as an explicit isolation note.

### Web image (`apps/web/Dockerfile`, build context = `apps/web`)

| Aspect | Value |
| --- | --- |
| Base / stages | `node:24-slim`; multi-stage `deps` → `builder` → `runner` |
| Build args | `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_WS_URL`, `NEXT_PUBLIC_STREAM_API_BASE` — injected at build time; defaults (`http://localhost:8081`, `ws://localhost:8081`) match a single-host deploy; `env.ts` requires all three in production |
| Runtime user | `node` (the official image user); the runner-stage `COPY` is chowned so runtime cache writes keep working |
| Port / entry | 8080; `npm start -- -p 8080` with `NODE_ENV=production` |
