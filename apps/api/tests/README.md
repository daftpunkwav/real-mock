# tests/

Backend test suite. Layout mirrors the source tree: one directory per domain, plus platform and cross-cutting suites, plus the root-level source-layout guard. Run with `cd apps/api && pytest` (`testpaths = tests`).

## Domain suites

| Directory | Covers |
| --- | --- |
| `profile/` | Profile domain (HTTP contract, schemas, contract guard) |
| `resume/` | Resume domain (parsing, review pipeline, upload and file endpoints, contracts) |
| `settings/` | Settings domain (model registry, stage config, vendors, data wipe) |
| `prep/` | Prep domain (agent stream, tools, memories, compaction, session routes) |
| `interview/` | Interview domain (flow, planning, realtime WS, runners, ledger, prompts, tools) |
| `records/` | Records domain (report agent, synthesis, turn notes, export and history routes) |
| `growth/` | Growth domain (insight agent, learning sidecar, history index) |

## Platform and cross-cutting suites

| Directory | Covers |
| --- | --- |
| `platform_core/` | Platform kernel (core utilities, config, database, secrets and redaction, session auth, error catalog) |
| `platform_ai/` | AI capabilities (LLM transports, agent loop and tools, context compression, isolation) |
| `sessions/` | Session-level integration: auth, rate limit, SSRF pin, WS mutex, HTTP/WS interview flows, streaming |
| `voice/` | Voice capabilities (voice config, resolve, TTS, STT providers) |
| `architecture/` | Architecture guard tests: import seams (platform vs. domains, DB boundary, interview layering), composition (bootstrap ORM registration, app factory), the published REST contract (path conventions, response shapes and media types, OpenAPI sync), cross-layer contracts (ledger document, profile read model, WS error codes), exposure guards (local-only, SSRF, cross-site) |
| `smoke/` | Aggregate boot smoke across platform and domain services |

## Root-level guards

| File | Purpose |
| --- | --- |
| `test_prompt_hygiene.py` | Source-layout guard: prompt text lives in the owning prompts module, never inline in a business file |

## Shared fixtures

| File | Purpose |
| --- | --- |
| `conftest.py` | Shared pytest fixtures |
| `fakes.py` | Shared test doubles |
