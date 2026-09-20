# capabilities/ai/agent/

Shared agent kernel: the think-then-act loop, working memory, and the tool registry. The interviewer and prep agents both run on this package; domain-specific tools stay in their domains. Parent map: [../README.md](../README.md).

## Loop kernel

| Module | Purpose |
| --- | --- |
| `loop.py` | `run_agent_loop`: one step = one LLM call + that round's tool execution. Domain tools register an OpenAI tools schema plus an `execute` callback; no MCP, shell, or sub-agents |
| `llm_round.py` | Single-round LLM call: prefer streaming with non-streaming fallback, truncate oversized tool results |
| `events.py` | Progress-event contract (`AgentEvent`, `OnAgentEvent`); emission is guarded so a UI callback failure never breaks the loop |
| `halt.py` | `AgentHalt`: a tool requests immediate loop termination (for example `ask_user` waiting for input) |
| `hints.py` | Cycle-budget awareness: closing nudge injected only in the final round so the model wraps up instead of being truncated |
| `working_memory.py` | Structured facts kept in model-visible context across compaction — session memory separate from the verbatim transcript |

## `tools/` — composable tool registry

| Module | Purpose |
| --- | --- |
| `spec.py` | `ToolSpec` (JSON schema + async execute) and `ToolBundle`, the runtime dispatcher; domains assemble toolsets without importing each other |
| `executor.py` | Timeout + error-classification wrapper for one tool call; canonical outcome contract `(raw, status)` with `done` / `error` |
| `codeexec.py` | Sandboxed snippet runner for agent self-verification; execution isolation lives in [`tools/isolation/`](tools/isolation/) (`process.py` default, `linux_job.py` on Linux) |
| `fetch.py` | Outbound web fetch through the SSRF-checked pinned client |
| `search.py` | Web search tool |
| `github.py` | GitHub lookups via `platform/capabilities/integrations/github/` |
| `profile.py` / `resume.py` | Candidate context tools: hierarchical section inspection over a caller-supplied profile/resume payload |

Tests: `apps/api/tests/platform_ai/`.
