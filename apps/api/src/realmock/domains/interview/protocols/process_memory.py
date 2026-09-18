"""Process long-term memory document (realmock.process_memory.v1).

One JSON document per ``interview_processes.memory`` row: per-round digests
written when a round finishes, consumed by the planner and the interviewer
prompt as cross-round memory. Pure document logic lives here; DB access stays
with callers.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

MEMORY_SCHEMA = "realmock.process_memory.v1"

DIGEST_LIMITS = {
    # Questions asked per round feed the next round's anti-repeat list; a
    # 30+ question round truncated to 12 left the interviewer blind to most
    # of what was already covered, so repeats slipped through.
    "topics": 20,
    "weak_points": 8,
    "strengths": 6,
    "summary_chars": 400,
}


def empty_memory() -> dict[str, Any]:
    """Return a fresh memory document."""
    return {"schema": MEMORY_SCHEMA, "rounds": [], "final": None}


def load_memory(raw: str | None) -> dict[str, Any]:
    """Parse the stored JSON; corrupt payloads degrade to an empty document."""
    if not raw:
        return empty_memory()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("corrupt process memory JSON; starting fresh")
        return empty_memory()
    if not isinstance(data, dict):
        return empty_memory()
    data.setdefault("schema", MEMORY_SCHEMA)
    if not isinstance(data.get("rounds"), list):
        data["rounds"] = []
    data.setdefault("final", None)
    return data


def dump_memory(memory: dict[str, Any]) -> str:
    """Serialize the memory document for storage."""
    return json.dumps(memory, ensure_ascii=False)


def append_round(
    memory: dict[str, Any],
    *,
    round_no: int,
    session_id: int,
    result: str | None,
    digest: dict[str, Any] | None,
) -> None:
    """Insert or replace the entry for one round (idempotent per round_no)."""
    entry: dict[str, Any] = {
        "round_no": int(round_no),
        "session_id": int(session_id),
        "result": result,
        "digest": digest or {},
    }
    rounds = [r for r in memory.get("rounds", []) if r.get("round_no") != round_no]
    rounds.append(entry)
    rounds.sort(key=lambda r: r.get("round_no", 0))
    memory["rounds"] = rounds


def mark_final(memory: dict[str, Any], *, result: str, rounds_completed: int) -> None:
    """Record the terminal outcome of the whole process."""
    memory["final"] = {"result": result, "rounds_completed": int(rounds_completed)}


def render_for_prompt(memory: dict[str, Any] | None) -> str:
    """Render prior-round digests as a compact prompt block (empty when no rounds).

    Returns an empty string when no rounds have been recorded yet.
    """
    if not memory:
        return ""
    rounds = [r for r in memory.get("rounds", []) if isinstance(r, dict)]
    if not rounds:
        return ""
    lines: list[str] = []
    for r in rounds[-DIGEST_LIMITS["topics"]:]:
        digest = r.get("digest") or {}
        head = f"- Round {r.get('round_no')}: result={r.get('result') or 'unjudged'}"
        summary = (digest.get("summary") or "").strip()
        if summary:
            head += f"; {summary[:DIGEST_LIMITS['summary_chars']]}"
        lines.append(head)
        topics = digest.get("topics_covered") or []
        if topics:
            lines.append(f"  Topics covered: {'; '.join(str(t) for t in topics[:DIGEST_LIMITS['topics']])}")
        weak = digest.get("weak_points") or []
        if weak:
            lines.append(f"  Candidate weak points: {'; '.join(str(w) for w in weak[:DIGEST_LIMITS['weak_points']])}")
        strong = digest.get("strengths") or []
        if strong:
            lines.append(f"  Candidate strengths: {'; '.join(str(s) for s in strong[:DIGEST_LIMITS['strengths']])}")
    final = memory.get("final")
    if final:
        lines.append(f"Process final outcome: {final}")
    return "\n".join(lines)


__all__ = [
    "DIGEST_LIMITS",
    "MEMORY_SCHEMA",
    "append_round",
    "dump_memory",
    "empty_memory",
    "load_memory",
    "mark_final",
    "render_for_prompt",
]
