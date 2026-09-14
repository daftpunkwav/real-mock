# tests/

Backend test suite. Layout mirrors the source tree: one directory per domain, plus platform and cross-cutting suites. Run with `cd apps/api && pytest` (`testpaths = tests`).

## Domain suites

| Directory | Covers |
| --- | --- |
| `profile/` | Profile domain |
| `resume/` | Resume domain (parsing, review pipeline, contracts) |
| `settings/` | Settings domain |
| `prep/` | Prep domain (agent stream, tools, memories, compaction) |
| `interview/` | Interview domain (flow, follow-up, verdicts) |
| `records/` | Records domain (report agent) |
| `growth/` | Growth domain |

## Platform and cross-cutting suites

| Directory | Covers |
| --- | --- |
| `platform_core/` | Platform kernel (core utilities, config, database) |
| `platform_ai/` | AI capabilities (LLM, agent context, compression) |
| `sessions/` | Session-level integration: auth, rate limit, SSRF pin, WS mutex, streaming |
| `voice/` | Voice capabilities (voice config, resolve, TTS) |
| `architecture/` | Architecture guard tests: platform must not import domains, domains must not import each other, DB boundary, API path conventions |
| `smoke/` | Aggregate boot smoke across platform and domain services |

## Shared fixtures

| File | Purpose |
| --- | --- |
| `conftest.py` | Shared pytest fixtures |
| `fakes.py` | Shared test doubles |
