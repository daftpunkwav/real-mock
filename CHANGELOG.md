# Changelog

User-visible changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versioning follows Semantic Versioning (SemVer).

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
