# capabilities/ai/

AI capability layer shared by all agent-driven domains: LLM provider calls, the generic agent loop, and context-window management.

## [`llm/`](llm/README.md) — provider-facing model calls

`unified_client.py` is the entry point over the protocol stack in `client/` (OpenAI chat / Responses and Anthropic protocol translation, streaming with retry, request/response assembly, provider config loaded from DB via `from_db.py`). Around it: stream post-processing (`stream_filters.py`, `stream_sanitizer.py`, `special_token_filter.py`), say-first speculative streaming (`say_first_stream.py`), output parsing (`json_extract.py`, `inline_tool_call.py`, `tool_args.py`), and usage / defaults / provider-error mapping (`usage.py`, `defaults.py`, `provider_errors.py`).

## [`agent/`](agent/README.md) — generic think-then-act loop

`loop.py` drives rounds (`llm_round.py`) with an event contract (`events.py`), hints, halt conditions (`halt.py`), and `working_memory.py`. `tools/` holds the shared tool set: spec + executor (`spec.py`, `executor.py`), `github.py`, `search.py`, `fetch.py`, `profile.py`, `resume.py`, `codeexec.py`, with execution isolation backends in `tools/isolation/` (process / linux_job).

## `context/` — context window management

`manager.py` (entry), `estimation.py` (token estimation), `compress.py` / `summarize.py` (compaction), `blobs.py` (payload blobs), `options.py` (configuration).
