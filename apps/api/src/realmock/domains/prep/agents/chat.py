"""Prep chat orchestration: synchronous single turn and event-stream answers.

The prep agent conversation layer: ``run_chat`` /
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

from realmock.platform.capabilities.ai.agent.working_memory import MEMORY_MARKER
from realmock.platform.capabilities.ai.context.options import (
    DEFAULT_AUTO_COMPACT_THRESHOLD,
    CompactionOptions,
)
from realmock.platform.capabilities.ai.llm.provider_errors import is_context_overflow
from realmock.platform.capabilities.ai.llm.stream_filters import sanitize_special_tokens

from .ask_user import (
    DIALOG_ANSWER_OBSERVATION,
    RESUME_TASK_KEY,
    extract_inline_ask_user,
    find_pending_ask,
    insert_dialog_answer,
    original_task_text,
    undo_dialog_answer,
)
from .context import format_linked_sessions
from .memory_precipitate import schedule_turn_memory_precipitation
from .persist import (
    compaction_event,
    complete_interrupted_tool_calls,
    finalize,
    finalize_with_delta,
    persist_cancel,
    persist_failed_turn,
    usage_event,
)
from .quiz_render import prep_quiz_renderer
from .streaming import make_display_filter, slice_stream, stream_background_events

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


def sanitize_final_reply(text: str) -> tuple[str, dict[str, Any] | None]:
    """Outbound sanitization: recover inline ask_user calls + strip special tokens/inline tool blocks. Returns ``(body, ask event or None)``."""
    cleaned, ask_event = extract_inline_ask_user(text or "")
    return sanitize_special_tokens(cleaned, quiz_renderer=prep_quiz_renderer).strip(), ask_event


def _drop_trailing_exchange(agent: "PrepAgent", user_text: str) -> None:
    """Regenerate support: remove the last exchange so the turn can rerun.

    Drops the whole trailing exchange back to the question that owns it: the
    final reply, any tool results, and the tool_call declarations that own
    those results — paused-dialog and normal tool rounds alike. Stopping at a
    declaration would leave it on history without its result (the provider
    rejects that) and the content guard would then keep the old question,
    duplicating it on the rerun. A user-only tail (a previously failed turn
    that persisted just the question) is popped too, so regenerating it does
    not duplicate the question either. Regenerable trailing system rows (the
    working-memory block finalize re-appends) are skipped first, so the drop
    below can reach the real exchange.

    The exchange drop is content-guarded: the trailing user row owns it only
    when its text matches the replayed question. A mismatch means the previous
    turn never finished (a cancel inside the prepare window can persist
    nothing, leaving an older exchange as the tail) — or the exchange is a
    finished turn the rerun does not replace. Either way nothing is dropped:
    stripping the reply or tool evidence of an exchange the rerun does not
    re-append would corrupt it, so the replay is appended as a fresh turn.
    """
    # Only the working-memory block is regenerable prompt material: every
    # finalize re-appends it at the tail, and a regenerate that stops at it
    # would never reach the exchange below. Compaction records and the seed
    # system prompt are NOT regenerable — a forced fold can leave its summary
    # block as the tail (the folded exchange has no user row left to match),
    # and popping it would destroy the only copy of the folded history.
    while (
        agent.messages
        and isinstance(agent.messages[-1], dict)
        and agent.messages[-1].get("role") == "system"
        and str(agent.messages[-1].get("content") or "").startswith(MEMORY_MARKER)
    ):
        agent.messages.pop()
    # Locate the trailing user row and drop the whole exchange it owns —
    # reply, tool rounds, paused-dialog declarations — only when the question
    # matches the replayed text, so the rerun replaces rather than duplicates.
    owner = None
    for index in range(len(agent.messages) - 1, -1, -1):
        message = agent.messages[index]
        if isinstance(message, dict) and message.get("role") == "user":
            owner = index
            break
    if (
        owner is not None
        and isinstance(agent.messages[owner], dict)
        and agent.messages[owner].get("content") == user_text
    ):
        del agent.messages[owner:]


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
        format_linked_sessions,
        db,
        context_session_ids,
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
    agent.last_ask_event = None
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
    usage_before = agent.usage_snapshot()
    try:
        answer = await agent.llm.chat(working, temperature=0.7)
        agent.note_round_usage(usage_before)
        return answer
    except Exception as e:
        if not is_context_overflow(e):
            raise
        logger.warning("Prep final answer overflowed; force-compacting and retrying once")
        working = await _force_compact_context(agent, policy, db, context_session_ids)
        retry_before = agent.usage_snapshot()
        answer = await agent.llm.chat(working, temperature=0.7)
        agent.note_round_usage(retry_before)
        return answer


def _abandon_resumed_turn(
    agent: "PrepAgent", messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Roll a failed resume back to the exact paused snapshot.

    The resume turn consumed the dialog in place (pointer inserted, marker
    cleared, answer appended). When the turn dies before finalize, that state
    must not persist: the retry would append the answer a second time and
    the dialog could never resume. Repairs the list the caller is about to
    persist — ``agent.messages``, or the loop's working copy on a cancel
    path (located by pointer content, since a rebuilt list shifts indexes).
    """
    index = agent._turn_state.resumed_dialog_index
    if index is not None:
        pointer = messages[index + 1] if index + 1 < len(messages) else None
        if not (isinstance(pointer, dict) and pointer.get("content") == DIALOG_ANSWER_OBSERVATION):
            index = None
    if index is None:
        # The caller's list was rebuilt (turn-start compaction) and the row
        # shifted: locate this turn's pointer by content instead. Scanning
        # from the end picks the NEWEST pointer — earlier, already-answered
        # dialogs carry the same observation text and must not win.
        for position in range(len(messages) - 1, -1, -1):
            message = messages[position]
            if (
                isinstance(message, dict)
                and message.get("role") == "tool"
                and message.get("content") == DIALOG_ANSWER_OBSERVATION
            ):
                index = position - 1
                break
    if index is None or index < 0:
        return messages
    agent._turn_state.resumed_dialog_index = None
    undo_dialog_answer(messages, index)
    # The just-typed answer is the first user row AFTER the pointer: prepare
    # appends it to the tail before inserting the pointer, and the rows in
    # between belong to the paused turn (waiting line, working memory). On a
    # cancel path the loop may have appended further rows behind the answer —
    # everything from the answer on goes, so persistence lands the exact
    # paused snapshot and a retry cannot see half-generated rounds.
    for scan in range(index + 1, len(messages)):
        row = messages[scan]
        if isinstance(row, dict) and row.get("role") == "user":
            del messages[scan:]
            break
    return messages


