# interview/

Realistic interview room domain: realtime WebSocket conversation, multi-round processes, verdicts and reports.

| Package | Purpose |
| --- | --- |
| [`agents/`](agents/README.md) | LLM roles, one subpackage each: `interviewer/` (lead interviewer), `topology/` (shadow evaluator, coding examiner, process orchestrator), `hint/`, `planning/`, `research/`, `memory/`. The package `__init__` is the facade — `realtime` / `routes` / `process` depend only on it plus the `events` / `agent_text` leaf contracts |
| `realtime/` | WebSocket runtime (handler, stacks, turn / media / control, audio engine) — see [realtime/README.md](realtime/README.md) |
| `process/` | Multi-round process orchestration and per-round digests |
| `protocols/` | Plan / round-plan schemas, deterministic round chains, process memory documents |
| [`capabilities/`](capabilities/README.md) | Interview-specific capabilities: `rag/`, `sandbox/` (coding), `vision/` |
| `ledger/` | Append / freeze session ledger (interview is the sole writer) |
| `routes/` | `sessions.py`, `interview.py`, `turns.py`, `processes.py`, `options.py`, `brief.py`, `ws/` (WebSocket endpoint) |
| `models/` | `session.py`, `process.py`, `brief.py`, `ws_lease.py` |
| `schemas/` | Session / process / options pydantic models |
| `workflows.py` + `constants.py` | Phase / workflow SSOT (locked against the frontend `config/phases.ts` by `tests/interview/test_phase_ssot.py`) |
| `main.py` / `startup.py` / `column_migrations.py` | Lifecycle hooks and column-level migrations |

Tests: `apps/api/tests/interview/` (flow, realtime, agents, protocol schema).
