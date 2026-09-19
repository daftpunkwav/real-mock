"""Finish-notify scheduler (WS mixin).

Historically named report_scheduler. Now freezes/notifies via finish_lifecycle
and pushes ``interview_complete`` without generating a report — debrief lives
in the records domain after the interview_finished hook.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from realmock.domains.interview.ledger.store import is_frozen
from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.agents import run_finish_lifecycle
from realmock.platform.core.constants import SessionStatus
from realmock.platform.database import SessionLocal

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable, Coroutine

    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class ReportSchedulerMixin:
    """Background finish notify. Depends on ctx.session_id / report_task / send / _spawn."""

    ctx: ConnectionContext

    if TYPE_CHECKING:
        # Members provided by sibling mixins of the composed InterviewWSHandler.
        send: Callable[..., Coroutine[Any, Any, None]]
        _spawn: Callable[..., "asyncio.Task[Any]"]

    def _schedule_report_generation(self) -> None:
        """Schedule finish notify / debrief trigger (name kept for FinishControlMixin)."""
        if self.ctx.report_task is not None and not self.ctx.report_task.done():
            return
        self.ctx.report_task = self._spawn(self._generate_report_bg())

    async def _generate_report_bg(self) -> None:
        db = SessionLocal()
        try:
            session = (
                db.query(InterviewSession)
                .filter(InterviewSession.id == self.ctx.session_id)
                .first()
            )
            if not session:
                return

            # Already finished with a frozen ledger: client only needs interview_complete.
            if (
                session.status == SessionStatus.COMPLETED.value
                and is_frozen(session)
            ):
                try:
                    await self.send(
                        "interview_complete",
                        session_id=self.ctx.session_id,
                        overall_score=session.overall_score,
                        result=getattr(session, "result", None),
                    )
                except Exception:
                    logger.debug(
                        "interview_complete notify failed sid=%s",
                        self.ctx.session_id,
                        exc_info=True,
                    )
                return

            run_finish_lifecycle(db, session, mark_completed=True)
            # Wait for the closing TTS playback before announcing completion:
            # `interview_complete` is the frontend's safe-to-navigate signal.
            # Without this, it races the spoken wrap-up (assistant_done is
            # text-complete, not speech-complete) and the room jumps to the
            # report page while the comment is still playing. No-op when no
            # audio was sent (text-only / TTS failed); bounded by the playback
            # timeout inside _wait_client_playback.
            try:
                waiter = getattr(self, "_wait_client_playback", None)
                if callable(waiter):
                    await waiter()
            except Exception:
                logger.debug(
                    "closing playback wait failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
            try:
                await self.send(
                    "interview_complete",
                    session_id=self.ctx.session_id,
                    overall_score=session.overall_score,
                    result=getattr(session, "result", None),
                )
            except Exception:
                logger.debug(
                    "interview_complete notify failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
        except Exception as e:
            logger.exception(
                "finish notify failed sid=%s: %s", self.ctx.session_id, e
            )
        finally:
            try:
                db.close()
            except Exception:
                logger.debug(
                    "finish-notify DB close failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
