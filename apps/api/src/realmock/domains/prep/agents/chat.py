"""Prep chat orchestration: synchronous single turn, SSE event stream, and persistence finalization.

The "conversation layer" extracted from the main ``agent`` file: ``run_chat`` / ``run_chat_stream``
drive tool rounds and replay the final answer, ``compaction_event`` builds the SSE compaction
payload, and ``finalize`` / ``polish_final`` / ``usage_event`` handle persistence sanitization.
The tool loop (``_run_tool_rounds``) and context assembly remain in :mod:`agent`.

Usage contract (frontend depends on this): the ``usage`` event carries this turn's
provider-reported DELTA (the per-request LLM client's accumulator, including turn
compression); session columns (``prompt/completion/cached_tokens``) accumulate
those deltas across turns. The ``done`` envelope carries session-level totals.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.platform.capabilities.ai.context.compress import (
    COMPACTION_DIGEST_MARKER,
    COMPACTION_SUMMARY_MARKER,
)
from realmock.platform.capabilities.ai.context.manager import (
    estimate_tokens,
    prepare_llm_context,
)
from realmock.platform.capabilities.ai.context.estimation import estimate_messages_tokens
from realmock.platform.capabilities.ai.context.options import (
    DEFAULT_AUTO_COMPACT_THRESHOLD,
    CompactionOptions,
)
from realmock.platform.capabilities.ai.llm.provider_errors import is_context_overflow
from realmock.platform.capabilities.ai.llm.stream_filters import sanitize_special_tokens

from .ask_user import extract_inline_ask_user
from .context import format_linked_sessions, strip_ref_blocks
from .streaming import make_display_filter, slice_stream, stream_tool_rounds

if TYPE_CHECKING:
    from .agent import PrepAgent

logger = logging.getLogger(__name__)

# The upper limit of the length of the persisted thinking (metadata for display)
_MAX_PERSISTED_THINKING_CHARS = 20_000
# SSE event-queue bound: tool rounds await ``put`` past this depth.
_EVENT_QUEUE_MAXSIZE = 256

# Pre-loop status line per UI locale (streamed visibly before the tool loop).
_THINKING_STATUS_DEFAULT = "Thinking…"
_THINKING_STATUS = {
    "zh-CN": "思考中",
    "en": _THINKING_STATUS_DEFAULT,
}


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
    """Build the ``compaction`` SSE payload only when a real compaction record appeared.

    A new minutes/digest block means history was genuinely folded. Routine
    turn-start churn — stale tool-pair collapse, memory/lang-hint re-render —
    shifts the token estimate without writing any record, so it stays quiet
    instead of crying "compaction" every turn.
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
    """Persist: append the assistant message (including steps/retrieval cards/thinking metadata), apply rule-based compaction, and update token statistics."""
    # Per-turn # references are transient prompt material: measure them, then
    # strip before persisting so stored history stays clean.
    agent.last_prompt_estimate = estimate_messages_tokens(working)
    options = compact_options or CompactionOptions()
    if agent._mid_turn_base is not None and agent._pre_loop_len is not None:
        # Agent-invoked mid-turn compaction rewrote persisted history while the
        # loop ran on: merge the loop's new tail (current round, pairing intact)
        # back on top of the compacted base instead of clobbering it.
        tail_new = working[agent._pre_loop_len :] if len(working) >= (agent._pre_loop_len or 0) else []
        agent.messages = strip_ref_blocks(agent._mid_turn_base) + list(tail_new)
        agent._mid_turn_base = None
    else:
        agent.messages = strip_ref_blocks(working)
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
        assistant_msg["thinking"] = combined[:_MAX_PERSISTED_THINKING_CHARS]
    agent.messages.append(assistant_msg)
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
    # Session ring estimate: text-content estimate only (tool-call argument
    # payloads excluded by design; provider-reported columns are authoritative).
    agent.session.token_usage = sum(
        estimate_tokens(str(m.get("content") or "")) for m in agent.messages
    )
    # Accumulated actual usage (available when the supplier returns; the estimated value is only used for the ring proportion)
    usage = getattr(agent.llm, "usage", None)
    if usage is not None:
        agent.session.prompt_tokens = (agent.session.prompt_tokens or 0) + usage.prompt_tokens
        agent.session.completion_tokens = (
            agent.session.completion_tokens or 0
        ) + usage.completion_tokens
        agent.session.cached_tokens = (agent.session.cached_tokens or 0) + usage.cached_tokens
    # Backend-truth message count for the stream envelope: tool/trim rounds
    # make client-side +2-per-turn reservations drift, so every turn reports
    # its real length and the client resyncs instead of guessing.
    agent.last_message_count = len(agent.messages)
    agent._save(db)


