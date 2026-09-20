# records/agents/report/

Two-stage ReAct pipeline that produces the deep interview report from a frozen session ledger. Parent map: [../../..](../../../README.md) (records domain).

## Pipeline

| Module | Purpose |
| --- | --- |
| `agent.py` | `DeepReportAgent` orchestration: batch splitting (`TURNS_PER_BATCH`), bounded parallel stage 1 (`MAX_PARALLEL_BATCHES`), overall `REPORT_TIME_BUDGET_SECONDS`, context specs |
| `turn_notes_agent.py` | Stage 1: one ReAct loop per batch of dialogue rounds; each loop reads, thinks, verifies, and emits one deep note per turn; missing coverage triggers a retry path |
| `synthesis_agent.py` | Stage 2: one ReAct loop reading accumulated notes through a paged tool, spot-checking the ledger where notes look unsupported, then writing the verdict, score breakdown, highlights / key problems, and training plan |

## Supporting modules

| Module | Purpose |
| --- | --- |
| `ledger_tools.py` | Progressive disclosure over the frozen transcript: `ledger_overview` / `ledger_read_turns` / `ledger_search` pull bounded pages; a batch run scopes reads to its own turn range — the transcript is never dumped into one prompt |
| `prompts.py` | System prompts and JSON contracts for both stages |
| `finalize.py` | JSON extraction with grounded repair for agent output; a bounded LLM repair pass is the last resort before failure |
| `normalize.py` | Tolerant normalization into schema types (aliases, clamps, list caps) so one drifted field never invalidates a whole report |

Tests: `apps/api/tests/records/`.
