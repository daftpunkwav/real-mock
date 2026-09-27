"""Interruption side effects (WS mixin): Candidate interruption count and TTS clearing."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

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
    """Candidate interruption handling; depends on ctx state fields + send / set_turn / runner."""

    ctx: "ConnectionContext"

    if TYPE_CHECKING:
        # Members provided by sibling mixins of the composed InterviewWSHandler.
        send: Callable[..., Coroutine[Any, Any, None]]
        set_turn: Callable[[TurnState], Coroutine[Any, Any, None]]
        runner: Any

    def _persist_interrupt_stats_sync(self, session_id: int, state_json: str) -> bool:
        """Persist the merged interrupt state onto the session row (blocking).

        Runs in a worker thread: opens and closes its own session, touches
        only the ``agent_state`` column, and returns whether the write landed.
        """
        db = SessionLocal()
        try:
            session = (
                db.query(InterviewSession)
                .filter(InterviewSession.id == session_id)
                .first()
            )
            if session is None:
                return False
            session.agent_state = state_json
            db.commit()
            return True
        except Exception:
            logger.exception("Persistence interruption statistics failed sid=%s", session_id)
            try:
                db.rollback()
            except Exception:
                logger.debug(
                    "Interrupting statistics rollback failed sid=%s",
                    session_id,
                    exc_info=True,
                )
            return False
        finally:
            try:
                db.close()
            except Exception:
                logger.debug(
                    "Interrupt statistics DB close failed sid=%s",
                    session_id,
                    exc_info=True,
                )

    async def _persist_interrupt_stats(self) -> None:
        """Record the interrupt counts through the runner facade, then persist.

        The counters are merged into the agent's working state (the single
        write path, so a later ``save_state`` cannot roll them back); the same
        snapshot is then written to the session row off the event loop.
        """
        runner = self.ctx.runner
        if runner is None:
            return
        state = runner.record_interrupt_counts(
            candidate=self.ctx.candidate_interrupts,
            ai=self.ctx.ai_interrupts,
        )
        state_json = json.dumps(state, ensure_ascii=False)
        await asyncio.to_thread(
            self._persist_interrupt_stats_sync, self.ctx.session_id, state_json
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
        try:
            await self._persist_interrupt_stats()
        except Exception:
            logger.exception("Interruption statistics reading failed sid=%s", self.ctx.session_id)
        await self.set_turn(TurnState.USER_SPEAKING)
        logger.info(
            "Candidate interrupt sid=%s count=%s epoch=%s",
            self.ctx.session_id,
            self.ctx.candidate_interrupts,
            self.ctx.stream_epoch,
        )


__all__ = ["InterruptControlMixin"]
