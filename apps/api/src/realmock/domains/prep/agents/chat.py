"""Prep chat orchestration: synchronous single turn and event-stream answers.

The conversation layer extracted from the main ``agent`` file: ``run_chat`` /
``run_chat_stream`` drive tool rounds and replay the final answer. Persistence
(``finalize``), the ``compaction``/``usage`` payloads, and cancel-time saves
live in :mod:`persist`. The tool loop (``_run_tool_rounds``) remains in
:mod:`agent`; turn context assembly and mid-turn compaction live in
:mod:`round_compaction`, and the turn toolset policy in :mod:`turn_tools`.

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

from realmock.platform.capabilities.ai.context.options import (
    DEFAULT_AUTO_COMPACT_THRESHOLD,
    CompactionOptions,
)
from realmock.platform.capabilities.ai.llm.provider_errors import is_context_overflow
from realmock.platform.capabilities.ai.llm.stream_filters import sanitize_special_tokens

from .ask_user import extract_inline_ask_user
from .context import format_linked_sessions
from .persist import (
    compaction_event,
    finalize,
    finalize_with_delta,
    persist_cancel,
    usage_event,
)
from .quiz_render import prep_quiz_renderer
from .streaming import make_display_filter, slice_stream, stream_tool_rounds

if TYPE_CHECKING:
    from .agent import PrepAgent

logger = logging.getLogger(__name__)

# Event-queue bound: tool rounds await ``put`` past this depth.
_EVENT_QUEUE_MAXSIZE = 256

# Pre-loop status line per UI locale (streamed visibly before the tool loop).
_THINKING_STATUS_DEFAULT = "Thinking…"
_THINKING_STATUS = {
    "zh-CN": "思考中",
    "en": _THINKING_STATUS_DEFAULT,
}


def polish_final(text: str) -> tuple[str, dict[str, Any] | None]:
    """Outbound sanitization: recover inline ask_user calls + strip special tokens/inline tool blocks. Returns ``(body, ask event or None)``."""
    cleaned, ask_event = extract_inline_ask_user(text or "")
    return sanitize_special_tokens(cleaned, quiz_renderer=prep_quiz_renderer).strip(), ask_event


def _drop_trailing_assistant(agent: "PrepAgent") -> None:
    """Regenerate support: remove the last assistant reply so the turn can rerun."""
    if (
        agent.messages
        and isinstance(agent.messages[-1], dict)
        and agent.messages[-1].get("role") == "assistant"
    ):
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
    """Reset per-turn state and stash the turn policy on the agent."""
    agent._turn_state.reset(options)
    # A quiz posed last turn is no longer pending: the question lives in the
    # verbatim tail of the history, and a stale reminder would otherwise sit in
    # the working-memory block for the rest of the session.
    agent.memory.pending_quiz = ""
    agent.last_turn_id = uuid.uuid4().hex
    return agent._turn_state.policy


async def _force_compact_context(
    agent: "PrepAgent",
    policy: CompactionOptions,
    db: Session,
    context_session_ids: list[int] | None,
) -> list[dict[str, Any]]:
    """Force-compact working context once (overflow path, shared by both channels).

    The rebuilt context already contains any mid-turn compaction result, so
    the finalize merge (indexed against the old loop copy) must not run.
    """
    emergency = CompactionOptions(intensity="aggressive", directive=policy.directive, retain=0)
    agent._turn_state.mid_turn_base = None
    working = await agent._build_context(force=True, options=emergency)
    return await _inject_refs(agent, working, db, context_session_ids)


async def _final_answer_with_overflow_retry(
    agent: "PrepAgent",
    working: list[dict[str, Any]],
    policy: CompactionOptions,
    db: Session,
    context_session_ids: list[int] | None,
) -> str:
    """Non-streaming final answer; on context overflow, force-compact and retry once."""
    try:
        return await agent.llm.chat(working, temperature=0.7)
    except Exception as e:
        if not is_context_overflow(e):
            raise
        logger.warning("Prep final answer overflowed; force-compacting and retrying once")
        working = await _force_compact_context(agent, policy, db, context_session_ids)
        return await agent.llm.chat(working, temperature=0.7)


async def _prepare_turn(
    agent: "PrepAgent",
    user_text: str,
    db: Session,
    *,
    drop_last_assistant: bool = False,
    ui_locale: str | None = None,
    context_session_ids: list[int] | None = None,
    compact_threshold: float | None = None,
    compact_options: CompactionOptions | None = None,
) -> tuple[CompactionOptions, str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Shared turn setup for both channels.

    Appends the user message, builds working context (+ per-turn refs), and
    records pre_loop_len. The non-streaming caller ignores pre_build/report;
    the streaming caller diffs them into a compaction event.

    Args:
        agent: Live PrepAgent (messages/turn state mutated in place).
        user_text: Latest user message content.
        db: Sessions database session (context assembly may read linked sessions).
        drop_last_assistant: Regenerate support — drop the trailing reply first.
        ui_locale: UI locale hint for the reply language.
        context_session_ids: Per-turn referenced sessions (transient injection).
        compact_threshold: Auto-compact trigger fraction (None = agent default).
        compact_options: Compaction intensity/directive/retain policy.

    Returns:
        ``(policy, turn_id, working, pre_build, build_report)``.
    """
    policy = _begin_turn(agent, compact_options)
    turn_id = agent.last_turn_id or uuid.uuid4().hex
    await agent._ensure_system(db, ui_locale)
    if drop_last_assistant:
        _drop_trailing_assistant(agent)
    agent.messages.append({"role": "user", "content": user_text})
    pre_build = list(agent.messages)
    build_report: dict[str, Any] = {}
    working = await agent._build_context(
        threshold=compact_threshold, options=policy, report=build_report,
    )
    working = await _inject_refs(agent, working, db, context_session_ids)
    agent._turn_state.pre_loop_len = len(working)
    return policy, turn_id, working, pre_build, build_report


