# Agent System

The platform-level agent machinery lives in `apps/api/src/realmock/platform/capabilities/ai/`: the generic think-then-act loop (`agent/`), context-window management (`context/`), and the LLM provider layer (`llm/`). Domain packages instantiate it: [prep agents](../apps/api/src/realmock/domains/prep/agents/README.md) and [interview agents](../apps/api/src/realmock/domains/interview/agents/README.md).

## `agent/` — think-then-act loop

| Module | Purpose |
| --- | --- |
| `loop.py` | `run_agent_loop()` drives tool rounds until the model stops requesting tools or `max_rounds` is reached; result is a `LoopResult` (`messages`, `final_content`, `tool_used`, `halted`, `thinking`). Body text without `tool_calls` is the final answer and ends the loop. Multiple tool calls in one round execute in parallel (`asyncio.gather`); calls beyond `max_tools_per_round` (default 8) stay declared in the assistant message and receive an explicit "not executed" observation. The last round injects a wrap-up hint; the loop ends on `AgentHalt`; `ApiBusinessError` propagates to the caller. |
| `llm_round.py` | `_call_llm_round()` — one model call per round, preferring streaming `chat_message_stream` (reasoning deltas delivered in real time) and falling back to non-streaming `chat_message` when the client lacks streaming or the protocol rejects it. Also holds `_truncate_tool_result`, capped at `TOOL_OBSERVATION_SOFT_CHARS` (12,000). |
| `events.py` | Progress-event contract: `AgentEvent` (a dict), `OnAgentEvent` accepting sync or async callbacks, and `emit_agent_event()`, which awaits the callback and logs (never raises) callback failures. |
| `halt.py` | `AgentHalt` — the exception a tool raises to end the loop (its message becomes the tool observation). |
| `hints.py` | Wrap-up hint (`_WRAP_UP_HINT`) and drift-correction hint (`_DRIFT_HINT`): a short toolless narration before any tool use triggers one corrective retry. |
| `working_memory.py` | `WorkingMemory` — structured facts kept in model-visible context after compression, marked with `MEMORY_MARKER` (`[Working memory]`). |

## `agent/tools/` — shared tool set

| Module | Purpose |
| --- | --- |
| `spec.py` | `ToolSpec` (OpenAI function schema + async handler) and `ToolBundle`, the ordered registry/dispatcher used by agent loops. |
| `executor.py` | `invoke_with_timeout()` — single-call timeout + error classification; timeouts and unexpected exceptions return as JSON observations (`"timeout"` / `"tool_failed"`), `ApiBusinessError` raises. |
| `github.py` | Wraps `capabilities/integrations/github/tools` (`GITHUB_TOOL_DEFINITIONS`, `execute_github_tool`) so domains share one schema + execute path. |
| `search.py` | Public-web search tool; result count bounded by `SEARCH_DEFAULT_MAX_RESULTS` (8) / `SEARCH_HARD_MAX_RESULTS` (12). |
| `fetch.py` | Public-web page fetch with SSRF mitigation (see [security.md](security.md)); redirects followed hop-by-hop (max 5 hops), output hard-capped (6,000 / 12,000 chars). |
| `profile.py` | Hierarchical user-profile tools: `profile_list_sections` / `profile_get_section` over five sections (`basics`, `education`, `career`, `skills`, `links`). |
| `resume.py` | Progressive-disclosure resume tools: `resume_overview` / `resume_get_section` (sections incl. paged raw excerpt). |
| `codeexec.py` | Sandboxed Python / JavaScript snippet runner; isolation backend picked per call by `run_code_snippet(..., isolation=...)`, `"auto"` by default. |

### `tools/isolation/` — execution isolation backends

Both backends implement the `IsolationBackend` protocol in `base.py` (`spawn` / `describe`), returning a `CompletedSnippet` (`exit_code`, `stdout`, `stderr`, `timed_out`, `notes`). Backends never raise for snippet behavior; exit codes and timeouts are data. `base.run_child()` kills the whole process tree on timeout (`terminate_tree`, POSIX process group via `killpg`).

| Backend | Enforced controls |
| --- | --- |
| `process.py` (`ProcessIsolation`) | Wall-clock timeout, private temp working directory, scrubbed environment. No user switch, no network block, no cgroup caps. Default on Windows, dev machines, and non-root processes. |
| `linux_job.py` (`LinuxJobIsolation`) | Linux only. Drops to an unprivileged account (default `nobody`, via `setpriv` / `runuser`), fresh network namespace (`unshare -n`, loopback stays down), cgroup v2 `memory.max` (default 256 MiB) and `cpu.max` (default `50000 100000` — half a CPU) under `/sys/fs/cgroup/realmock-codeexec`, best-effort read-only remount of `/` inside a private mount namespace. Launch strategy is picked by probing OS helpers, in preference order: `contained` > `userns-mapped` > `userns-netonly` > `netonly` > `plain`. Every control that cannot be enforced becomes an explicit `<control>=unavailable` entry in `notes` — never a silent downgrade. Tunables via `CODEEXEC_*` environment variables. |

