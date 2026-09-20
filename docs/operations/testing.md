# Testing

Backend tests live in `apps/api/tests/`, frontend tests in `apps/web/src/` beside the code they cover.

## Backend

```bash
cd apps/api && pytest
```

`testpaths = tests` is set in `apps/api/pyproject.toml`; the layout mirrors the source tree — one directory per domain, plus platform and cross-cutting suites.

### Domain suites

| Directory | Covers |
| --- | --- |
| `profile/` | Profile domain |
| `resume/` | Resume domain (parsing, review pipeline, contracts) |
| `settings/` | Settings domain |
| `prep/` | Prep domain (agent stream, tools, memories, compaction) |
| `interview/` | Interview domain (flow, follow-up, verdicts) |
| `records/` | Records domain (report agent) |
| `growth/` | Growth domain |

### Platform and cross-cutting suites

| Directory | Covers |
| --- | --- |
| `platform_core/` | Platform kernel (core utilities, config, database) |
| `platform_ai/` | AI capabilities (LLM, agent context, compression) |
| `sessions/` | Session-level integration: auth, rate limit, SSRF pin, WS mutex, streaming |
| `voice/` | Voice capabilities (voice config, resolve, TTS) |
| `architecture/` | Architecture guard tests |
| `smoke/` | Aggregate boot smoke across platform and domain services |

### Shared fixtures

| File | Purpose |
| --- | --- |
| `conftest.py` | Shared pytest fixtures |
| `fakes.py` | Shared test doubles |

### Architecture guard tests (`tests/architecture/`)

| File | Guard |
| --- | --- |
| `test_platform_no_domain_imports.py` | The platform layer must not import business domains or composition-root bootstrap code (AST guard) |
| `test_domains_no_cross_imports.py` | Domain packages must not import sibling domain packages (AST guard) |
| `test_db_boundary_imports.py` | With dual databases, the interview/agent domains must not directly import shared-table ORM models |
| `test_interview_layering.py` | AST guards for the interview domain layering (`agents` subpackages per LLM role) |
| `test_bootstrap_session_domains.py` | Bootstrap domain registration: isolated processes must not load unrelated business ORMs |
| `test_api_v1_paths.py` | Both `/api/v1` and `/api` compatibility aliases resolve (`/api/v1/options` and `/api/options`) |
| `test_app_factory.py` | `app_factory`/`asgi` entry-point and middleware behavior |
| `test_exposure_guards.py` | Deployment-exposure regressions (local-only peer check; `ENV=prod` must not honor `TEST_MODE` for non-loopback peers) |
| `test_openapi_contract_sync.py` | See contract guards below |

### Contract guards

| Test | Contract |
| --- | --- |
| `tests/interview/test_phase_ssot.py` | `workflows` PhaseDef ↔ `InterviewPhaseId` ↔ frontend `apps/web/src/config/phases.ts` |
| `tests/interview/test_ws_protocol_schema.py` | `protocol/interview_ws.schema.json` ↔ backend `WSClientEvent` / `WSServerEvent` ↔ frontend `apps/web/src/types/domains/interview_ws.ts` |
| `tests/architecture/test_openapi_contract_sync.py` | The committed root `openapi.json` matches the live `app.openapi()` schema |

### Realtime test convention

Realtime tests patch module-level symbols in the owning module (e.g. `turn.stt_finish.transcribe_utterance_result`, `voice.tts_queue.synthesize_speech`, `connection.heartbeat.verify_connection_lease`), not methods on the handler class. See the realtime README at `apps/api/src/realmock/domains/interview/realtime/README.md`.

## Frontend

| Command | Purpose |
| --- | --- |
| `npm test` | vitest, single run |
| `npm run test:watch` | vitest in watch mode |
| `npx tsc --noEmit` | TypeScript type gate |
| `npm run lint` | ESLint |

Tests live in `__tests__/` directories next to the code they cover; the current scale is 58 `*.test.ts(x)` files across `src/`.

## CI gates

Both jobs run on push to `main` and on all pull requests (`.github/workflows/ci.yml`).

| Job | Checks |
| --- | --- |
| `backend` | `ruff==0.15.20`; `mypy==2.1.0` over `src` (blocking); pytest full regression with coverage gate `--cov-fail-under=40` over `realmock.platform` and the profile / resume / settings / prep / interview domains; `pip-audit==2.10.1` with `--ignore-vuln PYSEC-2026-311` (chromadb 1.5.9 known issue, no fixed release yet) |
| `frontend` | `npm ci`; `npx tsc --noEmit`; `npm run lint`; `npm test`; `npm run build`; `npm run audit` (fails on high+ unless allowlisted in `apps/web/npm-audit-allowlist.json`) |