async def run_chat(
    agent: "PrepAgent", user_text: str, db: Session, *,
    drop_last_assistant: bool = False, ui_locale: str | None = None,
    context_session_ids: list[int] | None = None,
    compact_threshold: float | None = None,
    compact_options: CompactionOptions | None = None,
) -> str:
    """Synchronous single-round reply (non-streaming channel).

    The turn-start compaction runs silently (no SSE compaction event on this
    channel); persistence and overflow-retry semantics match run_chat_stream.

    Args:
        agent: Live PrepAgent (messages/memory/counters mutated in place).
        user_text: Latest user message content.
        db: Sessions database session (turn persists through it).
        drop_last_assistant: Regenerate support — drop the trailing reply first.
        ui_locale: UI locale hint for the reply language.
        context_session_ids: Per-turn referenced sessions (transient injection).
        compact_threshold: Auto-compact trigger fraction (None = agent default).
        compact_options: Compaction intensity/directive/retain policy.

    Returns:
        The sanitized final reply text.
    """
    policy, turn_id, working, _, _ = await _prepare_turn(
        agent, user_text, db,
        drop_last_assistant=drop_last_assistant, ui_locale=ui_locale,
        context_session_ids=context_session_ids,
        compact_threshold=compact_threshold,
        compact_options=compact_options,
    )

    asked_user: dict[str, bool] = {"on": False}
    working, early, groups, steps, thinking = await agent._run_tool_rounds(
        working, db, asked_user=asked_user
    )
    if asked_user["on"]:
        # The pop-up window has been displayed: consistent with the streaming path, waiting for the user to answer, no more fabricated answers
        final = agent.pending_reply_text()
    elif early:
        # The text at the end of the model is the final answer; pop-up events cannot be sent to non-streaming channels, and only purification is done.
        final, _ = polish_final(early)
        final = final or agent.pending_reply_text()
    else:
        final = await _final_answer_with_overflow_retry(agent, working, policy, db, context_session_ids)

    finalize(
        agent, working, final, db, tool_steps=steps, search_groups=groups, thinking=thinking,
        compact_threshold=compact_threshold, compact_options=policy, turn_id=turn_id,
    )
    return final if isinstance(final, str) else ""


def _new_content_state() -> dict[str, Any]:
    """Fresh speculative-streaming state (caller-owned; flushed after the loop)."""
    return {
        "streamed": False,
        "status_cleared": False,
        "filtered_text": "",
        "filter": make_display_filter(),
    }


def _take_mid_turn_report_event(agent: "PrepAgent") -> dict[str, Any] | None:
    """Consume the mid-turn compaction report as an SSE event (or None)."""
    report = agent._turn_state.mid_turn_report
    if report is None:
        return None
    agent._turn_state.mid_turn_report = None
    return {
        "type": "compaction",
        "before": report.get("before", 0),
        "after": report.get("after", 0),
        "summarized": True,
        "prompt_tokens": report.get("prompt_tokens", 0),
        "completion_tokens": report.get("completion_tokens", 0),
        "latency_ms": report.get("latency_ms", 0.0),
        "context_window": agent.context_window,
    }


