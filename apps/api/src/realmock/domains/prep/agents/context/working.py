"""Working context assembly: compaction + memory inject + per-turn suffixes."""

from __future__ import annotations

import json
from typing import Any

from realmock.domains.prep.agents.context.hints import upsert_lang_hint, upsert_usage_hint
from realmock.domains.prep.agents.context.markers import (
    BREAKDOWN_ASSISTANT,
    BREAKDOWN_MEMORY,
    BREAKDOWN_ORDER,
    BREAKDOWN_OTHER,
    BREAKDOWN_SYSTEM,
    BREAKDOWN_THINKING,
    BREAKDOWN_TOOLS,
    BREAKDOWN_USER,
    LINKED_BLOCK_MARKER,
    REF_BLOCK_MARKER,
)
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.agent.working_memory import MEMORY_MARKER
from realmock.platform.capabilities.ai.context.compress import (
    COMPACTION_DIGEST_MARKER,
    COMPACTION_SUMMARY_MARKER,
)
from realmock.platform.capabilities.ai.context.estimation import estimate_tokens
from realmock.platform.capabilities.ai.context.manager import (
    compact_with_summary,
    upsert_memory_block,
)
from realmock.platform.capabilities.ai.context.options import (
    DEFAULT_AUTO_COMPACT_THRESHOLD,
    CompactionOptions,
)


def _classify_system_block(content: str) -> str:
    """Bucket one system message: memory-like markers vs plain system prompt."""
    text = content or ""
    if (
        text.startswith(MEMORY_MARKER)
        or text.startswith("[working memory]")
        or text.startswith(COMPACTION_SUMMARY_MARKER)
        or text.startswith(COMPACTION_DIGEST_MARKER)
        or text.startswith(REF_BLOCK_MARKER)
        or text.startswith(LINKED_BLOCK_MARKER)
    ):
        return BREAKDOWN_MEMORY
    return BREAKDOWN_SYSTEM


def build_context_breakdown(messages: list[dict[str, Any]]) -> dict[str, int]:
    """Measure persisted history per bucket (mechanical estimate, same ratio as budgeting).

    Buckets: user message bodies / assistant reply bodies / thinking text /
    tool calls + observations + step/search metadata / system prompt blocks /
    memory + summary + referenced-session blocks / anything else.
    """
    counts: dict[str, int] = {key: 0 for key in BREAKDOWN_ORDER}
    for m in messages or []:
        if not isinstance(m, dict):
            counts[BREAKDOWN_OTHER] += 1
            continue
        role = m.get("role")
        content = m.get("content") or ""
        if role == "user":
            counts[BREAKDOWN_USER] += estimate_tokens(str(content))
        elif role == "assistant":
            counts[BREAKDOWN_ASSISTANT] += estimate_tokens(str(content))
            thinking = m.get("thinking")
            if thinking:
                counts[BREAKDOWN_THINKING] += estimate_tokens(str(thinking))
            tool_calls = m.get("tool_calls")
            if tool_calls:
                counts[BREAKDOWN_TOOLS] += estimate_tokens(json.dumps(tool_calls, ensure_ascii=False, default=str))
            for meta_key in ("steps", "search_groups"):
                meta = m.get(meta_key)
                if meta:
                    counts[BREAKDOWN_TOOLS] += estimate_tokens(json.dumps(meta, ensure_ascii=False, default=str))
        elif role == "tool":
            counts[BREAKDOWN_TOOLS] += estimate_tokens(str(content))
        elif role == "system":
            counts[_classify_system_block(str(content))] += estimate_tokens(str(content))
        else:
            counts[BREAKDOWN_OTHER] += estimate_tokens(str(content))
    return counts


async def build_working_context(
    messages: list[dict[str, Any]],
    context_window: int,
    *,
    memory: WorkingMemory,
    llm: Any,
    reply_locale: str | None = None,
    threshold: float | None = None,
    force: bool = False,
    options: CompactionOptions | None = None,
    keep_from: int | None = None,
    provenance: dict[str, Any] | None = None,
    default_focus: str | None = None,
    report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Assemble model context: LLM summary compression + working-memory inject + lang suffix.

    Compress only at the start of each chat turn (may trigger one summary LLM
    call). Persist paths (chat.finalize) use rule-based compression to avoid save latency.
    ``threshold`` (fraction of the context window, e.g. 0.7) comes from the
    user's auto-compact setting; ``None`` keeps the agent-decided default.
    ``force`` (manual ``/compact``) always attempts an LLM summary.
    ``options`` carries intensity/directive/retain; ``keep_from`` pins the
    verbatim cutoff for mid-turn agent-invoked compaction; ``provenance``
    stamps the new summary trailer; ``default_focus`` anchors the summary
    when the run carries no explicit directive; ``report`` collects
    compaction cost (tokens/latency) without raising.
    """
    opts = options or CompactionOptions()
    compacted = await compact_with_summary(
        messages, context_window, memory=memory, llm=llm,
        # The verbatim tail follows the turn policy exactly (retain setting
        # raised by the intensity floor), floored at the latest exchange so
        # the live user message is never summarized away. The platform's
        # keep_recent=20 default must not silently override a smaller retain.
        keep_recent=max(opts.keep_window(), 2),
        threshold=DEFAULT_AUTO_COMPACT_THRESHOLD if threshold is None else threshold,
        force=force,
        options=opts,
        keep_from=keep_from,
        provenance=provenance,
        default_focus=default_focus,
        report=report,
    )
    with_memory = upsert_memory_block(compacted, memory)
    with_lang = upsert_lang_hint(with_memory, reply_locale)
    return upsert_usage_hint(with_lang, context_window)


__all__ = ["build_context_breakdown", "build_working_context"]