def polish_final(text: str) -> tuple[str, dict[str, Any] | None]:
    """Outbound sanitization: recover inline ask_user calls + strip special tokens/inline tool blocks. Returns ``(body, ask event or None)``."""
    cleaned, ask_event = extract_inline_ask_user(text or "")
    return sanitize_special_tokens(cleaned).strip(), ask_event


def usage_event(agent: "PrepAgent") -> dict[str, Any] | None:
    """This turn's LLM usage delta; absent when the provider reported none.

    The frontend adds each turn delta into its session totals (additive merge);
    on session restore it reseeds from the summary columns instead.
    """
    usage = getattr(agent.llm, "usage", None)
    if usage is None or not (usage.prompt_tokens or usage.completion_tokens):
        return None
    return {"type": "usage", **usage.to_dict()}


def _drop_trailing_assistant(agent: "PrepAgent") -> None:
    """Regenerate support: remove the last assistant reply so the turn can rerun."""
    if agent.messages and agent.messages[-1].get("role") == "assistant":
        agent.messages.pop()


async def _inject_refs(
    agent: "PrepAgent",
    working: list[dict[str, Any]],
    db: Session,
    context_session_ids: list[int] | None,
) -> list[dict[str, Any]]:
    """Append the per-turn # reference block (transient; stripped at persist).

    Referenced sessions render with the same single-level budgets as linked
    sessions. Unknown/deleted ids resolve to nothing and never fail the turn.
    """
    if not context_session_ids:
        return working
    block = await asyncio.to_thread(
        format_linked_sessions, db, context_session_ids,
        exclude_id=getattr(agent.session, "id", None),
    )
    if not block:
        return working
    return [*working, {"role": "system", "content": block}]


def _begin_turn(agent: "PrepAgent", options: CompactionOptions | None) -> CompactionOptions:
    """Reset per-turn compaction state and stash the turn policy on the agent."""
    policy = options or CompactionOptions()
    agent._turn_policy = policy
    agent._compact_used_this_turn = False
    agent._expanded_this_turn = False
    agent._turn_tools = None
    agent._mid_turn_base = None
    agent._mid_turn_report = None
    agent._pre_loop_len = None
    # A quiz posed last turn is no longer pending: the question lives in the
    # verbatim tail of the history, and a stale reminder would otherwise sit in
    # the working-memory block for the rest of the session.
    agent.memory.pending_quiz = ""
    agent.last_turn_id = uuid.uuid4().hex
    return policy


async def _final_answer_with_overflow_retry(
    agent: "PrepAgent",
    working: list[dict[str, Any]],
    policy: CompactionOptions,
) -> str:
    """Non-streaming final answer; on context overflow, force-compact and retry once."""
    try:
        return await agent.llm.chat(working, temperature=0.7)
    except Exception as e:
        if not is_context_overflow(e):
            raise
        logger.warning("Prep final answer overflowed; force-compacting and retrying once")
        emergency = CompactionOptions(intensity="aggressive", directive=policy.directive, retain=0)
        # The rebuilt context already contains any mid-turn compaction result, so
        # the finalize merge (indexed against the old loop copy) must not run.
        agent._mid_turn_base = None
        working = await agent._build_context(force=True, options=emergency)
        return await agent.llm.chat(working, temperature=0.7)


async def run_chat(
    agent: "PrepAgent", user_text: str, db: Session, *,
    drop_last_assistant: bool = False, ui_locale: str | None = None,
    context_session_ids: list[int] | None = None,
    compact_threshold: float | None = None,
    compact_options: CompactionOptions | None = None,
) -> str:
    policy = _begin_turn(agent, compact_options)
    turn_id = agent.last_turn_id or uuid.uuid4().hex
    agent._ensure_system(db, ui_locale)
    if drop_last_assistant:
        _drop_trailing_assistant(agent)
    agent.messages.append({"role": "user", "content": user_text})
    working = await agent._build_context(threshold=compact_threshold, options=policy)
    working = await _inject_refs(agent, working, db, context_session_ids)
    agent._pre_loop_len = len(working)

    asked_user: dict[str, bool] = {"on": False}
    working, early, groups, steps, thinking = await agent._run_tool_rounds(
        working, db, asked_user=asked_user
    )
    if asked_user["on"]:
        # The pop-up window has been displayed: consistent with the streaming path, waiting for the user to answer, no more fabricated answers
        final = agent.waiting_line()
    elif early:
        # The text at the end of the model is the final answer; pop-up events cannot be sent to non-streaming channels, and only purification is done.
        final, _ = polish_final(early)
        final = final or agent.waiting_line()
    else:
        final = await _final_answer_with_overflow_retry(agent, working, policy)

    finalize(
        agent, working, final, db, tool_steps=steps, search_groups=groups, thinking=thinking,
        compact_threshold=compact_threshold, compact_options=policy, turn_id=turn_id,
    )
    return final if isinstance(final, str) else ""


