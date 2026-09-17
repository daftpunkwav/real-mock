"""Follow-up signals + RAG-hit injection and message-tail normalization.

Extracted from :mod:`realmock.domains.interview.agents.interviewer.runner` with a single responsibility:
- Analyze the follow-up signal (needs_followup), inject a system message, and record weaknesses;
- Inject RAG hits as a system message;
- Normalize the message tail: ensure the user message is last and this turn's appended system prompts follow it.
"""

from __future__ import annotations

import logging
from typing import Any

from realmock.domains.interview.agents.session_state import InterviewSessionState
from realmock.domains.interview.agents.followup import analyze as analyze_followup

logger = logging.getLogger(__name__)


def append_followup_and_rag(
    state: InterviewSessionState,
    *,
    user_text: str,
    last_question: str,
    tech_domains: list[str],
    phase_id: str,
    rag_msg: dict[str, Any] | None,
    face: dict[str, Any] | None,
    build_user_content: Any,
    session_id: int,
    pending_probe: str | None = None,
) -> None:
    """Inject the follow-up signal + RAG hits + reorder the message tail (keeping user last).

    Follow-up guidance and RAG system messages are temporarily stored in append order, then restored in their original order after the user message is replaced,
    ensuring that only system prompts appended for the current turn follow user.
    """
    signal = analyze_followup(
        user_text,
        question=last_question,
        tech_domains=tech_domains,
        phase_id=phase_id,
        pending_probe=pending_probe,
    )
    if signal.needs_followup:
        state.messages.append({
            "role": "system",
            "content": f"[Follow-up guidance: {signal.category}] {signal.suggested_probe}",
        })
        # The guidance wording is an examiner instruction, not a candidate
        # weakness fact — keep it out of weak_points so prompts and
        # cross-round digests stay factual. The category lands in
        # followup_clues for the growth learning loop.
        clues = state.agent_state.setdefault("followup_clues", [])
        clues.append(signal.category)
        if len(clues) > 60:
            del clues[:-60]
        logger.info(
            "Follow-up signal: session=%s cat=%s len=%d",
            session_id, signal.category, len(user_text),
        )

    state.refresh_system_memory()

    if rag_msg:
        state.messages.append(rag_msg)

    # Follow-up / RAG were appended after user; pop them, replace user, then re-append
    trailing_msgs: list[dict[str, Any]] = []
    for _ in range(5):
        if not state.messages:
            break
        tail = state.messages[-1]
        if tail.get("role") != "system":
            break
        content = tail.get("content", "")
        if not (isinstance(content, str) and (
            content.startswith("[Follow-up guidance")
            or content.startswith("[Question guidance")
            or content.startswith("## Company knowledge")
            or content.startswith("## Enterprise knowledge base")
            or content.startswith("## Enterprise Knowledge Base")
        )):
            break
        trailing_msgs.append(state.messages.pop())
    trailing_msgs.reverse()

    user_content = build_user_content(user_text, face)
    state.messages[-1] = {"role": "user", "content": user_content}
    for m in trailing_msgs:
        state.messages.append(m)


__all__ = ["append_followup_and_rag"]
