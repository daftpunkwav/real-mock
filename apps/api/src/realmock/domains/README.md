# domains/

Business domains. Seven independent modules, each mounted by `platform/router_mount.py`.

| Domain | Purpose |
| --- | --- |
| `profile/` | Candidate profile (single-tenant; PUT full-replace semantics) |
| `resume/` | Resume upload, parsing, deep review, paginated preview |
| `settings/` | Provider / model / stage settings and integrations (GitHub link, model tests) |
| `prep/` | Prep interview coach: agent chat with tools, memory compaction, usage accounting |
| `interview/` | Realistic interview room: realtime WebSocket, multi-round flow, verdicts |
| `records/` | Interview history and reports |
| `growth/` | Growth statistics |

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

Thin domains (`profile/`, `settings/`) skip layers they don't need. `interview/` additionally carries `realtime/` (WebSocket runtime, see [interview/realtime/README.md](interview/realtime/README.md)) and `ledger/`.