## `context/` — context window management

| Module | Purpose |
| --- | --- |
| `manager.py` | Entry point; `prepare_llm_context` orchestration (compression + working-memory injection as a separate system section). |
| `estimation.py` | Script-aware token estimation for budget checks (CJK ≈ 1.5 chars/token, Latin ≈ 4); image data URLs budgeted at 32 chars/token with `VISION_CONTEXT_IMAGE_RATIO` (0.35) of the window reserved. |
| `compress.py` | Rule-based `compress_messages` (system messages + latest tail + summary line) and collapsing of stale tool-call pairs; products marked `[Conversation Minutes]` / `[Context compression]`. |
| `summarize.py` | `compact_with_summary` — above threshold, LLM-generated sectioned summary replaces the omitted conversation incrementally; LLM failure falls back to the rule-based summary (logged, visible) unless `force=True`. |
| `blobs.py` | LLM compression for oversized text blobs; on failure returns an explicitly marked head+tail excerpt. |
| `options.py` | `CompactionOptions` value object; intensity levels `light` / `balanced` / `aggressive` with verbatim-tail floors of 10 / 4 / 0 messages. |

## `llm/` — provider-facing model calls

`unified_client.py` (package root) is a backward-compatible wrapper; the implementation is the protocol stack in `client/`:

| Module | Purpose |
| --- | --- |
| `client/unified_client.py` | `UnifiedLLMClient` — selects the API path by protocol: OpenAI chat completions / Anthropic messages / OpenAI Responses. Holds client state, SSRF checks, URL + payload construction, streaming orchestration; provider config loaded from DB via `from_db.py`. |
| `client/llm_client.py` | Client methods including `chat_message_stream` (streaming tool rounds). |
| `client/retry_stream.py` | OpenAI-compatible streaming execution: retries 429 / 5xx / connection errors with exponential backoff before any delta is emitted (3 attempts); 4xx is not retried (a rejected `stream_options` field is removed and the request replayed); failure after the first delta raises. |
| `protocol_translate.py` / `response_extract.py` / `assemblers.py` / `chat_endpoints.py` / `streaming.py` | Request-body construction, response parsing, incremental stream assemblers, non-streaming endpoints, streaming execution. |

Stream post-processing (`stream_filters.py` entry): `special_token_filter.py` strips training-template tokens (`<|X|>` / `<]X[>`) stream-safely across chunk boundaries; `inline_tool_call.py` cleans inline `<tool_call>` XML degraded from function calling; `StreamSanitizer` orchestrates both and wraps reasoning deltas in `<think>...</think>`. `say_first_stream.py` parses `{"say": "...", ...}` output incrementally from the stream — the first spoken sentence is emitted as soon as its sentence-ending punctuation arrives; degradation (missing `say` key, JSON parse failure) falls back to plain text.

## Model capability declarations

`domains/settings/services/model_registry.py` is the capability-based declaration system over four DB tables (`platform/models/config_models.py`):

| Table | Content |
| --- | --- |
| `LlmProvider` | Provider entry (name, enabled, website, notes). |
| `LlmProviderChannel` | Per-kind connection settings; kinds `chat` / `stt` / `tts` (`CHANNEL_KINDS`). |
| `ModelProfile` | One model entry: context window, max output, capability flags `cap_chat` / `cap_vision` / `cap_audio_in` / `cap_audio_out` / `cap_reasoning`, plus `extras` convention keys `reasoning` (variants, defaultVariant) and `modalities` (input / output). |
| `TaskBinding` | Binds each task (`chat` / `stt` / `tts`) to a model profile with a fallback handler; binding an entry whose capability flag does not cover the task is rejected. |

HTTP surface: `domains/settings/routes/models.py` and `domains/settings/routes/model_tests.py`.

## Domain-level instances

- **Prep agents** — [`domains/prep/agents/`](../apps/api/src/realmock/domains/prep/agents/README.md): turn orchestration (`chat.py`, `agent.py`), per-turn toolset policy (`turn_tools.py`), tool execution callback with `ask_user` dispatch (`tool_exec.py`; the `ask_user` tool emits an `ask_user` event and raises `AgentHalt`), mid-turn compaction (`round_compaction.py`, `MidTurnCompaction`), speculative streaming (`streaming.py`), persistence (`persist.py`); subpackages `context/`, `ask_user/`, `tools/` (families `basic/`, `candidate/`, `memory/`, `repo/`, `system/`).
- **Interview agents** — [`domains/interview/agents/`](../apps/api/src/realmock/domains/interview/agents/README.md): one subpackage per role (`interviewer/`, `topology/`, `hint/`, `planning/`, `research/`, `memory/`), shared kernel flat at the package root. The package `__init__` is the facade: `realtime` / `routes` / `process` depend only on it plus the leaf contracts `agents.events` and `agents.agent_text`. `say_first.py` parses the say-first protocol for interview turns.
