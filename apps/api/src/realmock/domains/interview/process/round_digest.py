"""Round digest builder: summarize a finished session into process-memory form.

Rule-based on purpose: runs synchronously inside the finish lifecycle, so it
must never make LLM calls. Inputs are the structured memories the interviewer
agent already maintains (asked questions, weak points, turn scores) plus the
frozen ledger for phase coverage.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from realmock.domains.interview.process.process_memory import _DIGEST_LIMITS

logger = logging.getLogger(__name__)


def _load_agent_state(session: Any) -> dict[str, Any]:
    try:
        state = json.loads(getattr(session, "agent_state", None) or "{}")
    except (json.JSONDecodeError, TypeError):
        logger.debug("corrupt agent_state JSON; digest from defaults")
        return {}
    return state if isinstance(state, dict) else {}


def _phase_coverage(ledger: dict[str, Any] | None) -> list[str]:
    """Ordered unique phase ids visited by ledger turns."""
    if not isinstance(ledger, dict):
        return []
    seen: list[str] = []
    for turn in ledger.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        phase = str(turn.get("phase") or "").strip()
        if phase and phase not in seen:
            seen.append(phase)
    return seen


def build_round_digest(session: Any, ledger: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the per-round digest document for process memory."""
    state = _load_agent_state(session)
    topics = [str(t).strip() for t in state.get("asked_questions") or [] if str(t).strip()]
    weak = [str(w).strip() for w in state.get("weak_points") or [] if str(w).strip()]
    strengths: list[str] = []
    last_score = state.get("last_turn_score")
    if isinstance(last_score, dict):
        brief = str(last_score.get("brief") or "").strip()
        if brief and (last_score.get("rating") or 0) >= 4:
            strengths.append(brief)

    phases = _phase_coverage(ledger)
    result = getattr(session, "result", None)
    round_no = getattr(session, "round_no", None)
    summary = (
        f"Round {round_no}: verdict={result or 'unjudged'}; "
        f"{len(topics)} questions asked across phases [{', '.join(phases[:8])}]"
    )

    return {
        "summary": summary[:_DIGEST_LIMITS["summary_chars"]],
        "topics_covered": topics[: _DIGEST_LIMITS["topics"]],
        "weak_points": weak[: _DIGEST_LIMITS["weak_points"]],
        "strengths": strengths[: _DIGEST_LIMITS["strengths"]],
        "phases_covered": phases[: 16],
    }


__all__ = ["build_round_digest"]
