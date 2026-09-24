"""Prep turn persistence: compaction events, message finalization, and usage deltas.

Split from ``chat.py`` (turn orchestration) so each module owns one duty:
``chat.py`` drives tool rounds and streams answers; this module persists turns
and builds the ``compaction``/``usage`` SSE payloads. Cancellation and
mid-turn failure land here too (``persist_cancel`` / ``persist_failed_turn``),
so a stop or an error never loses the typed question.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.domains.prep.agents.context import strip_ref_blocks
from realmock.platform.capabilities.ai.context.compress import (
    COMPACTION_DIGEST_MARKER,
    COMPACTION_SUMMARY_MARKER,
)
from realmock.platform.capabilities.ai.context.estimation import estimate_messages_tokens
from realmock.platform.capabilities.ai.context.manager import (
    estimate_tokens,
    prepare_llm_context,
)
from realmock.platform.capabilities.ai.context.options import (
    DEFAULT_AUTO_COMPACT_THRESHOLD,
    CompactionOptions,
)

if TYPE_CHECKING:
    from .agent import PrepAgent

logger = logging.getLogger(__name__)

def _summary_markers(messages: list[dict[str, Any]]) -> set[str]:
    """Fingerprints of compaction record blocks — LLM minutes and rule digests (turn-start vs post-build diffing)."""
    marks: set[str] = set()
    for m in messages or []:
        if not isinstance(m, dict) or m.get("role") != "system":
            continue
        content = str(m.get("content") or "")
        if content.startswith((COMPACTION_SUMMARY_MARKER, COMPACTION_DIGEST_MARKER)):
            marks.add(content[:200])
    return marks


def compaction_event(
    before_messages: list[dict[str, Any]],
    after_messages: list[dict[str, Any]],
    report: dict[str, Any] | None = None,
    *,
    context_window: int = 0,
    threshold: float | None = None,
) -> dict[str, Any] | None:
    """Build the ``compaction`` event-stream payload only when a real compaction record appeared.

    A new minutes/digest block means history was genuinely folded. Routine
    turn-start churn — stale tool-pair collapse, memory/lang-hint re-render —
    shifts the token estimate without writing any record, so it stays quiet
    instead of crying "compaction" every turn.

    Args:
        before_messages: History snapshot before context assembly.
        after_messages: Working context after assembly.
        report: Optional compaction cost report (tokens/latency).
        context_window: Model context window for the envelope (0 omits it).
        threshold: Auto-compact threshold echoed when inside (0, 1).

    Returns:
        The compaction event dict, or None when nothing was folded.
    """
    before = estimate_messages_tokens(before_messages)
    after = estimate_messages_tokens(after_messages)
    summarized = bool(_summary_markers(after_messages) - _summary_markers(before_messages))
    if not summarized:
        return None
    report = report or {}
    event: dict[str, Any] = {
        "type": "compaction",
        "before": before,
        "after": after,
        "summarized": summarized,
        "prompt_tokens": int(report.get("prompt_tokens", 0)),
        "completion_tokens": int(report.get("completion_tokens", 0)),
        "latency_ms": round(float(report.get("latency_ms", 0.0)), 1),
    }
    if context_window > 0:
        event["context_window"] = context_window
    if isinstance(threshold, (int, float)) and 0 < threshold < 1:
        event["threshold"] = threshold
    return event


def _merge_mid_turn(agent: "PrepAgent", working: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge loop tail onto mid-turn compacted base (or strip refs when no compaction).

    When agent-invoked compaction rewrote history mid-turn, the loop ran on a
    working copy: splice the new tail (indexed by pre_loop_len, pairing intact)
    back onto the compacted base instead of clobbering it.
    """
    base = agent._turn_state.mid_turn_base
    pre_len = agent._turn_state.pre_loop_len
    if base is not None and pre_len is not None:
        tail_new = working[pre_len:] if len(working) >= (pre_len or 0) else []
        agent._turn_state.mid_turn_base = None
        return strip_ref_blocks(base) + list(tail_new)
    return strip_ref_blocks(working)


