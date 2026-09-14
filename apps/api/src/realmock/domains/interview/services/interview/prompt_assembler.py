"""Interview turn: message assembly and context lookup.

Split from :class:`realmock.domains.interview.services.interview.runner.InterviewRunner`:
- Assemble final LLM messages (face-analysis hints / image modality / long-context compaction);
- Read-only lookups for candidate profile and LLM settings.

Long interviews (1h+) compact via LLM session minutes
(:func:`compact_with_summary`); compaction failure propagates;
rule-based fallback lives in runner_opening.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.interview.models import InterviewSession
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.context.summarize import compact_with_summary
from realmock.domains.interview.services.interview.session_state import InterviewSessionState
from realmock.platform.database import api_db_session
from realmock.platform.services.pipeline.config import get_stage_config_for_runtime

logger = logging.getLogger(__name__)

#: Keep this many recent messages verbatim when minutes-compaction kicks in.
_COMPACT_KEEP_RECENT = 20


class PromptAssembler:
    """Helper to build LLM call messages (stateless; reusable across a session)."""

    def __init__(
        self,
        session: InterviewSession,
        agent: InterviewSessionState,
        llm: Any | None = None,
    ) -> None:
        self.session = session
        self.agent = agent
        self.llm = llm

    @staticmethod
    def build_user_content(
        text: str,
        face: dict[str, Any] | None,
    ) -> str:
        """Assemble the user text sent to the LLM (including face-analysis hints)."""
        content = text
        if face:
            hints: list[str] = []
            if not face.get("face_detected", True):
                hints.append("no face detected in frame")
            elif face.get("looking_away"):
                hints.append("candidate appears to be looking away from the camera")
            nervousness = face.get("nervousness", 0)
            if isinstance(nervousness, (int, float)) and nervousness > 0.5:
                hints.append("candidate appears nervous")
            if hints:
                content += f"\n[Face analysis: {'; '.join(hints)}]"
        return content

    async def build_api_messages(
        self,
        text: str,
        face: dict[str, Any] | None,
        image_b64: str | None,
        context_window: int | None = None,
    ) -> list[dict[str, Any]]:
        """Build the messages list for the LLM API (image modality + compaction when needed).

        Caller must ensure ``self.agent.messages`` already ends with the current-turn user
        message (set by :meth:`stream_turn`). This method does not append another user message.
        """
        messages = list(self.agent.messages)
        if image_b64:
            user_content = self.build_user_content(text, face)
            messages[-1] = {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_content},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }

        memory = WorkingMemory.from_state(self.agent.agent_state)
        if context_window:
            compressed = await compact_with_summary(
                messages,
                context_window,
                memory=memory,
                llm=self.llm,
                keep_recent=_COMPACT_KEEP_RECENT,
            )
            self.agent.agent_state.update(memory.to_state_patch())
            if len(compressed) < len(messages):
                logger.info(
                    "Context compaction: session=%s %d->%d (budget=%d)",
                    self.session.id, len(messages), len(compressed), context_window,
                )
            return compressed
        return messages

    def last_assistant_question(self) -> str:
        """Return the latest interviewer utterance from history (for follow-up analysis)."""
        for m in reversed(self.agent.messages):
            if m.get("role") == "assistant":
                content = m.get("content", "")
                if isinstance(content, str):
                    return content
        return ""

    def get_tech_domains(self, db: Session) -> list[str]:
        """Read tech-domain list from the candidate profile."""
        profile = self.agent.get_user_profile(db)
        if profile is None:
            return []
        return profile.tech_domains_list or []

    def get_context_window(self, db: Session) -> int:
        """Read context window from current LLM settings.

        0 or unset means unlimited (no compression). Config lives in the api db.
        """
        with api_db_session() as api_db:
            config = get_stage_config_for_runtime(api_db, "reason")
            context_window = config.get("context_window")
            if not context_window:
                return 0
            return int(context_window)


__all__ = ["PromptAssembler"]
