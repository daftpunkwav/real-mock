"""Follow-up signal analysis + this turn's transient guidance blocks.

Single responsibility: analyze the follow-up signal against the candidate's
reply and collect the system messages that guide THIS call only. The blocks
are transient — they concern this one answer, so persisting them would resurface
stale guidance every later turn (until a step boundary folded it away) and
grow the history linearly. Facts the interviewer should keep (weak points,
follow-up clue categories) still land in agent_state for the memory section
and the growth learning loop.
"""

from __future__ import annotations

import logging
from typing import Any

from realmock.domains.interview.agents.session_state import InterviewSessionState
from realmock.domains.interview.agents.followup import analyze as analyze_followup

logger = logging.getLogger(__name__)


def build_turn_guidance(
    state: InterviewSessionState,
    *,
    user_text: str,
    last_question: str,
    tech_domains: list[str],
    phase_id: str,
    rag_msg: dict[str, Any] | None,
    session_id: int,
    pending_probe: str | None = None,
) -> list[dict[str, Any]]:
    """Analyze the reply and return this turn's guidance blocks (not persisted).

    Returns system messages for the current LLM call only: the follow-up
    directive (when the signal fires) and the RAG company-knowledge block
    (when retrieval hit). The caller appends them to the transient call tail.
    """
    blocks: list[dict[str, Any]] = []
    signal = analyze_followup(
        user_text,
        question=last_question,
        tech_domains=tech_domains,
        phase_id=phase_id,
        pending_probe=pending_probe,
    )
    if signal.needs_followup:
        blocks.append(
            {
                "role": "system",
                "content": f"[Follow-up guidance: {signal.category}] {signal.suggested_probe}",
            }
        )
        # The guidance wording is an examiner instruction, not a candidate
        # weakness fact — keep it out of weak_points so prompts and
        # cross-round digests stay factual. The category lands in
        # followup_clues for the growth learning loop.
        clues = state.agent_state.setdefault("followup_clues", [])
        clues.append(signal.category)
        if len(clues) > 150:
            del clues[:-150]
        logger.info(
            "Follow-up signal: session=%s cat=%s len=%d",
            session_id,
            signal.category,
            len(user_text),
        )

    if rag_msg:
        blocks.append(rag_msg)
    return blocks


__all__ = ["build_turn_guidance"]
