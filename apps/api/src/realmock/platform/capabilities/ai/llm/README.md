# capabilities/ai/llm/

Provider-facing LLM calls: one protocol stack with three wire protocols (OpenAI chat completions, Anthropic messages, OpenAI responses), plus stream post-processing and output parsing shared by every domain. Parent map: [../README.md](../README.md).

## `client/` — protocol stack

| Module | Purpose |
| --- | --- |
| `unified_client.py` | `UnifiedLLMClient` entry point over the three protocols; delegates body building / parsing / streaming / endpoints to the modules below |
| `protocol_translate.py` | Request-body construction per protocol; protocol-specific message/tool conversion delegated to `anthropic_converters.py` / `responses_converters.py` (shared pure helpers in `protocol_utils.py`) |
| `response_extract.py` | Response parsing (body / tool calls / reasoning / finish reasons / business errors / citations / server-tool items) and per-event SSE parsing; pure functions, no network |
| `streaming.py` | Streaming transport shared by both clients: SSE parsing, usage collection, `stream_options` downgrade signal; retries on the shared ladder until the first delta, terminal provider errors raise `LLMUpstreamError` |
| `assemblers.py` | Streaming tool-round assemblers (openai_chat / anthropic / openai_responses): reasoning deltas immediate, content deltas queued for speculative streaming, tool calls buffered to stream end; terminal state captured (finish reason, provider error events, signed thinking blocks, refusal/search-item surfacing) |
| `chat_endpoints.py` | Non-streaming endpoints (`chat` / `test_connection` / `chat_message`) on the shared pinned-client path; business-level provider failures (HTTP-success bodies) raise `LLMUpstreamError` |
| `retry_stream.py` | Streaming retries: 429/5xx/connection errors on the shared ladder before the first delta; no 4xx retries; `stream_options` fallback replay |
| `json_response.py` | JSON output parsing for `chat_json`: think/code-fence stripping, bounded tolerant retries; failures stay visible, never fake JSON |
| `llm_client.py` | `LLMClient`, the OpenAI-compatible BYOK client; per-request SSRF validation of `api_base`, DB-stored keys auto-decrypted |
| `openai_transport.py` | `LLMClient` chat-protocol execution, JSON-output parse repair, embeddings calls |
| `llm_client_ext.py` | `LLMClient` outbound probes (`test_connection`) and `embed` |
| `from_db.py` | Client assembly from model profiles (capability-declared task bindings); custom reasoning variants (`extras.reasoning.variants`) ride through verbatim; no silent fallback when a scenario names a profile explicitly |

## Around the stack

| Module | Purpose |
| --- | --- |
| `stream_filters.py` | Public stream-sanitization entry point |
| `stream_sanitizer.py` | Dual-channel (reasoning/content) sanitization orchestration |
| `special_token_filter.py` | Streaming-safe stripping of training-template tokens (`<|X|>` / `<]X[>` forms) |
| `inline_tool_call.py` | Removes XML `<tool_call>` blocks that leaked into body text (protocol drift); preserves valid `<question>` content |
| `say_first_stream.py` | Say-first structured streaming: `{"say": ...}` first key streams to the voice/subtitle channel; remaining keys parse as control fields at stream end |
| `json_extract.py` | Recovers JSON objects from noisy output: string-aware balanced-brace scan, keeps the key-richest candidate |
| `usage.py` | Token usage extraction and accumulation for all three protocols, plus per-request diagnostics (upstream request id, latency, last error) |
| `retry_policy.py` | Shared retry ladder for outbound LLM calls: up to 10 retries (10/10/20/20/40/40/80/80/100/100 s), a provider `Retry-After` header wins for the immediate retry; ReadTimeout is never retried |
| `defaults.py` | Token-budget defaults; user-configured context window / max output win over these constants |
| `provider_errors.py` | Conservative provider-side context-overflow classification so callers can compact-and-retry |
| `unified_client.py`, `tool_args.py` | Backward-compatible wrappers re-exporting from `client/` |

Tests: `apps/api/tests/platform_ai/`.
