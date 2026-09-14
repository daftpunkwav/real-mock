"""Finish-notify scheduler (WS mixin).

Historically named report_scheduler. Now freezes/notifies via finish_lifecycle
and pushes ``interview_complete`` without generating a report — debrief lives
in the records domain after the interview_finished hook.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from realmock.domains.interview.ledger.store import is_frozen
from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.services.interview.finish_lifecycle import run_finish_lifecycle
from realmock.platform.core.constants import SessionStatus
from realmock.platform.database import SessionLocal

if TYPE_CHECKING:
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class ReportSchedulerMixin:
    """Background finish notify. Depends on ctx.session_id / report_task / send / _spawn."""

    ctx: ConnectionContext

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
