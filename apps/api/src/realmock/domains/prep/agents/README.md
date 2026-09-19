# prep/agents/

Prep agent machinery: the think-then-act loop and everything a prep turn touches.

| Module | Purpose |
| --- | --- |
| `chat.py` | Turn orchestration: synchronous single turn and event-stream answers |
| `agent.py` | The prep agent itself (function-calling think-then-act loop) |
| `turn_tools.py` | Per-turn toolset policy |
| `tool_exec.py` | Tool execution callback: ask_user dispatch, identical-argument short-circuit |
| `turn_state.py` | Per-turn mutable state |
| `round_compaction.py` | Mid-turn context compaction |
| `streaming.py` | Speculative content tokens, tool-round event queue, early-body emission |
| `persist.py` | Turn persistence: compaction events, message finalization, usage deltas |
| `quiz_render.py` | Inline-quiz rendering of tool-call drift |

| Subpackage | Purpose |
| --- | --- |
| `context/` | Context assembly: `seed.py` (stable-first seed blocks), `working.py`, `linked.py` (#-referenced sessions), `hints.py`, `markers.py` |
| `ask_user/` | User-prompt control flow: `dispatch.py`, `inline.py`, `normalize.py`, `schema.py` |
| `tools/` | Tool registry (`registry.py`, `spec.py`) and five families: `basic/` (code_exec, company_info, quiz, take_note, web_search), `candidate/` (profile, resume, shared), `memory/` (write, list_summaries, get_detail, list_tags), `repo/` (github), `system/` (availability, compact, search_tools) |
