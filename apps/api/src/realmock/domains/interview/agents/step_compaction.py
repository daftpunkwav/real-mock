"""Step-boundary compaction core operation and orchestration.

Pacing sovereignty: the interviewer decides when a step is done
(``phase_complete``). When the state machine advances a step it records a
*boundary*; this module then — fully in the background — converts the closed
step's verbatim dialogue into a structured briefing and splices it into
``agent.messages`` in place of the raw segment.

Design contract:

- compression protects attention, it never merely saves space: full
  transcript in, structured brief out, nothing silently dropped;
- a step at or under :data:`COMPACT.skip_below_tokens` stays verbatim;
- LLM failure retries up to three times with backoff, then the raw segment
  stays and is folded into the NEXT boundary's attempt (accumulate-and-retry);
  the chain terminates: after ``COMPACT.max_failed_rounds`` failed rounds the
  segment is dead-lettered (raw kept verbatim) instead of retrying forever;
- a task that dies around the compaction (budget overrun, crash, WS-disconnect
  cancellation) hands its boundary back to the same chain — an uncompacted
  segment is never silently dropped;
- replacement is an in-place slice assignment so appends made by a turn that
  started meanwhile are never lost;
- once more than ``keep_recent_summaries`` briefings pile up (or their token
  mass crosses the rollup threshold), the oldest ones are merged into one
  running digest via a rollup call; rollup failure is deferred, never destructive;
- the ledger keeps every turn verbatim regardless of what happens here.

Layering: boundary bookkeeping and index arithmetic live in
:mod:`step_compaction_state`, the transcript→brief content calls in
:mod:`step_compaction_summary`; this module owns the splice itself plus the
concurrency (per-runner lock) and durability (idle-gated persist) wrappers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import weakref
from typing import TYPE_CHECKING, Any

from realmock.domains.interview.agents.agent_policies import COMPACT
from realmock.domains.interview.agents.step_compaction_state import (
    record_failed_boundary,
    rollup_needed,
    shift_tracked_indexes,
    steps_state,
    take_pending_boundary,
)
from realmock.domains.interview.agents.step_compaction_summary import (
    apply_reflections,
    render_summary_block,
    render_transcript,
    rollup,
    summarize_call,
)
from realmock.platform.capabilities.ai.context.estimation import estimate_messages_tokens

if TYPE_CHECKING:
    from realmock.domains.interview.agents.session_state import InterviewSessionState

logger = logging.getLogger(__name__)


async def compact_step_boundary(
    agent: "InterviewSessionState",
    boundary: dict[str, Any],
    *,
    llm: Any,
) -> bool:
    """Summarize one closed step and splice the brief into history.

    Returns True when the segment was replaced by a summary block. Never
    raises: every failure path keeps the raw dialogue and records state for
    the next boundary.
    """
    steps = steps_state(agent)
    start = int(boundary["start"])
    end = int(boundary["end"])
    end = min(end, len(agent.messages))
    if end <= start:
        return False

    segment = list(agent.messages[start:end])
    try:
        tokens = estimate_messages_tokens(segment)
    except Exception:
        tokens = -1
    if 0 <= tokens <= COMPACT.skip_below_tokens:
        logger.info(
            "step %s compaction skipped (small, ~%s tokens)", boundary.get("step_no"), tokens
        )
        return False

    transcript = render_transcript(segment)
    focus = str(boundary.get("phase_id", ""))
    summary: dict[str, Any] | None = None
    for attempt in range(COMPACT.max_attempts):
        delay = COMPACT.retry_delays[attempt] if attempt < len(COMPACT.retry_delays) else 0.0
        if delay:
            await asyncio.sleep(delay)
        try:
            summary = await summarize_call(llm, transcript, focus)
        except Exception as e:
            logger.warning(
                "step %s summary attempt %d failed: %s", boundary.get("step_no"), attempt + 1, e
            )
            summary = None
        if summary is not None:
            break
    if summary is None:
        # Fall back: keep the raw dialogue; the next boundary retries with
        # this segment folded in (accumulate-and-retry, bounded rounds).
        record_failed_boundary(agent, boundary)
        logger.warning(
            "step %s compaction failed after %d attempts; raw kept",
            boundary.get("step_no"),
            COMPACT.max_attempts,
        )
        return False

    apply_reflections(agent, summary)
    rendered = render_summary_block(int(boundary.get("step_no", 0)), summary)
    block = {"role": "system", "content": rendered}
    # In-place slice replacement: appends made after the boundary (the next
    # step may already be running) sit beyond `end` and are never touched.
    now = time.time()
    agent.messages[start:end] = [block]
    # The splice removed (end-start-1) messages: every tracked index right of
    # `end` must shift left by the same delta or the next boundary reads
    # out-of-range positions and the state machine silently dies.
    delta = (end - start) - 1
    shift_tracked_indexes(agent, steps, end, delta)
    summaries = [
        s
        for s in steps.get("summaries", [])
        if not (s.get("start") == start and s.get("end") == end)
    ]
    summaries.append(
        {
            "step_no": boundary.get("step_no"),
            "phase_id": boundary.get("phase_id"),
            "start": start,
            "end": start + 1,
            "rendered": rendered,
            "tokens": max(1, len(rendered) // 3),
            "at": now,
        }
    )
    steps["summaries"] = summaries
    # Previously failed segments that overlapped this boundary are now covered.
    failed = [
        f
        for f in agent.agent_state.get("failed_steps", [])
        if not (int(f.get("start", -1)) >= start and int(f.get("end", -1)) <= end)
    ]
    agent.agent_state["failed_steps"] = failed

    if rollup_needed(agent):
        await rollup(llm, agent)
    return True


async def compact_accumulated_boundaries(
    agent: "InterviewSessionState",
    boundary: dict[str, Any],
    *,
    llm: Any,
) -> bool:
    """Compact previously failed segments plus the new boundary in one pass.

    The accumulated (previously failed) segments sit contiguously before the
    new step's segment; they are summarized together so accumulate-and-retry
    stays a single call. Distinct from the ``steps["pending"]`` queue: that
    one holds captured-but-not-yet-run descriptors (see
    :func:`step_compaction_state.take_pending_boundary`); this merges the
    failed-chain entries.
    """
    failed: list[dict[str, Any]] = agent.agent_state.get("failed_steps", [])
    if not failed:
        return await compact_step_boundary(agent, boundary, llm=llm)
    first = min(int(f.get("start", boundary["start"])) for f in failed)
    merged = {
        "start": min(first, int(boundary["start"])),
        "end": int(boundary["end"]),
        "step_no": boundary.get("step_no"),
        "phase_id": boundary.get("phase_id"),
    }
    ok = await compact_step_boundary(agent, merged, llm=llm)
    return ok


# One compaction at a time per runner: a second boundary landing while the
# first task is still running would otherwise summarize against indexes the
# first task is about to shift.
_COMPACTION_LOCKS: "weakref.WeakKeyDictionary[Any, asyncio.Lock]" = weakref.WeakKeyDictionary()


def _compaction_lock_for(runner: Any) -> asyncio.Lock:
    try:
        lock = _COMPACTION_LOCKS.get(runner)
    except TypeError:
        lock = None
    if lock is None:
        lock = asyncio.Lock()
        try:
            _COMPACTION_LOCKS[runner] = lock
        except TypeError:
            pass
    return lock


#: How long the persist step waits for the interview flow to go idle before
#: giving up (the flow's own ``save_state`` then persists the snapshot).
_PERSIST_IDLE_WAIT_SEC = 15.0


def _write_snapshot(sid: int, agent: "InterviewSessionState") -> None:
    """Write agent_state+messages onto the session row by id.

    The in-memory session ORM object is detached here, so write a fresh row
    looked up by id instead of mutating the stale one.
    """
    from realmock.domains.interview.models import InterviewSession
    from realmock.platform.database import sessions_db_session

    with sessions_db_session() as db:
        row = db.get(InterviewSession, sid)
        if row is None:
            return
        row.agent_state = json.dumps(agent.agent_state, ensure_ascii=False)
        row.messages = json.dumps(agent.messages, ensure_ascii=False)
        db.commit()


async def _persist_after_flow_idle(runner: Any, agent: "InterviewSessionState") -> None:
    """Best-effort persistence so the compaction survives even if no further
    turn comes.

    Only persist against an idle flow. The turn's own ``save_state`` serializes
    and commits synchronously on the event loop; this persist must not
    interleave with it (a commit landing between this snapshot's serialize and
    its commit would let a stale snapshot overwrite that turn's freshly saved
    state). Waiting out the active turn, then running serialize+commit
    synchronously on the loop, makes the two writers mutually exclusive by
    construction. If the flow stays busy, skipping is safe: the flow's own
    ``save_state`` persists everything this task changed.
    """
    sid = getattr(agent.session, "id", None)
    if sid is None:
        return
    waited = 0.0
    while getattr(runner, "flow_active", False) and waited < _PERSIST_IDLE_WAIT_SEC:
        await asyncio.sleep(0.25)
        waited += 0.25
    if getattr(runner, "flow_active", False):
        logger.debug(
            "step compaction persist skipped; interview flow still active sid=%s",
            sid,
        )
        return
    try:
        _write_snapshot(sid, agent)
    except Exception:
        logger.debug("step compaction persist failed", exc_info=True)


def spawn_boundary_compaction(
    runner: Any,
    boundary: dict[str, Any],
) -> "asyncio.Task[None]":
    """Fire the background compaction task (never blocks the reply).

    Returns the spawned task so callers (tests, teardown) can await or cancel
    it explicitly.
    """
    agent = runner.agent
    llm = runner.llm
    lock = _compaction_lock_for(runner)

    async def _run() -> None:
        popped = False
        current = boundary
        async with lock:
            try:
                # Re-read under the lock: the queued copy carries any index
                # shifts that landed while this task waited its turn.
                current = take_pending_boundary(agent, boundary)
                popped = True
                await asyncio.wait_for(
                    compact_accumulated_boundaries(agent, current, llm=llm),
                    timeout=COMPACT.budget_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "step compaction overran its budget sid=%s step=%s",
                    getattr(agent.session, "id", None),
                    boundary.get("step_no"),
                )
                if popped:
                    # The boundary was consumed but the compaction did not
                    # finish: hand it back so the next boundary retries it.
                    record_failed_boundary(agent, current)
            except asyncio.CancelledError:
                # WS disconnect / teardown: re-file an unconsumed boundary so
                # the segment is not lost with the task (the finally below
                # persists the bookkeeping even when no further turn comes).
                if popped:
                    record_failed_boundary(agent, current)
                raise
            except Exception:
                logger.debug("step compaction crashed; raw kept", exc_info=True)
                if popped:
                    record_failed_boundary(agent, current)
            finally:
                await _persist_after_flow_idle(runner, agent)

    return runner.spawn_bg_task(_run())