def _build_assistant_message(
    final: str,
    *,
    tool_steps: list[dict[str, Any]] | None = None,
    search_groups: list[dict[str, Any]] | None = None,
    thinking: str | None = None,
    stopped: bool = False,
    turn_id: str | None = None,
) -> dict[str, Any]:
    """Build the persisted assistant message (string content + display metadata).

    Args:
        final: Sanitized reply body ("", non-str coerced to "").
        tool_steps: Display/persist tool progress cards (or None).
        search_groups: Retrieval cards for the search_results event (or None).
        thinking: Model reasoning text, persisted in full (display metadata only).
        stopped: True when the client disconnected mid-stream (partial turn).
        turn_id: Correlation id stamped on the assistant message (or None).

    Returns:
        The assistant message dict (content always a string).
    """
    # Guard against null finals (a provider may return an empty body): the
    # history contract requires string content; empty replies stay hidden.
    assistant_msg: dict[str, Any] = {"role": "assistant", "content": final if isinstance(final, str) else ""}
    if stopped:
        assistant_msg["stopped"] = True
    if turn_id:
        assistant_msg["turn_id"] = turn_id
    # Only metadata for display; LLM client only takes role/content and will not enter the model context.
    if tool_steps:
        assistant_msg["steps"] = tool_steps
    if search_groups:
        assistant_msg["search_groups"] = search_groups
    combined = (thinking or "").strip()
    if combined:
        # Persisted in full: thinking is display metadata only (never enters
        # the model context), and truncating it would lose reasoning history.
        assistant_msg["thinking"] = combined
    return assistant_msg


def _accumulate_usage(agent: "PrepAgent") -> None:
    """Recompute text estimate and accumulate provider-reported deltas (tolerant to Nones)."""
    # Session ring estimate: text-content estimate only (tool-call argument
    # payloads excluded by design; provider-reported columns are authoritative).
    agent.session.token_usage = sum(
        estimate_tokens(str(m.get("content") or "")) for m in agent.messages
        if isinstance(m, dict)
    )
    # Accumulated actual usage (available when the supplier returns; the estimated value is only used for the ring proportion)
    usage = getattr(agent.llm, "usage", None)
    if usage is not None:
        agent.session.prompt_tokens = (agent.session.prompt_tokens or 0) + (usage.prompt_tokens or 0)
        agent.session.completion_tokens = (
            agent.session.completion_tokens or 0
        ) + (usage.completion_tokens or 0)
        agent.session.cached_tokens = (agent.session.cached_tokens or 0) + (usage.cached_tokens or 0)
    # Last LLM call of the turn (per-call provider truth; the ring's context
    # occupancy comes from here, not from the text estimate).
    last_round = getattr(agent, "last_round_usage", None)
    if isinstance(last_round, dict):
        agent.session.last_round_prompt_tokens = int(last_round.get("prompt_tokens") or 0)
        agent.session.last_round_completion_tokens = int(last_round.get("completion_tokens") or 0)


def finalize(
    agent: "PrepAgent",
    working: list[dict[str, Any]],
    final: str,
    db: Session,
    *,
    tool_steps: list[dict[str, Any]] | None = None,
    search_groups: list[dict[str, Any]] | None = None,
    thinking: str | None = None,
    stopped: bool = False,
    compact_threshold: float | None = None,
    compact_options: CompactionOptions | None = None,
    turn_id: str | None = None,
) -> None:
    """Persist one turn: strip transient refs, append the assistant message, and update counters.

    Args:
        agent: Live PrepAgent (messages/memory/counters mutated in place).
        working: Loop-end working copy (may include transient #ref blocks).
        final: Sanitized reply body ("", non-str coerced to "").
        db: Session committed via PrepAgent._save (rollback on failure).
        tool_steps: Display/persist tool progress cards (or None).
        search_groups: Retrieval cards for the search_results event (or None).
        thinking: Model reasoning text, persisted in full (display metadata only).
        stopped: True when the client disconnected mid-stream (partial turn).
        compact_threshold: Persist-path budget, same semantics as turn-start.
        compact_options: Verbatim-tail policy (retain raised by intensity floor).
        turn_id: Correlation id stamped on the assistant message (or None).

    Returns:
        None; sets agent.last_prompt_estimate/last_message_count and commits.
    """
    # Per-turn # references are transient prompt material: measure them, then
    # strip before persisting so stored history stays clean.
    agent.last_prompt_estimate = estimate_messages_tokens(working)
    options = compact_options or CompactionOptions()
    agent.messages = _merge_mid_turn(agent, working)
    agent.messages.append(_build_assistant_message(
        final, tool_steps=tool_steps, search_groups=search_groups,
        thinking=thinking, stopped=stopped, turn_id=turn_id,
    ))
    if final:
        agent.memory.remember("asked", final)
    agent.messages = prepare_llm_context(
        agent.messages, agent.context_window, memory=agent.memory,
        # Persist-path bound follows the same auto-compact setting as the
        # turn-start LLM compaction, so a user threshold is honored, not
        # silently undercut by the default. The verbatim tail matches the
        # turn-start policy too: retain raised by the intensity floor,
        # floored at the latest exchange.
        threshold=(
            compact_threshold
            if isinstance(compact_threshold, (int, float)) and 0 < compact_threshold < 1
            else DEFAULT_AUTO_COMPACT_THRESHOLD
        ),
        keep_recent=max(options.keep_window(), 2),
    )
    _accumulate_usage(agent)
    # Backend-truth message count for the stream envelope: tool/trim rounds
    # make client-side +2-per-turn reservations drift, so every turn reports
    # its real length and the client resyncs instead of guessing.
    agent.last_message_count = len(agent.messages)
    agent._save(db)