def _persist_failure_state(
    agent: "PrepAgent",
    asked_user: dict[str, Any],
    loop_working: dict[str, Any],
    working: list[dict[str, Any]],
    turn_id: str,
    policy: CompactionOptions | None,
    db: Session,
    *,
    compact_threshold: float | None = None,
    compact_options: CompactionOptions | None = None,
    tool_steps: list[dict[str, Any]] | None = None,
    search_groups: list[dict[str, Any]] | None = None,
    thinking: str = "",
) -> bool:
    """Land the pause state when a turn with a fired dialog dies before finalize.

    A business/LLM error raised after ``ask_user`` emitted its event still
    owes the user an answerable dialog: persist the loop's working copy with
    the open call marked (and its dangling siblings completed) instead of
    dropping the turn to a bare question persist, or the answer would start a
    new task. Returns True when the pause state was persisted; False means
    the caller should run the plain failed-turn path.
    """
    gate_event = asked_user.get("event")
    ask_event = gate_event if isinstance(gate_event, dict) else None
    if ask_event is None:
        return False
    persist_cancel(
        agent,
        # The dialog's open call exists only on the loop's working copy.
        loop_working.get("working") or working,
        agent.pending_reply_text(),
        {},  # no speculative-stream state on the sync failure path
        db,
        tool_steps=tool_steps,
        search_groups=search_groups,
        thinking=thinking,
        compact_threshold=compact_threshold,
        compact_options=compact_options,
        turn_id=turn_id,
        ask=ask_event,
        pause_event=ask_event,
    )
    return True


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
    memory_index_limit: int | None = None,
) -> tuple[CompactionOptions, str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Shared turn setup for both channels.

    Appends the user message, builds working context (+ per-turn refs), and
    records pre_loop_len. The non-streaming caller ignores pre_build/report;
    the streaming caller diffs them into a compaction event.

    Args:
        agent: Live PrepAgent (messages/turn state mutated in place).
        user_text: Latest user message content.
        db: Sessions database session (context assembly may read linked sessions).
        drop_last_assistant: Regenerate support — drop the trailing exchange (reply + question) first.
        ui_locale: UI locale hint for the reply language.
        context_session_ids: Per-turn referenced sessions (transient injection).
        compact_threshold: Auto-compact trigger fraction (None = agent default).
        compact_options: Compaction intensity/directive/retain policy.

    Returns:
        ``(policy, turn_id, working, pre_build, build_report)``.
    """
    policy = _begin_turn(agent, compact_options)
    turn_id = agent.last_turn_id or uuid.uuid4().hex
    # Memory-index width applies when the seed is first built; stored on the
    # agent so the request value reaches the (threaded) seed builder.
    if memory_index_limit is not None:
        agent.memory_index_limit = memory_index_limit
    await agent._ensure_system(db, ui_locale)
    if drop_last_assistant:
        _drop_trailing_exchange(agent, user_text)
    agent.messages.append({"role": "user", "content": user_text})
    # A paused dialog turns this input into its answer: complete the open
    # ask_user call with a pointer observation (the answer itself stays in
    # the user message just appended) and re-enter the SAME turn, so the
    # interrupted task remains the live task instead of the reply reading
    # like a new topic (see ask_user.pending). Popup answers and free-typed
    # text arrive through the same channel — both are the dialog's reply.
    pending_index = find_pending_ask(agent.messages)
    if pending_index is not None:
        # The resumed turn freezes its toolset from the ORIGINAL task text,
        # not the dialog reply: the reply is the channel, not the task, and
        # text-gated tools the task activated (repo talk) must stay declared
        # across the pause. A pause-time stamp on the pending row is
        # authoritative (earlier dialog exchanges may already have folded);
        # otherwise skip prior dialog answers text-wise.
        pending_message = agent.messages[pending_index]
        stored_task = (
            pending_message.get(RESUME_TASK_KEY) if isinstance(pending_message, dict) else None
        )
        agent._turn_state.resume_task_text = (
            stored_task
            if isinstance(stored_task, str) and stored_task
            else original_task_text(agent.messages, pending_index)
        )
        if insert_dialog_answer(agent.messages, pending_index):
            agent._turn_state.resumed_dialog_index = pending_index
        else:
            # A stored marker without a resolvable open call would leave a
            # dangling declaration the provider rejects on every request.
            # Complete it and run this input as a normal turn instead.
            logger.warning(
                "Prep resume found an unresolvable pending marker sid=%s",
                getattr(agent.session, "id", ""),
            )
            complete_interrupted_tool_calls(agent.messages)
            agent._turn_state.resume_task_text = None
    pre_build = list(agent.messages)
    build_report: dict[str, Any] = {}
    try:
        working = await agent._build_context(
            threshold=compact_threshold,
            options=policy,
            report=build_report,
        )
        working = await _inject_refs(agent, working, db, context_session_ids)
    except Exception:
        # A failed prepare must not consume the dialog: roll the history back
        # to the exact paused snapshot (pointer removed, marker restored, the
        # just-typed answer dropped) so the failed-turn persist still resumes
        # and a retry does not duplicate the answer.
        _abandon_resumed_turn(agent, agent.messages)
        raise
    agent._turn_state.pre_loop_len = len(working)
    return policy, turn_id, working, pre_build, build_report


async def run_chat(
    agent: "PrepAgent",
    user_text: str,
    db: Session,
    *,
    drop_last_assistant: bool = False,
    ui_locale: str | None = None,
    context_session_ids: list[int] | None = None,
    compact_threshold: float | None = None,
    compact_options: CompactionOptions | None = None,
    memory_index_limit: int | None = None,
) -> str:
    """Synchronous single-round reply (non-streaming channel).

    The turn-start compaction runs silently (no SSE compaction event on this
    channel); persistence and overflow-retry semantics match run_chat_stream.

    Args:
        agent: Live PrepAgent (messages/memory/counters mutated in place).
        user_text: Latest user message content.
        db: Sessions database session (turn persists through it).
        drop_last_assistant: Regenerate support — drop the trailing exchange (reply + question) first.
        ui_locale: UI locale hint for the reply language.
        context_session_ids: Per-turn referenced sessions (transient injection).
        compact_threshold: Auto-compact trigger fraction (None = agent default).
        compact_options: Compaction intensity/directive/retain policy.

    Returns:
        The sanitized final reply text.
    """
    # Hoisted so the failure handler below can read the dialog gate and the
    # loop's working copy even when the turn dies before the loop starts.
    asked_user: dict[str, Any] = {"on": False}
    loop_working: dict[str, Any] = {}
    turn_id = ""
    policy: CompactionOptions | None = None
    working: list[dict[str, Any]] = []
    committed = False
    try:
        policy, turn_id, working, _, _ = await _prepare_turn(
            agent,
            user_text,
            db,
            drop_last_assistant=drop_last_assistant,
            ui_locale=ui_locale,
            context_session_ids=context_session_ids,
            compact_threshold=compact_threshold,
            compact_options=compact_options,
            memory_index_limit=memory_index_limit,
        )

        working, early, groups, steps, thinking = await agent._run_tool_rounds(
            working, db, asked_user=asked_user, working_out=loop_working
        )
        ask_event: dict[str, Any] | None = None
        final: str | None = None
        if asked_user["on"]:
            # The ask_user tool fired; the dialog payload rides the response's
            # ask_user field (the stream channel emits it as a live event instead).
            final = agent.pending_reply_text()
            gate_event = asked_user.get("event")
            ask_event = dict(gate_event) if isinstance(gate_event, dict) else None
        else:
            inline_ask = None
            if early:
                # Trailing model text is the final answer; an inline ask_user
                # drift is rescued into the response's dialog field while the
                # prose stays as the reply body (mirrors the stream channel).
                final, inline_ask = sanitize_final_reply(early)
                if inline_ask is not None:
                    ask_event = inline_ask
            if ask_event is not None:
                if not final:
                    # Dialog rescued from an otherwise-empty body: keep the
                    # waiting line under it.
                    final = agent.pending_reply_text()
            elif not final:
                # Nothing user-visible exists: generate a closing answer, same as
                # the stream channel (never fall back to the waiting line without
                # a dialog — that copy would be misleading).
                final = await _final_answer_with_overflow_retry(
                    agent, working, policy, db, context_session_ids
                )
        agent.last_ask_event = ask_event

        finalize(
            # The history contract requires string content (None coerces to an
            # empty, hidden reply — finalize applies the same rule).
            agent,
            working,
            final or "",
            db,
            tool_steps=steps,
            search_groups=groups,
            thinking=thinking,
            compact_threshold=compact_threshold,
            compact_options=policy,
            turn_id=turn_id,
            ask=ask_event,
            # A tool-invoked dialog ends the turn PAUSED on its open call;
            # inline-rescued dialogs have no tool_call to resume.
            pause_event=ask_event if asked_user["on"] else None,
        )
        committed = True
        # End-of-turn curation runs detached: the reply returns immediately.
        schedule_turn_memory_precipitation(
            agent, user_text, final if isinstance(final, str) else ""
        )
        return final if isinstance(final, str) else ""
    except Exception:
        if committed:
            # finalize already landed the turn (a detached curation task or a
            # late stream glitch raised afterwards): the saved history must
            # not be rolled back or persisted a second time.
            raise
        if not _persist_failure_state(
            agent,
            asked_user,
            loop_working,
            working,
            turn_id,
            policy,
            db,
            compact_threshold=compact_threshold,
            compact_options=compact_options,
        ):
            # The turn died before finalize (LLM quota/auth errors,
            # closing-stream failures): persist the just-typed question so it
            # survives a refresh, then let the error surface.
            _abandon_resumed_turn(agent, agent.messages)
            persist_failed_turn(agent, db)
        raise
        raise


async def _stream_waiting_line(agent: "PrepAgent") -> AsyncIterator[str | dict[str, Any]]:
    """Close a dialog-paused turn visually: clear the status line, then stream
    the waiting line. Pop-up events and search cards were already pushed when
    the tool executed, so nothing else is re-emitted here."""
    yield {"type": "status", "text": ""}
    async for piece in slice_stream(agent.pending_reply_text()):
        yield piece


def _finalize_paused_turn(
    agent: "PrepAgent",
    working: list[dict[str, Any]],
    db: Session,
    *,
    tool_steps: list[dict[str, Any]] | None,
    search_groups: list[dict[str, Any]] | None,
    thinking: str,
    compact_threshold: float | None,
    policy: CompactionOptions,
    turn_id: str,
    asked_user: dict[str, Any],
) -> dict[str, Any] | None:
    """Persist a dialog-paused turn (the open call marked for resume).

    Returns the usage-delta event for the stream envelope (or None).
    """
    gate_event = asked_user.get("event")
    ask_event = gate_event if isinstance(gate_event, dict) else None
    return finalize_with_delta(
        agent,
        working,
        agent.pending_reply_text(),
        db,
        tool_steps=tool_steps,
        search_groups=search_groups,
        thinking=thinking,
        compact_threshold=compact_threshold,
        compact_options=policy,
        turn_id=turn_id,
        ask=ask_event,
        pause_event=ask_event,
    )


def _new_content_state() -> dict[str, Any]:
    """Fresh speculative-streaming state (caller-owned; flushed after the loop)."""
    return {
        "streamed": False,
        "status_cleared": False,
        "filtered_text": "",
        "filter": make_display_filter(),
    }


def _take_mid_turn_compaction_report(agent: "PrepAgent") -> dict[str, Any] | None:
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
    agent: "PrepAgent",
    user_text: str,
    db: Session,
    *,
    drop_last_assistant: bool = False,
    ui_locale: str | None = None,
    context_session_ids: list[int] | None = None,
    compact_threshold: float | None = None,
    compact_options: CompactionOptions | None = None,
    memory_index_limit: int | None = None,
) -> AsyncIterator[str | dict[str, Any]]:
    """Think-then-act tool loop (events pushed immediately) → then stream the final answer.

    When the client disconnects (stop button), the partial turn is still
    persisted with ``stopped=True`` instead of being lost.

    Args:
        agent: Live PrepAgent (messages/memory/counters mutated in place).
        user_text: Latest user message content.
        db: Sessions database session (turn persists through it).
        drop_last_assistant: Regenerate support — drop the trailing exchange (reply + question) first.
        ui_locale: UI locale hint for the reply language.
        context_session_ids: Per-turn referenced sessions (transient injection).
        compact_threshold: Auto-compact trigger fraction (None = agent default).
        compact_options: Compaction intensity/directive/retain policy.

    Yields ``str`` (response-body token) or ``dict`` (``status`` / ``thinking`` /
    ``tool_step`` / ``search_results`` / ``ask_user`` / ``usage`` / ``compaction`` events,
    plus ``{"type": "token"}`` payloads streamed live from inside the tool rounds).
    """
    try:
        policy, turn_id, working, pre_build, build_report = await _prepare_turn(
            agent,
            user_text,
            db,
            drop_last_assistant=drop_last_assistant,
            ui_locale=ui_locale,
            context_session_ids=context_session_ids,
            compact_threshold=compact_threshold,
            compact_options=compact_options,
            memory_index_limit=memory_index_limit,
        )
    except Exception:
        # Prepare-window failure after the user message was appended: persist
        # the question so it survives a refresh, then surface the error.
        persist_failed_turn(agent, db)
        raise

    start_event = compaction_event(
        pre_build,
        working,
        build_report,
        context_window=agent.context_window,
        threshold=(
            compact_threshold
            if isinstance(compact_threshold, (int, float)) and 0 < compact_threshold < 1
            else DEFAULT_AUTO_COMPACT_THRESHOLD
        ),
    )
    if start_event is not None:
        yield start_event
    yield {
        "type": "status",
        "text": _THINKING_STATUS.get(ui_locale or "", _THINKING_STATUS_DEFAULT),
    }
    await asyncio.sleep(0)

    # Bounded queue: backpressure when the SSE consumer lags instead of
    # unbounded memory growth on slow connections.
    events: asyncio.Queue = asyncio.Queue(maxsize=_EVENT_QUEUE_MAXSIZE)
    asked_user: dict[str, Any] = {"on": False}
    # The loop runs on its own copy of ``working`` (see run_agent_loop); the
    # out-dict tracks it so a cancel mid-round can still land the pause
    # round's open call — the loop-entry list never sees loop appends.
    loop_working: dict[str, Any] = {}
    # Speculative content-streaming state: one display filter held across rounds
    # so its rules (the display mirror of sanitize_final_reply) apply across chunk and
    # round boundaries; the loop-end flush releases any held-back tail.
    content_state: dict[str, Any] = _new_content_state()
    outcome: dict[str, Any] = {}
    early: str | None = None
    search_groups: list[dict[str, Any]] = []
    tool_steps: list[dict[str, Any]] = []
    thinking: str = ""
    # The loop exports its accumulators only on normal completion, so mirror
    # the streamed thinking/tool events while forwarding them: a stop mid-loop
    # can then still persist what was already produced. (A cancelled round may
    # re-emit a replaced thinking segment; thinking is display-only metadata.)
    streamed_steps: list[dict[str, Any]] = []
    streamed_thinking: list[str] = []
    final: str = ""
    finalized = False
    # False until the loop's outcome lands: before it, the loop's working
    # copy is authoritative; after, the (possibly overflow-replaced) local
    # `working` is.
    loop_done = False
    try:
        async for item in stream_background_events(
            agent._run_tool_rounds,
            outcome,
            events,
            working,
            db,
            asked_user=asked_user,
            content_state=content_state,
            working_out=loop_working,
        ):
            if isinstance(item, dict):
                kind = item.get("type")
                if kind == "thinking":
                    streamed_thinking.append(str(item.get("content") or ""))
                elif kind == "tool_step":
                    streamed_steps.append({k: v for k, v in item.items() if k != "type"})
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
            loop_done = True
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
        mid_event = _take_mid_turn_compaction_report(agent)
        if mid_event is not None:
            yield mid_event

        if asked_user["on"]:
            async for piece in _stream_waiting_line(agent):
                yield piece
            delta = _finalize_paused_turn(
                agent,
                working,
                db,
                tool_steps=tool_steps,
                search_groups=search_groups,
                thinking=thinking,
                compact_threshold=compact_threshold,
                policy=policy,
                turn_id=turn_id,
                asked_user=asked_user,
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
            final, inline_ask = sanitize_final_reply(early)
            if final and not content_state.get("streamed"):
                # Nothing was streamed live (non-streaming LLM fallback): replay in slices.
                async for piece in slice_stream(final):
                    yield piece
            if inline_ask is not None:
                # Promote the inlined question into a real ask_user event (the model put it in text instead of the tool call)
                yield {"type": "ask_user", **inline_ask}
        if not final and inline_ask is None:
            if content_state.get("streamed"):
                # Speculative tokens already reached the user (loop exhausted or
                # failed mid-stream). Regenerating would repeat on screen and
                # fork from persisted history — finish with the streamed text.
                filtered = str(content_state.get("filtered_text") or "")
                final = sanitize_final_reply(filtered)[0].strip()
                if not final:
                    # Streamed text sanitized to nothing: fall through to the
                    # live closing stream below.
                    content_state["streamed"] = False
            if not content_state.get("streamed"):
                # Bottom line: nothing user-visible exists yet (rounds exhausted, LLM
                # exception, or early text sanitized to nothing) — stream a closing
                # answer live instead of ending the turn empty.
                final = ""
                usage_before = agent.usage_snapshot()
                try:
                    async for token in agent.llm.chat_stream(working, temperature=0.7):
                        final += token
                        yield token
                except Exception as e:
                    if not is_context_overflow(e) or final:
                        raise
                    # Overflow before any token: force-compact and retry the final
                    # answer once instead of failing the turn.
                    logger.warning(
                        "Prep stream final overflowed; force-compacting and retrying once"
                    )
                    working = await _force_compact_context(agent, policy, db, context_session_ids)
                    usage_before = agent.usage_snapshot()
                    async for token in agent.llm.chat_stream(working, temperature=0.7):
                        final += token
                        yield token
                agent.note_round_usage(usage_before)
        elif not final:
            # Dialog rescued from an otherwise-empty body: keep the waiting line.
            final = agent.pending_reply_text()
            async for piece in slice_stream(final):
                yield piece

        delta = finalize_with_delta(
            agent,
            working,
            final,
            db,
            tool_steps=tool_steps,
            search_groups=search_groups,
            thinking=thinking,
            compact_threshold=compact_threshold,
            compact_options=policy,
            turn_id=turn_id,
        )
        finalized = True
        if delta:
            yield delta
        # End-of-turn curation runs detached after the completion envelope: the
        # done event is no longer delayed by the advisory LLM call, and a client
        # disconnect after the last token cannot cancel it anymore.
        schedule_turn_memory_precipitation(agent, user_text, final)
    except (asyncio.CancelledError, GeneratorExit):
        # Client stopped the stream: persist the partial turn so the question
        # and whatever was produced survive a refresh. Never yield here, and
        # never let a persistence failure mask the cancellation itself.
        # Note: the blocking commit is intentional here — the turn must land
        # before the generator closes, or the question is lost on refresh.
        if not finalized:
            gate_event = asked_user.get("event")
            ask_event = gate_event if isinstance(gate_event, dict) else None
            # After the loop returns, the local `working` is authoritative
            # (the closing overflow path may have replaced it with a
            # force-compacted list); mid-loop, the loop's copy is — the
            # dialog round's open call exists only there.
            context = working if loop_done else (loop_working.get("working") or working)
            if not context:
                # Defensive: the stream cannot reach the cancel handler
                # before prepare produced a working list (prepare failures
                # re-raise past the main try), so an empty context means an
                # unexpected state — persisting one would clobber the whole
                # session history with a bare reply row.
                logger.error("Prep cancel persist skipped: empty working list")
                raise
            delivered = not events or bool(asked_user.get("emitted"))
            if not delivered:
                # The dialog event never reached the queue (client gone while
                # the bounded put was blocked): the user has seen nothing, so
                # no resume marker is persisted — the round's declarations
                # (including the undelivered dialog call) are completed as
                # interrupted instead, and the next input runs a fresh turn.
                ask_event = None
                complete_interrupted_tool_calls(context)
            if ask_event is None:
                # A resume turn cancelled before its dialog fired must not
                # persist the consumed pointer: roll back to the pause
                # snapshot so the answer can still resume on retry.
                _abandon_resumed_turn(agent, context)
            persist_cancel(
                agent,
                context,
                final,
                content_state,
                db,
                tool_steps=tool_steps or streamed_steps,
                search_groups=search_groups,
                thinking=thinking or "".join(streamed_thinking),
                compact_threshold=compact_threshold,
                compact_options=policy,
                turn_id=turn_id,
                ask=ask_event,
                # mark_paused_ask tolerates non-dict payloads; a dialog that
                # never fired leaves ask_event None and nothing is marked.
                pause_event=ask_event,
            )
        raise
    except Exception:
        if finalized:
            # finalize already landed the turn: nothing to roll back or
            # re-persist for exceptions raised after the commit.
            raise
        if not _persist_failure_state(
            agent,
            asked_user,
            loop_working,
            working,
            turn_id,
            policy,
            db,
            compact_threshold=compact_threshold,
            compact_options=compact_options,
            tool_steps=tool_steps or streamed_steps,
            search_groups=search_groups,
            thinking=thinking or "".join(streamed_thinking),
        ):
            # The turn died before finalize (LLM quota/auth errors,
            # closing-stream failures): persist the just-typed question so it
            # survives a refresh, then let the route render the error event.
            _abandon_resumed_turn(agent, agent.messages)
            persist_failed_turn(agent, db)
        raise


__all__ = [
    "compaction_event",
    "finalize",
    "sanitize_final_reply",
    "run_chat",
    "run_chat_stream",
    "usage_event",
]
