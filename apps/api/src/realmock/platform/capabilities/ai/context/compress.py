"""Rule-based compression: ``compress_messages`` and collapsing old tool pairs.

- ``_prune_stale_tool_pairs``: collapse tool-call pairs before the most recent user message
  (remove assistant.tool_calls + tool results from context; old tool observations can consume thousands of
  tokens, while their conclusions are already carried by working memory/summaries; preserve the latest round unchanged to maintain protocol pairing);
- ``_fold_protected_run``: bound the aggregate size of the tool rows a protected pair keeps;
- ``compress_messages``: retain all system messages + the latest N messages + a summary line.
"""

from __future__ import annotations

from typing import Any

from realmock.platform.capabilities.ai.agent.working_memory import WorkingMemory
from realmock.platform.capabilities.ai.context.estimation import (
    _omitted_digest,
    estimate_messages_tokens,
    estimate_tokens,
)
from realmock.platform.capabilities.ai.llm.json_extract import truncate_chunk

# Compression product mark (system message prefix); old mark messages are replaced after new records are generated.
# Public: prep routes/agents match and rebuild these prefixes across the domain boundary.
COMPACTION_SUMMARY_MARKER = "[Conversation Minutes]"
COMPACTION_DIGEST_MARKER = "[Context compression]"

#: Share of the context window one protected tool run may occupy. A
#: ``keep_tool_pair`` run stays verbatim so its open call remains paired, which
#: makes this the only ceiling that reaches it: while it is over budget, folds
#: elsewhere cannot bring the request back inside the window.
PROTECTED_RUN_TOKEN_RATIO = 0.1
#: Floor for the derived ceiling, so a small window does not squeeze the run
#: down to an excerpt that carries no signal.
PROTECTED_RUN_MIN_TOKENS = 500
#: Preferred floor for one protected tool row. If the aggregate cannot fit at
#: this floor, shrink further while keeping every result and marking each cut.
PROTECTED_ROW_MIN_CHARS = 2_000


def protected_run_budget(max_tokens: int) -> int:
    """Token ceiling for one protected tool run; 0 when the window is unknown."""
    if max_tokens <= 0:
        return 0
    return max(PROTECTED_RUN_MIN_TOKENS, int(max_tokens * PROTECTED_RUN_TOKEN_RATIO))


def _fold_protected_run(out: list[dict[str, Any]], positions: list[int], budget: int) -> None:
    """Fold the largest tool rows of a protected run until the run fits ``budget``.

    A ``keep_tool_pair`` assistant keeps every directly following tool result
    verbatim, so a dialog that ran in parallel with other tools drags those
    sibling results into the run. Each one is individually bounded upstream, but
    nothing bounded their aggregate — the sum is what overflows the window.

    Folding is largest-first, so the small rows of the run (a dialog's own
    pointer result among them) survive untouched, and head+tail behind an
    explicit marker, so no cut is silent. The assistant declaration is never
    touched. Rows are replaced rather than mutated: ``out`` shares dicts with
    the caller's live session history.
    """
    rows = {
        position: out[position]
        for position in positions
        if isinstance(out[position].get("content"), str)
    }
    costs = {position: estimate_tokens(str(row["content"])) for position, row in rows.items()}
    total = sum(costs.values())
    # Exhaust the preferred floor across all rows before going below it.
    for floor in (PROTECTED_ROW_MIN_CHARS, 0):
        for position in sorted(costs, key=lambda item: -costs[item]):
            if total <= budget:
                return
            text = str(rows[position]["content"])
            limit = len(str(out[position]["content"]))
            while limit > floor and total > budget:
                limit = max(floor, limit // 2)
                # truncate_chunk keeps at least 80 characters at each end;
                # a marker alone lets even many short rows fit a tight budget.
                folded = truncate_chunk(text, limit=limit) if limit else "[chunk truncated]"
                folded_cost = estimate_tokens(folded)
                if folded_cost >= costs[position] or len(folded) >= len(out[position]["content"]):
                    continue
                total -= costs[position] - folded_cost
                costs[position] = folded_cost
                out[position] = {**rows[position], "content": folded}


def _prune_stale_tool_pairs(
    rest: list[dict[str, Any]], *, protected_token_budget: int = 0
) -> list[dict[str, Any]]:
    """Collapse tool-call pairs (assistant.tool_calls + tool results) before the latest user message.

    Preserve the latest round verbatim so tool_calls and tool results remain fully paired under
    the OpenAI protocol; for earlier rounds, retain only assistant messages with response text
    (discard the tool_calls structure).

    Exception: an assistant flagged ``keep_tool_pair`` keeps its declaration and every directly
    following tool result verbatim — the escape hatch for calls whose result arrives
    asynchronously (dialog-style tools that pause the turn). Collapsing them would orphan the open
    call or erase the exchange.

    ``protected_token_budget`` caps what that exemption costs: when the protected run exceeds it,
    the largest of its tool rows are folded to fit (see :func:`_fold_protected_run`). The pairing
    and the declaration always survive; only the oversized bodies shrink.
    """
    last_user = -1
    for i, m in enumerate(rest):
        if m.get("role") == "user":
            last_user = i
    out: list[dict[str, Any]] = []
    protected_rows: list[int] = []
    # True while walking the tool-result run that follows a keep_tool_pair assistant.
    protected_pair = False
    for i, m in enumerate(rest):
        if i >= last_user:
            out.append(m)
            continue
        role = m.get("role")
        if role == "tool":
            if protected_pair:
                protected_rows.append(len(out))
                out.append(m)
            continue
        if role != "assistant":
            # A user row ends any protected run: tool rows after it belong to
            # a later pair, not to the protected assistant.
            protected_pair = False
            out.append(m)
            continue
        protected_pair = bool(m.get("keep_tool_pair"))
        if protected_pair or not m.get("tool_calls"):
            out.append(m)
        elif m.get("content"):
            out.append({"role": "assistant", "content": m["content"]})
    if protected_token_budget:
        _fold_protected_run(out, protected_rows, protected_token_budget)
    return out


def _snap_start_to_protected_pair(rest: list[dict[str, Any]], start: int) -> int:
    """Pull the fold boundary back so a ``keep_tool_pair`` pair stays in the verbatim tail.

    The boundary must not fall inside or immediately after a protected pair's
    result run: folding it would either erase the exchange or drop the pending
    marker of an open call — the next input would then start a new turn
    instead of resuming the paused one (an open call has no results, so its
    run ends right after the declaration itself). The pairs are tiny, so
    keeping them verbatim is cheap. An ``ask_pending`` declaration is pulled
    back wherever the cutoff sits: its marker must never fold away, or the
    paused dialog silently becomes a new task on the next input.
    """
    for i, m in enumerate(rest[:start]):
        if m.get("role") != "assistant" or not m.get("keep_tool_pair"):
            continue
        if m.get("ask_pending"):
            return i
        run_end = i + 1
        while run_end < len(rest) and rest[run_end].get("role") == "tool":
            run_end += 1
        if run_end >= start:
            return i
    return start


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
        [m for m in messages if m.get("role") != "system"],
        protected_token_budget=protected_run_budget(max_tokens),
    )
    # The old tool took unconditional effect on folding (micro-compression); further compression was only performed when a threshold was exceeded
    if max_tokens > 0 and estimate_messages_tokens(system + rest) <= max_tokens * threshold:
        return system + rest

    start = _align_split_start(rest, max(0, len(rest) - keep_recent))
    start = _snap_start_to_protected_pair(rest, start)
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
