"""Step-compaction bookkeeping: boundary capture, the pending queue, the
failed-retry chain, and tracked-index arithmetic.

Pure state layer: everything here operates on ``agent_state`` dicts and
message-list *indexes* — no LLM, no I/O, no concurrency. The content layer
(transcript → brief) lives in :mod:`step_compaction_summary`; the core
operation and its orchestration live in :mod:`step_compaction`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from realmock.domains.interview.agents.agent_policies import COMPACT

if TYPE_CHECKING:
    from realmock.domains.interview.agents.session_state import InterviewSessionState

logger = logging.getLogger(__name__)

_STATE_KEY = "steps"


def steps_state(agent: "InterviewSessionState") -> dict[str, Any]:
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
    steps = steps_state(agent)
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


def take_pending_boundary(
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


def already_spliced(agent: "InterviewSessionState", boundary: dict[str, Any]) -> bool:
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


def record_failed_boundary(agent: "InterviewSessionState", boundary: dict[str, Any]) -> None:
    """Book an uncompacted segment for the accumulate-and-retry chain.

    Replaces the failed entries the boundary's range already covers (each
    retry merges them into one range) and counts the round; after
    :data:`COMPACT.max_failed_rounds` failed rounds the segment is
    dead-lettered — the raw dialogue stays verbatim and the chain stops — so a
    permanently failing summary call can neither retry forever nor grow the
    merged input without bound.
    """
    if already_spliced(agent, boundary):
        return
    start = int(boundary.get("start", -1))
    end = int(boundary.get("end", -1))
    if end <= start:
        return
    failed = [f for f in agent.agent_state.get("failed_steps", []) if isinstance(f, dict)]
    covered = [
        f for f in failed if int(f.get("start", -1)) >= start and int(f.get("end", -1)) <= end
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


def shift_tracked_indexes(
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


def rollup_needed(agent: "InterviewSessionState") -> bool:
    steps = agent.agent_state.get(_STATE_KEY, {})
    summaries = [s for s in steps.get("summaries", []) if isinstance(s, dict)]
    if len(summaries) <= COMPACT.keep_recent_summaries:
        return False
    mass = sum(int(s.get("tokens", 0)) for s in summaries)
    return mass > COMPACT.rollup_token_threshold or len(summaries) > COMPACT.rollup_count_threshold