async def run_chat_stream(
    agent: "PrepAgent", user_text: str, db: Session, *,
    drop_last_assistant: bool = False, ui_locale: str | None = None,
    context_session_ids: list[int] | None = None,
    compact_threshold: float | None = None,
    compact_options: CompactionOptions | None = None,
) -> AsyncIterator[str | dict[str, Any]]:
    """ReAct tool loop (events pushed immediately) → then stream the final answer.

    Yields ``str`` (response-body token) or ``dict`` (``status`` / ``thinking`` /
    ``tool_step`` / ``search_results`` / ``ask_user`` / ``usage`` / ``compaction`` events,
    plus ``{"type": "token"}`` payloads streamed live from inside the tool rounds).

    When the client disconnects (stop button), the partial turn is still
    persisted with ``stopped=True`` instead of being lost.
    """
    policy = _begin_turn(agent, compact_options)
    turn_id = agent.last_turn_id or uuid.uuid4().hex
    agent._ensure_system(db, ui_locale)
    if drop_last_assistant:
        _drop_trailing_assistant(agent)
    agent.messages.append({"role": "user", "content": user_text})
    pre_build = list(agent.messages)
    build_report: dict[str, Any] = {}
    working = await agent._build_context(
        threshold=compact_threshold, options=policy, report=build_report,
    )
    working = await _inject_refs(agent, working, db, context_session_ids)
    agent._pre_loop_len = len(working)

    start_event = compaction_event(
        pre_build, working, build_report,
        context_window=agent.context_window,
        threshold=(
            compact_threshold
            if isinstance(compact_threshold, (int, float)) and 0 < compact_threshold < 1
            else DEFAULT_AUTO_COMPACT_THRESHOLD
        ),
    )
    if start_event is not None:
        yield start_event
    yield {"type": "status", "text": _THINKING_STATUS.get(ui_locale or "", _THINKING_STATUS_DEFAULT)}
    await asyncio.sleep(0)

    # Bounded queue: backpressure when the SSE consumer lags instead of
    # unbounded memory growth on slow connections.
    events: asyncio.Queue = asyncio.Queue(maxsize=_EVENT_QUEUE_MAXSIZE)
    asked_user: dict[str, bool] = {"on": False}
    # Speculative content-streaming state: one display filter held across rounds
    # so its rules (the display mirror of polish_final) apply across chunk and
    # round boundaries; the loop-end flush releases any held-back tail.
    content_state: dict[str, Any] = {
        "streamed": False,
        "status_cleared": False,
        "raw": "",
        "filter": make_display_filter(),
    }
    outcome: dict[str, Any] = {}
    early: str | None = None
    search_groups: list[dict[str, Any]] = []
    tool_steps: list[dict[str, Any]] = []
    thinking: str = ""
    final: str = ""
    finalized = False
    try:
        async for item in stream_tool_rounds(
            agent._run_tool_rounds, outcome, events, working, db,
            asked_user=asked_user, content_state=content_state,
        ):
            yield item

        error = outcome.get("error")
        if error is not None:
            # Orchestration/business failures must surface (SSE error event via
            # the route layer), never degrade into a tool-less silent answer —
            # same contract as the non-streaming run_chat path.
            raise error

        value = outcome.get("value")
        if isinstance(value, tuple) and len(value) == 5:
            working, early, search_groups, tool_steps, thinking = value

        # Release the display filter's held-back tail (a partial special token,
        # partial block opening, or unterminated block at stream end).
        tail = content_state["filter"].flush()
        if tail:
            content_state["streamed"] = True
            yield tail

        # Agent-invoked mid-turn compaction ran inside the loop: surface it
        # like any other tool-driven step before the final answer streams.
        if agent._mid_turn_report is not None:
            report = agent._mid_turn_report
            agent._mid_turn_report = None
            yield {
                "type": "compaction",
                "before": report.get("before", 0),
                "after": report.get("after", 0),
                "summarized": True,
                "prompt_tokens": report.get("prompt_tokens", 0),
                "completion_tokens": report.get("completion_tokens", 0),
                "latency_ms": report.get("latency_ms", 0.0),
                "context_window": agent.context_window,
            }

        if asked_user["on"]:
            # Pop-up events and search cards have been pushed immediately when the tool is executed; here only the status line is cleared at the end
            yield {"type": "status", "text": ""}
            final = agent.waiting_line()
            async for piece in slice_stream(final):
                yield piece
            finalize(agent, working, final, db, tool_steps=tool_steps, search_groups=search_groups, thinking=thinking, compact_threshold=compact_threshold, compact_options=policy, turn_id=turn_id)
            finalized = True
            event = usage_event(agent)
            if event:
                yield event
            return

        if search_groups:
            yield {"type": "search_results", "groups": search_groups}

        # Start of text: clear status line (no-op when streaming content already cleared it)
        yield {"type": "status", "text": ""}
        inline_ask = None
        if early:
            # The final text of the model is the final answer (may be accompanied by inline ask_user drift): first purify and rescue and then slice and playback
            final, inline_ask = polish_final(early)
            if final and not content_state.get("streamed"):
                # Nothing was streamed live (non-streaming LLM fallback): replay in slices.
                async for piece in slice_stream(final):
                    yield piece
            if inline_ask is not None:
                # Rescue it into a real pop-up window: a selection box pops up after the context is given in the text
                yield {"type": "ask_user", **inline_ask}
        if not final and inline_ask is None:
            if content_state.get("streamed"):
                # Speculative tokens already reached the user (loop exhausted or
                # failed mid-stream). Regenerating would repeat on screen and
                # fork from persisted history — finish with the streamed text.
                raw = str(content_state.get("raw") or "")
                final = polish_final(raw)[0].strip()
                if not final:
                    # Streamed text sanitized to nothing: fall through to the
                    # live closing stream below.
                    content_state["streamed"] = False
            if not content_state.get("streamed"):
                # Bottom line: nothing user-visible exists yet (rounds exhausted, LLM
                # exception, or early text sanitized to nothing) — stream a closing
                # answer live instead of ending the turn empty.
                final = ""
                try:
                    async for token in agent.llm.chat_stream(working, temperature=0.7):
                        final += token
                        yield token
                except Exception as e:
                    if not is_context_overflow(e) or final:
                        raise
                    # Overflow before any token: force-compact and retry the final
                    # answer once instead of failing the turn.
                    logger.warning("Prep stream final overflowed; force-compacting and retrying once")
                    emergency = CompactionOptions(intensity="aggressive", directive=policy.directive, retain=0)
                    # The rebuilt context already contains any mid-turn compaction
                    # result, so the finalize merge must not run (see finalize).
                    agent._mid_turn_base = None
                    working = await agent._build_context(force=True, options=emergency)
                    working = await _inject_refs(agent, working, db, context_session_ids)
                    async for token in agent.llm.chat_stream(working, temperature=0.7):
                        final += token
                        yield token
        elif not final:
            # Dialog rescued from an otherwise-empty body: keep the waiting line.
            final = agent.waiting_line()
            async for piece in slice_stream(final):
                yield piece

        event = usage_event(agent)
        finalize(agent, working, final, db, tool_steps=tool_steps, search_groups=search_groups, thinking=thinking, compact_threshold=compact_threshold, compact_options=policy, turn_id=turn_id)
        finalized = True
        if event:
            yield event
    except (asyncio.CancelledError, GeneratorExit):
        # Client stopped the stream: persist the partial turn so the question
        # and whatever was produced survive a refresh. Never yield here, and
        # never let a persistence failure mask the cancellation itself.
        if not finalized:
            try:
                finalize(
                    agent, working, final or str(content_state.get("raw") or ""), db,
                    tool_steps=tool_steps, search_groups=search_groups,
                    thinking=thinking, stopped=True,
                    compact_threshold=compact_threshold, compact_options=policy,
                    turn_id=turn_id,
                )
            except Exception as persist_exc:
                logger.warning("Prep cancel-time persist failed: %s", persist_exc)
        raise


__all__ = [
    "_EVENT_QUEUE_MAXSIZE",
    "_MAX_PERSISTED_THINKING_CHARS",
    "compaction_event",
    "finalize",
    "polish_final",
    "run_chat",
    "run_chat_stream",
    "usage_event",
]
