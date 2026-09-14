"""Silence follow-up orchestration (WS mixin): trigger conditions + follow-up delivery + history integration.

LLM generation of realistic follow-ups is in :mod:`silence_probe` (this module does not duplicate the generation logic).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from realmock.platform.database import SessionLocal
from realmock.domains.interview.realtime.core.events import TurnState

if TYPE_CHECKING:
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class SilenceNudgeMixin:
    """Silence follow-up orchestration; depends on ctx fields + _generate_silence_probe (SilenceProbeMixin)."""

    ctx: "ConnectionContext"

    async def _on_silence_nudge(self) -> None:
        """Realistic silence follow-up: use the reasoning LLM to generate one in real time from the current
question/follow-up plan/silence count.

        Follow up at most twice for the same question (first encourage the candidate to speak,
        then provide a direct hint); if the LLM fails, fall back to a local template; append the
        follow-up text to the previous assistant utterance to preserve alternating message roles
        (required by the Anthropic protocol).
        """
        if self.ctx.turn_state != TurnState.USER_SPEAKING:
            return
        now = asyncio.get_event_loop().time()
        if self.ctx.mic_opened_at and now - self.ctx.mic_opened_at < self.ctx.nudge_grace_sec:
            return
        cooldown = self.ctx.nudge_cooldown_sec
        if self.ctx.stt_fail_streak >= 2:
            cooldown = 45.0
        if now - self.ctx.last_nudge_at < cooldown:
            return
        self.ctx.last_nudge_at = now
        db = SessionLocal()
        try:
            session = self._load_session(db)
            if not session:
                return
            question = self._last_assistant_text()
            if question != self.ctx.silence_probe_question:
                self.ctx.silence_probe_question = question
                self.ctx.silence_probe_seq = 0
            if self.ctx.silence_probe_seq >= 2:
                return
            self.ctx.silence_probe_seq += 1

            state = getattr(self.ctx.agent, "agent_state", {}) or {}
            probe_hint = str(state.get("last_probe") or "")
            silent_sec = int(now - self.ctx.mic_opened_at) if self.ctx.mic_opened_at else 0

            probe_text = await self._generate_silence_probe(
                question=question,
                probe_hint=probe_hint,
                attempt=self.ctx.silence_probe_seq,
                silent_sec=silent_sec,
            )
            if not probe_text or probe_text == self.ctx.last_silence_probe:
                probe_text = self.ctx.orchestrator.build_silence_nudge(
                    session.personality,
                    session.strictness,
                    phase=session.current_phase,
                )
            self.ctx.last_silence_probe = probe_text

            await self.set_turn(TurnState.PROCESSING)
            await self.send(
                "silence_nudge",
                content=probe_text,
                seq=self.ctx.silence_probe_seq,
            )
            self._begin_playback_wait()
            await self._speak_one(probe_text)
            self._append_to_last_assistant(probe_text)
            # Short single-sentence prompt while the candidate is silent: wait the
            # playback out before reopening the mic.
            await self._open_mic_after_playback(wait_playback=True)
        finally:
            try:
                db.close()
            except Exception:
                logger.debug(
                    "silence_nudge DB close failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )

    def _last_assistant_text(self) -> str:
        """The most recent interviewer's statement in the message history (the contextual anchor for realistic questioning)."""
        if not self.ctx.agent:
            return ""
        for m in reversed(self.ctx.agent.messages):
            if m.get("role") == "assistant":
                return str(m.get("content") or "")
        return ""

    def _append_to_last_assistant(self, text: str) -> None:
        """Merge the follow-up question into the latest assistant statement to avoid consecutive assistants in the message history."""
        if not self.ctx.agent or not text:
            return
        for m in reversed(self.ctx.agent.messages):
            if m.get("role") == "assistant":
                content = str(m.get("content") or "")
                m["content"] = f"{content}\n{text}" if content else text
                return


__all__ = ["SilenceNudgeMixin"]
