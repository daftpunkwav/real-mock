# RealMock Architecture

The backend is a modular monolith: one FastAPI process, packaged as `realmock` (src layout) under `apps/api/` and assembled in `src/realmock/asgi.py`.

## Layers

| Package | Owns | May depend on |
| --- | --- | --- |
| `platform/` | Platform kernel: cross-domain infrastructure (AI / voice capabilities, DB, config, contracts, shared services) | `platform` only |
| `domains/` | The seven business domains | `platform` + own package; never another domain |
| `bootstrap/` | Composition root: database wiring (`db_bootstrap.py`) and the session ORM (`sessions_orm.py`) | `platform` + `domains` |

`bootstrap/` sits outside `platform/` because it imports domain packages to register their ORM models before table creation; a platform-to-domain import is an architecture violation (guarded by `tests/architecture/test_platform_no_domain_imports.py`).

## Domains

| Domain | Purpose |
| --- | --- |
| `profile/` | Candidate profile (single-tenant; PUT full-replace semantics) |
| `resume/` | Resume upload, parsing, deep review, paginated preview |
| `settings/` | Provider / model / stage settings and integrations (GitHub link, model tests) |
| `prep/` | Prep interview coach: agent chat with tools, memory compaction, usage accounting |
| `interview/` | Realistic interview room: realtime WebSocket, multi-round flow, verdicts |
| `records/` | Interview history and reports |
| `growth/` | Growth statistics |

Each domain exports a `service_router` (`domains/<name>/router.py`) and owns its own path prefix (for example `/profile`, `/resume`, `/settings`, `/prep`, `/interview`, `/options`, `/records`, `/reports`, `/growth`).

## Dependency rules and guards

Dependency direction: `bootstrap/` -> `domains/` -> `platform/`; cross-domain collaboration goes through platform services and contracts. The rules are enforced by the test suite in `apps/api/tests/architecture/`:

| Test | Guard |
| --- | --- |
| `test_platform_no_domain_imports.py` | AST guard: `platform` must not import `realmock.domains` or `realmock.bootstrap` |
| `test_domains_no_cross_imports.py` | AST guard: domains must not import sibling domains |
| `test_db_boundary_imports.py` | Interview / agent domains must not import shared-table (api.db) ORM models directly |
| `test_bootstrap_session_domains.py` | Standalone processes must not load unrelated business ORMs |
| `test_interview_layering.py` | AST guards for the interview domain layering |
| `test_api_v1_paths.py` | `/api/v1` and the `/api` compatibility alias both exist |
| `test_app_factory.py` | Entry-point and middleware behavior of `app_factory` / `asgi` |
| `test_exposure_guards.py` | Deployment-exposure guard regressions |
| `test_openapi_contract_sync.py` | The committed `openapi.json` matches the live app schema |

## Domain anatomy

Domains share a common layering; a domain carries only the layers it needs:

| Layer | Purpose |
| --- | --- |
| `router.py` | Assembles and exports the domain `service_router` |
| `routes/` | HTTP / WS endpoints (thin: parse, delegate, serialize) |
| `services/` | Business logic |
| `agents/` | LLM agents (agent-driven domains) |
| `schemas/` | Request / response pydantic models |
| `models/` | Domain ORM models (domains that own sessions.db tables) |
| `main.py` / `startup.py` | Domain lifecycle hooks (where needed) |
| `column_migrations.py` | Lightweight column-level migrations for domain tables |

`interview/` additionally carries `realtime/` (WebSocket runtime), `process/` (multi-round orchestration and round digests), `protocols/` (plan / round-plan schemas, round chains, process memory), `capabilities/` (RAG, coding sandbox, vision), `ledger/` (append / freeze session ledger) and the domain-root `workflows.py` (phase / workflow definitions, locked against the frontend `apps/web/src/config/phases.ts` by tests).

## Process assembly

`asgi.py` builds the aggregate app:

| Step | Module | Purpose |
| --- | --- | --- |
| 1 | `asgi.create_app()` | Logging, settings, `FastAPI(title="RealMock API")` |
| 2 | `platform/app_factory.py` | `install_trace_middleware`, `add_default_cors`, `register_core_error_handlers`; CORS and secret-key policy checks run in `asgi.py` |
| 3 | `platform/router_mount.py` | `include_with_legacy_api_alias` mounts the seven domain routers under `/api/v1` and registers a legacy `/api` alias |
| 4 | lifespan | `bootstrap/db_bootstrap.py`: `bootstrap_databases_and_seed()` (table creation, migrations, seed) and platform contract wiring; then `domains/interview/startup.py: ensure_rag_index()` |

`platform/app_factory.py` also provides `create_service_app()`, used by the standalone domain entry points `domains/prep/main.py` and `domains/interview/main.py` (CORS, `/health`, `/api/v1` prefix, error handlers, trace middleware). The aggregate entry has its own assembly and does not reuse this factory.

## Frontend

`apps/web/` is the Next.js + React frontend (dev server on port 8080). See [apps/web/README.md](../apps/web/README.md).
