"""LLM token-budget defaults.

User-configured ``context_window`` / ``max_output`` on a model profile win.
When those values are missing or non-positive, callers must use these
constants — never scatter literals such as ``256000`` or ``64000``.

The two platform-wide fallback constants are defined in
:mod:`realmock.platform.core.constants` (lower layer) and re-exported here
for the LLM-internal call sites.
"""

from __future__ import annotations

from realmock.platform.core.constants import DEFAULT_CONTEXT_WINDOW, DEFAULT_MAX_OUTPUT_TOKENS

# Compaction summaries stay small so they do not consume the main output budget.
COMPACTION_SUMMARY_MAX_TOKENS = 800
COMPRESSION_TIMEOUT_SECONDS = 120.0
# Soft cap for a single tool observation before LLM compression is attempted.
TOOL_OBSERVATION_SOFT_CHARS = 12_000
# Target size of a compressed tool observation.
TOOL_OBSERVATION_COMPRESSED_CHARS = 4_000
# Speech stages are not the chat model; keep dedicated budgets.
SPEECH_STAGE_MAX_OUTPUT_TOKENS = 4_096
SPEECH_STAGE_CONTEXT_WINDOW = 8_192
SPEECH_STAGE_TTS_MAX_OUTPUT_TOKENS = 8_192
# Non-streaming request ceilings. Big-context requests (deep review: page
# images + accumulated evidence, max reasoning effort) legitimately need
# minutes on some providers; a read timeout below that turns every late agent
# round into a guaranteed ReadTimeout instead of a slow but real answer.
LLM_CHAT_TIMEOUT_SECONDS = 480.0
LLM_CHAT_MESSAGE_TIMEOUT_SECONDS = 300.0
LLM_TEST_CONNECTION_TIMEOUT_SECONDS = 60.0


def resolve_context_window(value: int | None) -> int:
    """Return a positive context window, falling back to the platform default."""
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        parsed = 0
    return parsed if parsed > 0 else DEFAULT_CONTEXT_WINDOW


def resolve_max_output_tokens(value: int | None) -> int:
    """Return a positive max-output budget, falling back to the platform default."""
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        parsed = 0
    return parsed if parsed > 0 else DEFAULT_MAX_OUTPUT_TOKENS


__all__ = [
    "COMPACTION_SUMMARY_MAX_TOKENS",
    "COMPRESSION_TIMEOUT_SECONDS",
    "DEFAULT_CONTEXT_WINDOW",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "LLM_CHAT_MESSAGE_TIMEOUT_SECONDS",
    "LLM_CHAT_TIMEOUT_SECONDS",
    "LLM_TEST_CONNECTION_TIMEOUT_SECONDS",
    "SPEECH_STAGE_CONTEXT_WINDOW",
    "SPEECH_STAGE_MAX_OUTPUT_TOKENS",
    "SPEECH_STAGE_TTS_MAX_OUTPUT_TOKENS",
    "TOOL_OBSERVATION_COMPRESSED_CHARS",
    "TOOL_OBSERVATION_SOFT_CHARS",
    "resolve_context_window",
    "resolve_max_output_tokens",
]
