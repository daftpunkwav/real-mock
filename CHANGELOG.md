# Changelog

User-visible changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versioning follows Semantic Versioning (SemVer).

## [Unreleased]

### Added

- Agent resilience: LLM calls retry on a 10-step ladder honoring provider `Retry-After`; tool calls auto-retry transient failures twice with per-tool default timeouts the model can extend per call; the circuit-breaker tally is written into every failure observation so the model sees how close a tool is to being blocked
- Agent perception: transient current-date/time anchor per request and a per-round budget line (rounds, width, calls spent); a final answer cut by the output cap resumes once seamlessly and is marked if still truncated
- Thinking levels: models can declare custom level lists (`extras.reasoning.variants`) passed verbatim to the provider, with Anthropic budgets interpolated and a default level applied when none is set; the effort selector follows the chosen model
- Prep tools: `web_fetch` reads a search hit's full text on demand; `web_search` exposes `max_results`
- Long-term memory: end-of-turn curation asks once whether the turn is worth saving (at most one write); prep settings add a memory-index injection width (0 = all memories)
- Context compaction: folded turns keep a deterministic tool-call ledger (tool, args, result digest, referenced URLs) and the summarizer reads tool observations with a larger budget
- Context panel: provider request diagnostics (request count, request id, latency, reasoning tokens, last error)

### Fixed

- Provider responses: finish reasons and business-error bodies (e.g. MiniMax `base_resp`) are no longer silently swallowed — truncated answers are continued and marked, refusal text is shown, upstream errors surface verbatim (credential-redacted) instead of a generic copy
- Streaming: retries before the first delta on all three protocols, terminal provider error events raise instead of ending silently, space-less SSE `data:` lines parse
- Anthropic tool loops with thinking enabled echo signed thinking blocks back, as the official API requires
- MiniMax chat: seeded entries request `reasoning_split` so thinking content is actually returned
- Prep UI: inline code in markdown tables no longer breaks mid-token, the thinking/tool trace uses the full bubble width, the context-ring popover is no longer clipped
- Prep context: thinking is persisted without the display-only 20k truncation

## [0.1.0] - 2026-09-21

### Added

- Resume domain: upload and parsing (including vision transcription for image-based PDFs), deep-review pipeline (content deep-read / market benchmarking / project deep-dive / final verdict), server-side paginated preview
- Prep interview coach: agent conversations (tool calls, streaming output, conversation memory compaction), job research resources
- Realistic interview room: WebSocket realtime conversation, voice capture and playback, interview history
- Model capability system: providers / channels / models declared in dedicated tables with per-model capability flags, task binding and scenario coverage
- Engineering: OpenAPI contract pipeline (`scripts/export_openapi.py` → `openapi.json` → frontend types), `scripts/dev.sh` one-command local startup

### Fixed

- Prep agent robustness: business errors pass through (no longer swallowed into empty turns), 600s whole-turn timeout, tool compaction settles within 30s, cancelled turns reclaimed correctly, disconnect awareness and bounded event queue
- Prep concurrency safety: DB access moved off the event loop, `memory_write` idempotency (dedup key + summary-level dedup) and serialized writes
- Prep context: system prompt split into stable-first seeded blocks, reply-language hint moved to a per-turn suffix, summary position fixed — improves prompt cache hit rate
- Prep usage accounting: streaming `usage` is per-turn incremental, `done`/sync responses carry the session-level triple, frontend incremental merge + server-side self-healing
- Prep composer capacity: reasoning and tool payloads counted into the "system & tools" bucket, local messages excluded, unknown server-side parts go to the system bucket instead of a constant 0%
- Prep UX: model and thinking intensity switchable while outputting (effective per send snapshot), background generations visible in the session list and individually stoppable, fork normalization and branch counter reset
- Prep context panel: server-measured seven-category breakdown (user messages / assistant replies / reasoning / tools & retrieval / system prompt / memories & summaries / other, hover for accounting notes), estimated flag when input tokens are missing, cache hit rate computed only from reported values
- Prep slash commands: /compact (compact now and write a summary) /clear (clear after confirmation) /help (local help)
- Prep # references: multi-select sessions via the # menu in the composer, chips display, injected for the current turn only (not persisted); removed the right-side linked-session card (backend link endpoint kept for compatibility)
- Markdown: code block language labels + one-click copy, Mermaid diagram rendering (falls back to code on parse failure), dark theme support
- Markdown code highlighting: prism loads 20 languages on demand, light/dark token colors, oversized code blocks degrade to plain text
- Markdown code runner: python (skulpt local subset, execLimit circuit breaker) / javascript (Blob Worker + timeout kill) / typescript (sucrase type-stripping, then Worker); other languages are copy-only; the output panel distinguishes stdout/stderr/errors and shows a truncation notice
- Mermaid UX: parse failures no longer leak a red error diagram (source view + gentle notice instead), diagram/source dual view, 50%–300% zoom + fullscreen, dark-theme palette, re-render on theme change
- Select unification: native selects across the app migrated to the custom Select (keyboard/ARIA), interview settings and Prep-related forms
- Test infra: vitest React plugin for .tsx component tests, added missing Select cleanup between cases

[0.1.0]: https://github.com/daftpunkwav/real-mock/releases/tag/v0.1.0
