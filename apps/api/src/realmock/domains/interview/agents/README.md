# interview/agents/

LLM roles for the interview domain: one subpackage per role, shared machinery flat at the package root. The package `__init__` is the **facade** — `realtime` / `routes` / `process` depend only on it plus the leaf contracts `agents.events` and `agents.agent_text`, never on sibling modules.

## Role subpackages

| Subpackage | Purpose |
| --- | --- |
| `interviewer/` | Lead interviewer: `runner.py` plus `runner_opening.py` / `runner_turn.py` / `runner_closing.py` |
| `topology/` | Shadow evaluator: three-stage background assessment — evaluate, recheck (only when the first pass flags `evidence_insufficient`), probe synthesis; grounding injected verbatim, no tools, 90 s budget (`agent_policies.BACKGROUND`) |
| `hint/` | Reference-answer agent (`hint_answer.py`): zero-tool grounding-only answer by default; a GitHub-signal question escalates to a github-only 2-round loop |
| `planning/` | Flow-plan and round planners (`planner.py`, `round_planner.py` + their prompt modules) |
| `research/` | Company web research, setup-page brief, and the pre-interview GitHub evidence digest (`company_research.py`, `company_brief.py`, `github_evidence.py`) |
| `memory/` | Cognitive memory graph |

## Flat kernel

Internal modules import each other by submodule path, clustered by prefix:

| Cluster | Modules |
| --- | --- |
| protocol | `events`, `agent_text`, `turn_output`, `say_first` |
| state | `session_state`, `session_overrides`, `past_records`, `history_compaction` |
| compaction | `step_compaction` (splice + orchestration), `step_compaction_state` (bookkeeping), `step_compaction_summary` (transcript→brief), `step_compaction_prompts` |
| prompts | `agent_prompts`, `closing_prompts`, `prompt_assembler`, `session_prompt` |
| policy | `agent_policies` |
| rounds | `tool_round_runner`, `tool_round_stream`, `tools`, `tool_guard` |
| turn | `followup`, `followup_inject`, `finish_lifecycle` |

Related turn state machine and media pipeline live in [`../realtime`](../realtime/README.md); the phase SSOT is `../workflows.py`.
