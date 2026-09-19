# prep/

Prep interview coach domain: agent-driven chat with tools, long-term memories, usage accounting.

| Layer | Contents |
| --- | --- |
| `routes/` | `chat.py`, `create.py`, `history.py`, `lists.py`, `manage.py`, `memories.py` |
| [`agents/`](agents/README.md) | Agent loop and tool machinery: `tools/` (registry + `basic/` `candidate/` `memory/` `repo/` `system/`), `context/` (seed / working / linked / hints / markers), `ask_user/`, streaming, turn state, round compaction, quiz rendering, persistence |
| `services/` | `memories.py`, `linking.py` (cross-session links), `session_notes.py`, `session_stats.py` |
| `models/` | Coaching sessions and long-term memories (tables in `sessions.db`; single-user app, no owner column) |
| `main.py` / `startup.py` | Standalone assembly and lifecycle hooks |
| `column_migrations.py` | Column-level migrations for prep tables |

Tests: `apps/api/tests/prep/`.
