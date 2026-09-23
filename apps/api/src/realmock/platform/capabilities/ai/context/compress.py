"""Rule-based compression: ``compress_messages`` and collapsing old tool pairs.

- ``_prune_stale_tool_pairs``: collapse tool-call pairs before the most recent user message
  (remove assistant.tool_calls + tool results from context; old tool observations can consume thousands of
  tokens, while their conclusions are already carried by working memory/summaries; preserve the latest round unchanged to maintain protocol pairing);
- ``compress_messages``: retain all system messages + the latest N messages + a summary line.
"""

from __future__ import annotations

from typing import Any

from realmock.platform.capabilities.ai.agent.working_memory import WorkingMemory
from realmock.platform.capabilities.ai.context.estimation import (
    _omitted_digest,
    estimate_messages_tokens,
)

# Compression product mark (system message prefix); old mark messages are replaced after new records are generated.
# Public: prep routes/agents match and rebuild these prefixes across the domain boundary.
COMPACTION_SUMMARY_MARKER = "[Conversation Minutes]"
COMPACTION_DIGEST_MARKER = "[Context compression]"


def _prune_stale_tool_pairs(rest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse tool-call pairs (assistant.tool_calls + tool results) before the latest user message.

    Preserve the latest round verbatim so tool_calls and tool results remain fully paired under
    the OpenAI protocol; for earlier rounds, retain only assistant messages with response text
    (discard the tool_calls structure).
    """
    last_user = -1
    for i, m in enumerate(rest):
        if m.get("role") == "user":
            last_user = i
    out: list[dict[str, Any]] = []
    for i, m in enumerate(rest):
        if i >= last_user:
            out.append(m)
            continue
        role = m.get("role")
        if role == "tool":
            continue
        if role == "assistant" and m.get("tool_calls"):
            if m.get("content"):
                out.append({"role": "assistant", "content": m["content"]})
            continue
        out.append(m)
    return out


def _align_split_start(rest: list[dict[str, Any]], start: int) -> int:
    """Move a fold boundary forward so the verbatim tail never opens with an
    orphan ``tool`` result.

    Tool results are contiguous after their assistant message, so walking past
    every ``tool`` message either (a) leaves the assistant with ``tool_calls``
    in the folded head together with all of its results, or (b) starts the tail
    on a fresh assistant/user turn. Without this, a boundary landing mid-pair
    sends the provider an unpaired ``tool`` message — a hard 400 every
    subsequent round, unrecoverable inside the loop.
    """
    while start < len(rest) and rest[start].get("role") == "tool":
        start += 1
    return start


def compress_messages(
    messages: list[dict[str, Any]],
    max_tokens: int,
    *,
    keep_recent: int = 20,
    threshold: float = 0.3,
    memory: WorkingMemory | None = None,
) -> list[dict[str, Any]]:
    """When over budget, compress to system messages + the latest N conversation messages.

    Strategy:
    - Always retain every ``system`` message (interview rules, follow-up guidance, etc. must not be lost).
    - First collapse old tool-call pairs, then determine whether further compression is needed using
      ``total > max_tokens * threshold`` (default threshold 0.3, so long sessions enter summarization early and avoid overflowing the context window).
    - Retain only the latest ``keep_recent`` user/assistant messages.
    - Write omitted user/assistant messages into a summary line; when ``memory`` is supplied, absorb them into working memory as well.
    """
    system = [m for m in messages if m.get("role") == "system"]
    rest = _prune_stale_tool_pairs(
        [m for m in messages if m.get("role") != "system"]
    )
    # The old tool took unconditional effect on folding (micro-compression); further compression was only performed when a threshold was exceeded
    if max_tokens > 0 and estimate_messages_tokens(system + rest) <= max_tokens * threshold:
        return system + rest

    start = _align_split_start(rest, max(0, len(rest) - keep_recent))
    trimmed = rest[start:]
    omitted = rest[:start]
    if memory is not None and omitted:
        memory.absorb_omitted(omitted)

    digest = _omitted_digest(omitted)
    summary_body = (
        f"[Context compression] The earliest {len(omitted)} messages are omitted; "
        f"the latest {len(trimmed)} are kept verbatim."
    )
    if digest:
        summary_body += "\nSummary:\n" + digest
    summary = {"role": "system", "content": summary_body}
    return system + [summary] + trimmed
