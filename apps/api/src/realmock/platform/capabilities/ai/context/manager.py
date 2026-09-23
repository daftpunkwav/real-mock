"""Context compression and token estimation (orchestration entry point).

Rule-based compression, LLM summary compression, and mechanical estimation are split into grouped modules in the same directory:

- ``estimation``: token estimation and plain-text/digest helpers
- ``compress``: rule-based ``compress_messages`` + tool-pair collapsing
- ``summarize``: LLM summary-style ``compact_with_summary``

This file retains the public functions and ``prepare_llm_context`` orchestration: compression + working-memory injection.
Working memory is injected as a separate system section so the model can still see structured facts after truncation.
"""

from __future__ import annotations

from typing import Any

from realmock.platform.capabilities.ai.agent.working_memory import (
    LEGACY_MEMORY_MARKER,
    MEMORY_MARKER,
    WorkingMemory,
)
from realmock.platform.capabilities.ai.context.compress import (
    COMPACTION_DIGEST_MARKER,
    COMPACTION_SUMMARY_MARKER,
    compress_messages,
)
from realmock.platform.capabilities.ai.context.estimation import (
    estimate_messages_tokens,
    estimate_tokens,
)
from realmock.platform.capabilities.ai.context.summarize import compact_with_summary

__all__ = [
    "COMPACTION_SUMMARY_MARKER",
    "COMPACTION_DIGEST_MARKER",
    "estimate_tokens",
    "estimate_messages_tokens",
    "compress_messages",
    "compact_with_summary",
    "upsert_memory_block",
    "prepare_llm_context",
]


def upsert_memory_block(
    messages: list[dict[str, Any]],
    memory: WorkingMemory | None,
) -> list[dict[str, Any]]:
    """Remove the old working memory segment and reinsert it according to the current ``WorkingMemory``."""
    out = [
        m
        for m in messages
        if not (
            m.get("role") == "system"
            and isinstance(m.get("content"), str)
            and (
                str(m.get("content")).startswith(MEMORY_MARKER)
                or str(m.get("content")).startswith(LEGACY_MEMORY_MARKER)
            )
        )
    ]
    if memory is None:
        return out
    if not memory.render() and not memory.pending_quiz:
        return out
    out.append({"role": "system", "content": memory.dump_block()})
    return out


def prepare_llm_context(
    messages: list[dict[str, Any]],
    max_tokens: int,
    *,
    memory: WorkingMemory | None = None,
    keep_recent: int = 20,
    threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """Context assembly before sending to model: compression + injection into working memory."""
    if max_tokens <= 0:
        compacted = list(messages)
    else:
        compacted = compress_messages(
            messages, max_tokens, keep_recent=keep_recent, memory=memory,
            threshold=threshold,
        )
    return upsert_memory_block(compacted, memory)
