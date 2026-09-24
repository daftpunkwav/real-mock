# prep/agents/tools/

The prep agent's tool surface: declaration, registry assembly, and five tool families. Parent map: [../README.md](../README.md); the generic loop and `ToolSpec` primitive live in `platform/capabilities/ai/agent/tools/`.

## Assembly

| Module | Purpose |
| --- | --- |
| `spec.py` | The single `ToolSpec` shape (function-calling schema + handler), loading tiers, and the per-tool default timeout; leaf tool modules depend only on this file (plus `platform/services`) — no handler logic here |
| `registry.py` | The only place that knows the full toolset: concatenates the family `SPECS` lists once into `TOOL_REGISTRY` / `SECONDARY_TOOLS` / `DOMAIN_TOOL_DEFINITIONS`, applies the central per-tool timeout table, and injects the model-overridable `timeout_seconds` argument into every schema. No leaf module imports it at import time |

## Families

| Directory | Tools | Notes |
| --- | --- | --- |
| `basic/` | `code_exec` (sandboxed snippet verification), `company_info` (target-company interview style), `quiz` (practice question), `take_note` (persist turn conclusions to working memory), `web_search`, `web_fetch` (read one page's full text) | Core per-turn capabilities; `web_fetch` loads on demand |
| `candidate/` | `profile`, `resume` + `shared.py` | Candidate-data inspection with live ORM binding per call, never cached across calls |
| `memory/` | `write` (durable, idempotent), `list_summaries`, `list_tags`, `get_detail` | Long-term memory access; the index queries are declared every turn, only the full-text detail read loads on demand |
| `repo/` | `github.py` | Six tools behind one factory over platform GitHub specs plus a repo-talk tool; loaded on demand |
| `system/` | `availability` (turn-start name-gated static subset policy), `compact` (agent-invoked compaction; declared but intentionally not loaded), `search_tools` (on-demand discovery over the secondary catalog, loads schemas mid-turn lazily) | Meta-tools governing the toolset itself |

Tests: `apps/api/tests/prep/`.
