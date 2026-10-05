"""Finish-notify scheduler (WS mixin).

Historically named report_scheduler. Now freezes/notifies via finish_lifecycle
and pushes ``interview_complete`` without generating a report — debrief lives
in the records domain after the interview_finished hook.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from realmock.domains.interview.agents import run_finish_lifecycle
from realmock.domains.interview.ledger.store import is_frozen
from realmock.domains.interview.models import InterviewSession
from realmock.platform.core.constants import SessionStatus
from realmock.platform.database import SessionLocal

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


def _finish_notify_sync(session_id: int) -> tuple[bool, bool, Any, Any]:
    """Blocking finish path: freeze the session and snapshot the outcome.

    Self-contained session lifecycle (open/close inside the thread, same
    convention as session_registry). Returns ``(found, already_frozen,
    overall_score, result)``. ``found`` is False only when the row does
    not exist — score and result are legitimately None right after the
    first finish (the debrief writes the score later), so they must never
    double as a missing-row signal. The scalars are read AFTER the
    lifecycle commit and BEFORE the session closes, because the ORM
    expires attributes on commit and the async side must not touch the
    instance afterwards.
    """
    db = SessionLocal()
    try:
        session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
        if not session:
            return False, False, None, None

        # Already finished with a frozen ledger: client only needs interview_complete.
        already_frozen = session.status == SessionStatus.COMPLETED.value and is_frozen(session)
        if not already_frozen:
            run_finish_lifecycle(db, session, mark_completed=True)
        # Snapshot after the commit-triggered expiry, before close():
        # the attribute access re-fetches the row inside this thread.
        return True, already_frozen, session.overall_score, getattr(session, "result", None)
    finally:
        try:
            db.close()
        except Exception:
            logger.debug(
                "finish-notify DB close failed sid=%s",
                session_id,
                exc_info=True,
            )


class ReportSchedulerMixin:
    """Background finish notify. Depends on ctx.session_id / report_task / send / _spawn."""

    ctx: ConnectionContext

    if TYPE_CHECKING:
        # Members provided by sibling mixins of the composed InterviewWSHandler.
        send: Callable[..., Coroutine[Any, Any, None]]
        _spawn: Callable[..., "asyncio.Task[Any]"]

    def _schedule_report_generation(self) -> None:
        """Schedule finish notify / debrief trigger.

        The historical name is kept because FinishControlMixin and
        UserTextControlMixin call it across the composed handler.
        """
        if self.ctx.report_task is not None and not self.ctx.report_task.done():
            return
        self.ctx.report_task = self._spawn(self._generate_report_bg())

    async def _generate_report_bg(self) -> None:
        try:
            # Blocking finish work (load / freeze / lifecycle commit) runs in
            # a worker thread; only the awaited notifications stay on the loop.
            found, already_frozen, overall_score, result = await asyncio.to_thread(
                _finish_notify_sync, self.ctx.session_id
            )
            if not found:
                # The session row is gone; nothing to notify about.
                return
            if already_frozen:
                try:
                    await self.send(
                        "interview_complete",
                        session_id=self.ctx.session_id,
                        overall_score=overall_score,
                        result=result,
                    )
                except Exception:
                    logger.debug(
                        "interview_complete notify failed sid=%s",
                        self.ctx.session_id,
                        exc_info=True,
                    )
                return
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
                    overall_score=overall_score,
                    result=result,
                )
            except Exception:
                logger.debug(
                    "interview_complete notify failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
        except Exception as e:
            logger.exception("finish notify failed sid=%s: %s", self.ctx.session_id, e)
