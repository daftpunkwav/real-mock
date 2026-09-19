# platform/

Platform kernel: infrastructure shared by all domains. Domains depend on this package; the reverse direction is an architecture violation (guarded by `tests/architecture/test_platform_no_domain_imports.py`).

## Packages

| Package | Purpose |
| --- | --- |
| `capabilities/` | External capability adapters: [`ai/`](capabilities/ai/README.md) (LLM providers, agent loop, context management), `integrations/github/`, `knowledge/search/`, [`voice/`](capabilities/voice/README.md) (STT / TTS / voice config) |
| `contracts/` | Cross-domain event and data contracts (interview finished, session score, report summary, session catalog, lifecycle hooks) |
| `core/` | Kernel utilities: constants, errors and handlers, logging, file locks, local-only guard, DB migration helpers, agent error log, shared prompt fragments, in-process rate limiting, secrets encryption, SSE helpers, security helpers (file / URL pin / redaction), session auth (cookies, CSRF, tokens) |
| `catalogs/` | Static reference catalogs (companies) |
| `models/` | Shared models (config models, rate-limit buckets) |
| `schemas/` | Shared pydantic schemas (candidate, pipeline, errors) |
| `services/` | Shared services (candidate read facade, DB split, resume picker, seed, pipeline) |
| `vendors/` | Vendor adapter descriptors (JSON defs) and template helpers (deep merge, placeholder substitution) |
| `data/` | Runtime data (SQLite databases, Chroma store). `stt_fixtures/` is tracked test data; everything else here is runtime-owned and untracked |
| `uploads/` | User-uploaded files at runtime (untracked) |

## Top-level modules

| Module | Purpose |
| --- | --- |
| `app_factory.py` | FastAPI app construction |
| `router_mount.py` | Domain router mounting |
| `config.py` | Configuration |
| `database.py` | Database setup |
