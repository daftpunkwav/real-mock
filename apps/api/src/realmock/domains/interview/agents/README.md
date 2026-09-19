# interview/agents/

LLM roles for the interview domain: one subpackage per role, shared machinery flat at the package root. The package `__init__` is the **facade** — `realtime` / `routes` / `process` depend only on it plus the leaf contracts `agents.events` and `agents.agent_text`, never on sibling modules.

## Role subpackages

| Subpackage | Purpose |
| --- | --- |
| `interviewer/` | Lead interviewer: `runner.py` plus `runner_opening.py` / `runner_turn.py` / `runner_closing.py` |
| `topology/` | Shadow evaluator, coding examiner, process orchestrator |
| `hint/` | Reference-answer agent (`hint_answer.py`) |
| `planning/` | Flow-plan and round planners (`planner.py`, `round_planner.py` + their prompt modules) |
| `research/` | Company web research and setup-page brief (`company_research.py`, `company_brief.py`) |
| `memory/` | Cognitive memory graph and reflection |

## Flat kernel

Internal modules import each other by submodule path, clustered by prefix:

| Cluster | Modules |
| --- | --- |
| protocol | `events`, `agent_text`, `turn_output`, `say_first` |
| state | `session_state`, `session_overrides`, `past_records`, `history_compaction` |
| prompts | `agent_prompts`, `closing_prompts`, `prompt_assembler`, `session_prompt` |
| rounds | `tool_round_runner`, `tool_round_stream`, `tools`, `tool_guard` |
| turn | `followup`, `followup_inject`, `finish_lifecycle` |

Related turn state machine and media pipeline live in [`../realtime`](../realtime/README.md); the phase SSOT is `../workflows.py`.
