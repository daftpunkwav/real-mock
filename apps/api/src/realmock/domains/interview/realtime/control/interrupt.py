"""Interruption side effects (WS mixin): Candidate interruption count and TTS clearing."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from realmock.platform.database import SessionLocal
from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.realtime.core.events import TurnState

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from typing import Any

    from realmock.domains.interview.models import InterviewSession
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class InterruptControlMixin:
    """Candidate interruption handling; depends on ctx state fields + send / set_turn / _load_session."""

    ctx: "ConnectionContext"

    if TYPE_CHECKING:
        # Members provided by sibling mixins of the composed InterviewWSHandler.
        send: Callable[..., Coroutine[Any, Any, None]]
        set_turn: Callable[[TurnState], Coroutine[Any, Any, None]]
        _load_session: Callable[..., InterviewSession | None]

    def _persist_interrupt_stats(self, session: InterviewSession, db: Session) -> None:
        """Incorporate the interrupt count into the agent memory state and then drop it into the library (single truth, anti-round save_state override rollback)."""
        try:
            state: dict = {}
            if self.ctx.agent is not None:
                state = dict(self.ctx.agent.agent_state)
            elif session.agent_state:
                loaded = json.loads(session.agent_state)
                state = loaded if isinstance(loaded, dict) else {}
            state["candidate_interrupts"] = self.ctx.candidate_interrupts
            state["ai_interrupts"] = self.ctx.ai_interrupts
            if self.ctx.agent is not None:
                # The memory state is synchronized with the library, and the count is not lost when serializing save_state in subsequent rounds.
                self.ctx.agent.agent_state["candidate_interrupts"] = self.ctx.candidate_interrupts
                self.ctx.agent.agent_state["ai_interrupts"] = self.ctx.ai_interrupts
            session.agent_state = json.dumps(state, ensure_ascii=False)
            db.add(session)
            db.commit()
        except Exception:
            logger.exception("Persistence interruption statistics failed sid=%s", self.ctx.session_id)
            try:
                db.rollback()
            except Exception:
                logger.debug(
                    "Interrupting statistics rollback failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )

    async def _on_candidate_barge_in(self) -> None:
        """The candidate interrupts the interviewer's broadcast: clear the TTS and let go of the conversation."""
        if self.ctx.turn_state not in (TurnState.AI_SPEAKING, TurnState.PROCESSING):
            return
        self.ctx.candidate_interrupts += 1
        self.ctx.stream_epoch += 1
        self.ctx.playback_generation += 1
        self.ctx.awaiting_playback_gen = self.ctx.playback_generation
        await self.ctx.tts_queue.clear()
        self.ctx.tts_sent_this_turn = False
        self.ctx.playback_done.set()
        self.ctx.audio_buffer = []
        self.ctx.audio_buffer_bytes = 0
        await self.send(
            "tts_interrupted",
            reason="candidate_barge",
            candidate_interrupts=self.ctx.candidate_interrupts,
            playback_generation=self.ctx.awaiting_playback_gen,
        )
        db = SessionLocal()
        try:
            try:
                session = self._load_session(db)
                if session:
                    self._persist_interrupt_stats(session, db)
            except Exception:
                logger.exception("Interruption statistics reading failed sid=%s", self.ctx.session_id)
        finally:
            try:
                db.close()
            except Exception:
                logger.debug(
                    "Interrupt statistics DB close failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
        await self.set_turn(TurnState.USER_SPEAKING)
        logger.info(
            "Candidate interrupt sid=%s count=%s epoch=%s",
            self.ctx.session_id,
            self.ctx.candidate_interrupts,
            self.ctx.stream_epoch,
        )


__all__ = ["InterruptControlMixin"]
