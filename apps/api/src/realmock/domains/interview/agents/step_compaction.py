"""Step-boundary compaction state machine (the interview's checkpoint layer).

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
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import weakref
from typing import TYPE_CHECKING, Any

from realmock.domains.interview.agents.agent_policies import COMPACT
from realmock.domains.interview.agents.memory.cognitive_graph import CompetencyStatus
from realmock.domains.interview.agents.step_compaction_prompts import (
    STEP_ROLLUP_PROMPT,
    STEP_SUMMARY_PROMPT,
)
from realmock.platform.capabilities.ai.context.estimation import estimate_messages_tokens

if TYPE_CHECKING:
    from realmock.domains.interview.agents.session_state import InterviewSessionState

logger = logging.getLogger(__name__)

_STATE_KEY = "steps"

_SUMMARY_KEYS = (
    "topics",
    "evidence",
    "verified",
    "suspicious",
    "weak_points",
    "agreed_facts",
    "probes_pending",
)


def _steps_state(agent: "InterviewSessionState") -> dict[str, Any]:
    return agent.agent_state.setdefault(
        _STATE_KEY, {"step_start": 1, "step_no": 1, "summaries": []}
    )


def record_step_boundary(
    agent: "InterviewSessionState", *, end: int | None = None
) -> dict[str, Any] | None:
    """Close the current step segment; returns the boundary descriptor.

    Called by the turn flow right after the state machine advanced a step.
    ``end`` pins the segment's exclusive end index for callers that must
    exclude messages appended after the close (a phase advance appends the
    NEXT step's entry message, which belongs to the new segment, not this
    one). ``None`` as ``end`` means "everything appended so far".
    The return ``None`` means there was nothing to close (empty segment).
    """
    steps = _steps_state(agent)
    # Clamp a stale start (e.g. state written before an external history
    # rewrite) so the boundary can never span past the real list.
    start = min(int(steps.get("step_start", 1)), len(agent.messages))
    if end is None:
        end = len(agent.messages)
    else:
        end = min(int(end), len(agent.messages))
    boundary = {
        "start": start,
        "end": end,
        "step_no": int(steps.get("step_no", 1)),
        "phase_id": str(getattr(agent.session, "current_phase", "") or ""),
    }
    if end <= start:
        return None
    steps["step_start"] = end
    steps["step_no"] = int(steps.get("step_no", 1)) + 1
    # Queue the descriptor: the spawned task re-reads it under the compaction
    # lock, because an earlier boundary's splice may shift indexes between
    # record time and run time (the lock serializes runs, not captures).
    steps.setdefault("pending", []).append(dict(boundary))
    agent.agent_state[_STATE_KEY] = steps
    return boundary


def _render_transcript(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for m in messages:
        role = m.get("role")
        if role not in ("user", "assistant", "system"):
            continue
        content = m.get("content")
        text = content if isinstance(content, str) else _json_dumps(content)
        lines.append(f"[{role}] {text}")
    return "\n".join(lines)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _parse_summary(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not raw:
        return None
    if not any(isinstance(raw.get(k), list) and raw.get(k) for k in _SUMMARY_KEYS):
        return None  # empty/garbage summary counts as a failure
    return raw


def _render_summary_block(step_no: int, summary: dict[str, Any]) -> str:
    def _items(key: str) -> str:
        value = summary.get(key) or []
        if isinstance(value, list):
            return "; ".join(_render_item(v) for v in value)
        return str(value)

    def _render_item(v: Any) -> str:
        if isinstance(v, dict):
            return _json_dumps(v)
        return str(v)

    lines = [f"## Step {step_no} summary (closed step briefing — do not repeat its questions)"]
    if summary.get("topics"):
        lines.append("Topics asked: " + _items("topics"))
    evidence = summary.get("evidence") or []
    if isinstance(evidence, list) and evidence:
        lines.append("Evidence:")
        for e in evidence:
            lines.append(f"  - {_json_dumps(e)}")
    for key, label in (
        ("verified", "Verified strengths"),
        ("suspicious", "Suspicious claims"),
        ("weak_points", "Weak points"),
        ("agreed_facts", "Agreed facts"),
        ("probes_pending", "Pending probes"),
    ):
        if summary.get(key):
            lines.append(f"{label}: {_items(key)}")
    if summary.get("pacing_note"):
        lines.append(f"Pacing note: {summary['pacing_note']}")
    return "\n".join(lines)


async def _summarize_call(llm: Any, transcript: str, focus: str) -> dict[str, Any] | None:
    raw = await llm.chat_json(
        [
            {"role": "system", "content": STEP_SUMMARY_PROMPT},
            {
                "role": "user",
                "content": (
                    (f"Step focus: {focus}\n" if focus else "") + f"Step transcript:\n{transcript}"
                ),
            },
        ],
        temperature=0.2,
    )
    return _parse_summary(raw)


def _apply_reflections(agent: "InterviewSessionState", summary: dict[str, Any]) -> None:
    """Record the summary's competency reflections into the cognitive graph.

    The structured brief carries a ``reflections`` list, so the per-step
    judgment rides the same call as the compaction instead of a separate
    periodic agent pass.
    """
    for ref in summary.get("reflections") or []:
        if not isinstance(ref, dict):
            continue
        topic = str(ref.get("topic", "")).strip()
        status = str(ref.get("status", "untested")).lower()
        if not topic or status not in {"verified", "suspicious", "failed", "untested"}:
            continue
        try:
            confidence = float(ref.get("confidence", 0.8))
        except (TypeError, ValueError):
            confidence = 0.8
        status_enum = (
            CompetencyStatus(status)
            if status in {s.value for s in CompetencyStatus}
            else CompetencyStatus.UNTESTED
        )
        agent.cognitive_memory.record_finding(
            topic=topic,
            category=str(ref.get("category", "general")),
            status=status_enum,
            claim=str(ref.get("claim", "")),
            finding=str(ref.get("finding", "")),
            turn_index=int(_steps_turn_index(agent)),
            confidence=confidence,
        )


def _steps_turn_index(agent: "InterviewSessionState") -> int:
    return len(agent.agent_state.get("asked_questions", []))


def _rollup_needed(agent: "InterviewSessionState") -> bool:
    steps = agent.agent_state.get(_STATE_KEY, {})
    summaries = [s for s in steps.get("summaries", []) if isinstance(s, dict)]
    if len(summaries) <= COMPACT.keep_recent_summaries:
        return False
    mass = sum(int(s.get("tokens", 0)) for s in summaries)
    return mass > COMPACT.rollup_token_threshold or len(summaries) > COMPACT.rollup_count_threshold


async def _rollup(llm: Any, agent: "InterviewSessionState") -> None:
    steps = agent.agent_state[_STATE_KEY]
    summaries: list[dict[str, Any]] = steps.get("summaries", [])
    keep = COMPACT.keep_recent_summaries
    retiring = summaries[:-keep] if len(summaries) > keep else []
    if not retiring:
        return
    existing = str(steps.get("interview_summary", "") or "")
    try:
        merged = await llm.chat(
            [
                {"role": "system", "content": STEP_ROLLUP_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Existing digest:\n{existing or '(empty — first merge)'}\n\n"
                        "Old step briefings to merge:\n"
                        + "\n\n".join(str(s.get("rendered", "")) for s in retiring)
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=2000,
        )
    except Exception as e:
        logger.debug("step rollup call failed; deferring: %s", e)
        return
    text = str(merged or "").strip()
    if not text:
        return
    steps["interview_summary"] = text
    steps["summaries"] = summaries[-keep:]
    steps["retired_count"] = int(steps.get("retired_count", 0)) + len(retiring)
    logger.info(
        "step summaries rolled up: retired=%d kept=%d", len(retiring), len(steps["summaries"])
    )


def _already_spliced(agent: "InterviewSessionState", boundary: dict[str, Any]) -> bool:
    """True when this boundary's raw segment was already replaced by its brief.

    Guards the failure bookkeeping against double-booking a range whose splice
    DID land (e.g. the budget expired during the post-splice rollup): re-filing
    a compacted range would make the next merge swallow the brief plus the next
    step's live dialogue and overwrite them — destructive, so it must never
    happen. The segment is identified by the rendered brief header, which is
    derived from the same descriptor that drove the splice.
    """
    start = int(boundary.get("start", -1))
    if start < 0 or start >= len(agent.messages):
        return True  # nothing left at that position — nothing to retry
    message = agent.messages[start]
    if not isinstance(message, dict) or message.get("role") != "system":
        return False
    return f"## Step {int(boundary.get('step_no', 0))} summary" in str(message.get("content", ""))


def _record_failed_boundary(agent: "InterviewSessionState", boundary: dict[str, Any]) -> None:
    """Book an uncompacted segment for the accumulate-and-retry chain.

    Replaces the failed entries the boundary's range already covers (each
    retry merges them into one range) and counts the round; after
    :data:`COMPACT.max_failed_rounds` failed rounds the segment is
    dead-lettered — the raw dialogue stays verbatim and the chain stops — so a
    permanently failing summary call can neither retry forever nor grow the
    merged input without bound.
    """
    if _already_spliced(agent, boundary):
        return
    start = int(boundary.get("start", -1))
    end = int(boundary.get("end", -1))
    if end <= start:
        return
    failed = [f for f in agent.agent_state.get("failed_steps", []) if isinstance(f, dict)]
    covered = [
        f
        for f in failed
        if int(f.get("start", -1)) >= start and int(f.get("end", -1)) <= end
    ]
    rest = [f for f in failed if f not in covered]
    rounds = max((int(f.get("rounds", 0)) for f in covered), default=0) + 1
    if rounds > COMPACT.max_failed_rounds:
        agent.agent_state["failed_steps"] = rest
        logger.warning(
            "step compaction gave up on segment [%d,%d) after %d failed rounds; "
            "raw dialogue stays verbatim",
            start,
            end,
            rounds - 1,
        )
        return
    entry = dict(boundary)
    entry["rounds"] = rounds
    agent.agent_state["failed_steps"] = rest + [entry]


def _shift_tracked_indexes(
    agent: "InterviewSessionState", steps: dict[str, Any], end: int, delta: int
) -> None:
    """Shift every tracked index right of ``end`` left by ``delta`` after a splice.

    The splice removed ``delta`` messages: stale indexes would make the next
    boundary read out-of-range positions and the state machine silently die.
    ``steps`` is the live "steps" state; ``failed_steps`` lives on agent_state.
    """
    if delta <= 0:
        return
    if int(steps.get("step_start", 0)) >= end:
        steps["step_start"] = int(steps["step_start"]) - delta
    for tracked in (
        steps.get("summaries", []),
        agent.agent_state.get("failed_steps", []),
        steps.get("pending", []),
    ):
        for item in tracked:
            if int(item.get("start", 0)) >= end:
                item["start"] = int(item["start"]) - delta
                item["end"] = int(item["end"]) - delta


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
    steps = agent.agent_state.setdefault(
        _STATE_KEY, {"step_start": 1, "step_no": 1, "summaries": []}
    )
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

    transcript = _render_transcript(segment)
    focus = str(boundary.get("phase_id", ""))
    summary: dict[str, Any] | None = None
    for attempt in range(COMPACT.max_attempts):
        delay = COMPACT.retry_delays[attempt] if attempt < len(COMPACT.retry_delays) else 0.0
        if delay:
            await asyncio.sleep(delay)
        try:
            summary = await _summarize_call(llm, transcript, focus)
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
        _record_failed_boundary(agent, boundary)
        logger.warning(
            "step %s compaction failed after %d attempts; raw kept",
            boundary.get("step_no"),
            COMPACT.max_attempts,
        )
        return False

    _apply_reflections(agent, summary)
    rendered = _render_summary_block(int(boundary.get("step_no", 0)), summary)
    block = {"role": "system", "content": rendered}
    # In-place slice replacement: appends made after the boundary (the next
    # step may already be running) sit beyond `end` and are never touched.
    now = time.time()
    agent.messages[start:end] = [block]
    # The splice removed (end-start-1) messages: every tracked index right of
    # `end` must shift left by the same delta or the next boundary reads
    # out-of-range positions and the state machine silently dies.
    delta = (end - start) - 1
    _shift_tracked_indexes(agent, steps, end, delta)
    summaries = [
        s
        for s in agent.agent_state.setdefault(_STATE_KEY, {}).get("summaries", [])
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
    agent.agent_state.setdefault(_STATE_KEY, {})["summaries"] = summaries
    # Previously failed segments that overlapped this boundary are now covered.
    failed = [
        f
        for f in agent.agent_state.get("failed_steps", [])
        if not (int(f.get("start", -1)) >= start and int(f.get("end", -1)) <= end)
    ]
    agent.agent_state["failed_steps"] = failed

    if _rollup_needed(agent):
        await _rollup(llm, agent)
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
    :func:`_take_pending_boundary`); this merges the failed-chain entries.
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


def _take_pending_boundary(
    agent: "InterviewSessionState", fallback: dict[str, Any]
) -> dict[str, Any]:
    """Pop the oldest queued boundary (FIFO: spawn order == lock order).

    The descriptor captured at record time can be stale — an earlier
    compaction may have spliced messages in between; the queued copy is
    shifted together with every other tracked index, so it is the truth.
    """
    steps = agent.agent_state.get(_STATE_KEY, {})
    pending = steps.get("pending")
    if isinstance(pending, list) and pending:
        first = pending.pop(0)
        if isinstance(first, dict):
            return first
    return fallback


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


async def _persist_after_flow_idle(
    runner: Any, agent: "InterviewSessionState"
) -> None:
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
                current = _take_pending_boundary(agent, boundary)
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
                    _record_failed_boundary(agent, current)
            except asyncio.CancelledError:
                # WS disconnect / teardown: re-file an unconsumed boundary so
                # the segment is not lost with the task (the finally below
                # persists the bookkeeping even when no further turn comes).
                if popped:
                    _record_failed_boundary(agent, current)
                raise
            except Exception:
                logger.debug("step compaction crashed; raw kept", exc_info=True)
                if popped:
                    _record_failed_boundary(agent, current)
            finally:
                await _persist_after_flow_idle(runner, agent)

    return runner.spawn_bg_task(_run())