def usage_event(agent: "PrepAgent") -> dict[str, Any] | None:
    """This turn's LLM usage delta; absent when the provider reported none.

    The frontend adds each turn delta into its session totals (additive merge);
    on session restore it reseeds from the summary columns instead. Request
    diagnostics (request id / latency / last error) ride along when known so
    the context panel can show them.
    """
    usage = getattr(agent.llm, "usage", None)
    if usage is None or not (usage.prompt_tokens or usage.completion_tokens):
        return None
    event = {"type": "usage", **usage.to_dict()}
    for key in ("requests", "last_request_id", "last_latency_ms", "last_error"):
        value = getattr(usage, key, None)
        if value:
            event[key] = value
    return event


def finalize_with_delta(
    agent: "PrepAgent",
    working: list[dict[str, Any]],
    final: str,
    db: Session,
    *,
    tool_steps: list[dict[str, Any]] | None = None,
    search_groups: list[dict[str, Any]] | None = None,
    thinking: str | None = None,
    compact_threshold: float | None = None,
    compact_options: CompactionOptions | None = None,
    turn_id: str | None = None,
) -> dict[str, Any] | None:
    """Capture the usage delta BEFORE persisting, then finalize; returns the delta event.

    Ordering matters: the delta is read from the live LLM client, while
    finalize accumulates it into session totals. Capturing first keeps the
    ``usage`` event (delta) and ``done`` envelope (totals) consistent even
    when persistence fails.

    Args:
        agent: Live PrepAgent (messages/memory/counters mutated in place).
        working: Loop-end working copy (may include transient #ref blocks).
        final: Sanitized reply body.
        db: Session committed via PrepAgent._save (rollback on failure).
        tool_steps: Display/persist tool progress cards (or None).
        search_groups: Retrieval cards for the search_results event (or None).
        thinking: Model reasoning text (or None).
        compact_threshold: Persist-path budget (None = default).
        compact_options: Verbatim-tail policy (or None for defaults).
        turn_id: Correlation id stamped on the assistant message (or None).

    Returns:
        The usage-delta event, or None when the provider reported nothing.
    """
    delta = usage_event(agent)
    finalize(
        agent, working, final, db, tool_steps=tool_steps, search_groups=search_groups,
        thinking=thinking, compact_threshold=compact_threshold,
        compact_options=compact_options, turn_id=turn_id,
    )
    return delta


def persist_cancel(
    agent: "PrepAgent",
    working: list[dict[str, Any]],
    final: str,
    content_state: dict[str, Any],
    db: Session,
    *,
    tool_steps: list[dict[str, Any]] | None = None,
    search_groups: list[dict[str, Any]] | None = None,
    thinking: str | None = None,
    compact_threshold: float | None = None,
    compact_options: CompactionOptions | None = None,
    turn_id: str | None = None,
) -> None:
    """Best-effort cancel-time persist (never raises; never yields)."""
    try:
        finalize(
            agent, working, final or str(content_state.get("filtered_text") or ""), db,
            tool_steps=tool_steps, search_groups=search_groups,
            thinking=thinking, stopped=True,
            compact_threshold=compact_threshold, compact_options=compact_options,
            turn_id=turn_id,
        )
    except Exception as persist_exc:
        logger.warning("Prep cancel-time persist failed: %s", persist_exc)


def persist_failed_turn(agent: "PrepAgent", db: Session) -> None:
    """Best-effort persist of a turn that died before finalize (never raises).

    The user message is already appended to history when a turn fails (LLM
    quota/auth errors, closing-stream failures); without this save the typed
    question would vanish on refresh. History is stored as it stands — the
    question without a reply, which the next turn picks up naturally.
    """
    try:
        agent._save(db)
    except Exception as save_exc:
        logger.warning("Prep failed-turn persist skipped: %s", save_exc)


__all__ = [
    "compaction_event",
    "finalize",
    "finalize_with_delta",
    "persist_cancel",
    "persist_failed_turn",
    "usage_event",
]