async def run_chat_stream(
    agent: "PrepAgent", user_text: str, db: Session, *,
    drop_last_assistant: bool = False, ui_locale: str | None = None,
    context_session_ids: list[int] | None = None,
    compact_threshold: float | None = None,
    compact_options: CompactionOptions | None = None,
) -> AsyncIterator[str | dict[str, Any]]:
    """Think-then-act tool loop (events pushed immediately) → then stream the final answer.

    When the client disconnects (stop button), the partial turn is still
    persisted with ``stopped=True`` instead of being lost.

    Args:
        agent: Live PrepAgent (messages/memory/counters mutated in place).
        user_text: Latest user message content.
        db: Sessions database session (turn persists through it).
        drop_last_assistant: Regenerate support — drop the trailing reply first.
        ui_locale: UI locale hint for the reply language.
        context_session_ids: Per-turn referenced sessions (transient injection).
        compact_threshold: Auto-compact trigger fraction (None = agent default).
        compact_options: Compaction intensity/directive/retain policy.

    Yields ``str`` (response-body token) or ``dict`` (``status`` / ``thinking`` /
    ``tool_step`` / ``search_results`` / ``ask_user`` / ``usage`` / ``compaction`` events,
    plus ``{"type": "token"}`` payloads streamed live from inside the tool rounds).
    """
    policy, turn_id, working, pre_build, build_report = await _prepare_turn(
        agent, user_text, db,
        drop_last_assistant=drop_last_assistant, ui_locale=ui_locale,
        context_session_ids=context_session_ids,
        compact_threshold=compact_threshold,
        compact_options=compact_options,
    )

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
    content_state: dict[str, Any] = _new_content_state()
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
        elif value is not None:
            logger.warning("Prep unexpected tool outcome shape: %r", type(value))

        # Release the display filter's held-back tail (a partial special token,
        # partial block opening, or unterminated block at stream end).
        tail = content_state["filter"].flush()
        if tail:
            content_state["streamed"] = True
            yield tail

        # Agent-invoked mid-turn compaction ran inside the loop: surface it
        # like any other tool-driven step before the final answer streams.
        mid_event = _take_mid_turn_report_event(agent)
        if mid_event is not None:
            yield mid_event

        if asked_user["on"]:
            # Pop-up events and search cards have been pushed immediately when the tool is executed; here only the status line is cleared at the end
            yield {"type": "status", "text": ""}
            final = agent.pending_reply_text()
            async for piece in slice_stream(final):
                yield piece
            delta = finalize_with_delta(
                agent, working, final, db, tool_steps=tool_steps, search_groups=search_groups,
                thinking=thinking, compact_threshold=compact_threshold,
                compact_options=policy, turn_id=turn_id,
            )
            finalized = True
            if delta:
                yield delta
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
                filtered = str(content_state.get("filtered_text") or "")
                final = polish_final(filtered)[0].strip()
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
                    working = await _force_compact_context(agent, policy, db, context_session_ids)
                    async for token in agent.llm.chat_stream(working, temperature=0.7):
                        final += token
                        yield token
        elif not final:
            # Dialog rescued from an otherwise-empty body: keep the waiting line.
            final = agent.pending_reply_text()
            async for piece in slice_stream(final):
                yield piece

        delta = finalize_with_delta(
            agent, working, final, db, tool_steps=tool_steps, search_groups=search_groups,
            thinking=thinking, compact_threshold=compact_threshold,
            compact_options=policy, turn_id=turn_id,
        )
        finalized = True
        if delta:
            yield delta
    except (asyncio.CancelledError, GeneratorExit):
        # Client stopped the stream: persist the partial turn so the question
        # and whatever was produced survive a refresh. Never yield here, and
        # never let a persistence failure mask the cancellation itself.
        # Note: the blocking commit is intentional here — the turn must land
        # before the generator closes, or the question is lost on refresh.
        if not finalized:
            persist_cancel(
                agent, working, final, content_state, db,
                tool_steps=tool_steps, search_groups=search_groups,
                thinking=thinking, compact_threshold=compact_threshold,
                compact_options=policy, turn_id=turn_id,
            )
        raise


__all__ = [
    "compaction_event",
    "finalize",
    "polish_final",
    "run_chat",
    "run_chat_stream",
    "usage_event",
]
