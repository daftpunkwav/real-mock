# domains/

Business domains. Seven independent modules, each mounted by `platform/router_mount.py`.

| Domain | Purpose |
| --- | --- |
| [`profile/`](profile/README.md) | Candidate profile (single-tenant; PUT full-replace semantics) |
| [`resume/`](resume/README.md) | Resume upload, parsing, deep review, paginated preview |
| [`settings/`](settings/README.md) | Provider / model / stage settings and integrations (GitHub link, model tests) |
| [`prep/`](prep/README.md) | Prep interview coach: agent chat with tools, memory compaction, usage accounting |
| [`interview/`](interview/README.md) | Realistic interview room: realtime WebSocket, multi-round flow, verdicts |
| [`records/`](records/README.md) | Interview history and reports |
| [`growth/`](growth/README.md) | Growth statistics |

## Shared anatomy

Domains share a common layering; a domain only carries the layers it needs:

| Layer | Purpose |
| --- | --- |
| `router.py` | Assembles and exports the domain APIRouter |
| `routes/` | HTTP / WS endpoints (thin: parse, delegate, serialize) |
| `services/` | Business logic |
| `agents/` | LLM agents (agent-driven domains) |
| `schemas/` | Request / response pydantic models |
| `models/` | Domain ORM models (domains that own tables) |
| `main.py` / `startup.py` | Domain lifecycle hooks (where needed) |
| `column_migrations.py` | Lightweight column-level migrations for domain tables |

Thin domains (`profile/`, `settings/`) skip layers they don't need. `interview/` is the largest domain and additionally carries `realtime/` (WebSocket runtime, see [interview/realtime/README.md](interview/realtime/README.md)), `process/` (multi-round process orchestration and per-round digests), `protocols/` (plan / round-plan schemas, round chains, process memory), `capabilities/` (RAG, coding sandbox, vision), `ledger/` (append / freeze session ledger) and the domain-root `workflows.py` (phase / workflow SSOT, locked against the frontend `config/phases.ts` by tests).
