"""User text enters the round (WS mixin): Candidate text enters the main round process."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.domains.interview.agents.events import EventKind

if TYPE_CHECKING:
    from realmock.domains.interview.realtime.core.context import ConnectionContext


class UserTextControlMixin:
    """Candidate text enters the round; relies on ctx.runner + turn_streaming consumption chain."""

    ctx: "ConnectionContext"

    async def _process_user_text(
        self, text: str, data: dict[str, Any], db: Session, session: InterviewSession
    ) -> None:
        assert self.ctx.runner is not None
        # The candidate may reply while the previous turn's TTS audio is still
        # playing (the mic opens at text-complete now): stop the stale audio so
        # the new turn's audio does not overlap it.
        await self._cancel_pending_playback()
        start_epoch = self.ctx.stream_epoch
        await self.set_turn(TurnState.PROCESSING)
        await self.set_turn(TurnState.AI_SPEAKING)

        last = await self._stream_events_with_tts(
            self._consume_runner_turn(text, data, db),
            db=db,
            session=session,
            auto_hint=True,
        )
        if start_epoch != self.ctx.stream_epoch:
            return
        if self.ctx.turn_state == TurnState.USER_SPEAKING:
            return
        if last is None or last.kind == EventKind.ERROR:
            await self._open_mic_after_playback()
            return
        if last.is_complete:
            await self.set_turn(TurnState.IDLE)
            self._schedule_report_generation()
            self._spawn(self._wait_client_playback())
        else:
            await self._open_mic_after_playback()


__all__ = ["UserTextControlMixin"]
