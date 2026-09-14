"""Active finishing (WS mixin): Streaming acknowledgment and report scheduling for candidate request_finish."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from realmock.platform.core.constants import SessionStatus
from realmock.platform.database import SessionLocal
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.domains.interview.services.interview.events import EventKind

if TYPE_CHECKING:
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class FinishControlMixin:
    """Candidates end proactively; relies on ctx.runner/llm + reporting dispatch chain."""

    ctx: "ConnectionContext"

    async def _on_request_finish(self) -> None:
        """Candidate-initiated end: streaming thanks; finish-notify scheduled (debrief lives in records domain)."""
        if self.ctx.closing:
            return
        db = SessionLocal()
        try:
            session = self._load_session(db)
            if not session:
                await self.send(
                    "error",
                    message="Interview session not found",
                    code="A2001",
                )
                return
            self.rebind_runtime_session(session)
            if session.status == SessionStatus.COMPLETED.value:
                await self.send(
                    "assistant_done",
                    content="Interview already finished; generating the report.",
                    phase=session.current_phase or "summary",
                    is_complete=True,
                    emotion="smile",
                )
                self._schedule_report_generation()
                return
            if self.ctx.runner is None or self.ctx.llm is None:
                await self.send(
                    "error",
                    message="Interview engine not ready; cannot wrap up",
                    code="A0006",
                )
                return

            self.ctx.closing = True
            try:
                await self.set_turn(TurnState.PROCESSING)
                await self.set_turn(TurnState.AI_SPEAKING)
                last = await self._stream_events_with_tts(
                    self.ctx.runner.stream_closing(db),
                    db=db,
                    session=session,
                    auto_hint=False,
                )
                if last is None or last.kind == EventKind.ERROR:
                    self.ctx.closing = False
                    await self._open_mic_after_playback()
                    await self.send(
                        "error",
                        message="Closing speech failed; retry End interview or check LLM settings",
                        code="C0001",
                        retryable=True,
                    )
                    return

                await self.set_turn(TurnState.IDLE)
                self._schedule_report_generation()
                self._spawn(self._wait_client_playback())
            except Exception:
                # The abnormal path must reset closing, otherwise barge-in/silent timeout/end again
                # Permanently blocked, the connection is not broken but the room is suspended; this mixin runs in _spawn
                # In the background task, the upward throw will only enter the log callback, so send it to the client first and then try again.
                # Raise the error frame again (send failure will no longer be thrown, and the original exception will be retained)
                self.ctx.closing = False
                try:
                    await self.send(
                        "error",
                        message="Closing failed unexpectedly; retry End interview or check LLM settings",
                        code="C0001",
                        retryable=True,
                    )
                except Exception:
                    logger.debug(
                        "Ending exception error event failed to send sid=%s",
                        self.ctx.session_id,
                        exc_info=True,
                    )
                raise
        finally:
            try:
                db.close()
            except Exception:
                logger.debug(
                    "request_finish DB close failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )


__all__ = ["FinishControlMixin"]
