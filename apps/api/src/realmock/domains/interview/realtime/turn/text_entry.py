"""Candidate text input into a turn (WS mixin): emit ``stt_final`` before entering the main flow.

Extracted from :mod:`...turn_coordinator`. This only orchestrates text turns; lock semantics live in
:class:`TurnLockMixin`, and the main flow is consumed by ``user_text_control.UserTextControlMixin``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any


from realmock.platform.database import SessionLocal
from realmock.domains.interview.realtime.core.events import TurnState

if TYPE_CHECKING:
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class TurnTextEntryMixin:
    """Text-to-turn: acquire lock → send ``stt_final`` → main flow; on failure, return to ``USER_SPEAKING``."""

    ctx: "ConnectionContext"

    async def _run_user_text(
        self,
        text: str,
        data: dict[str, Any],
    ) -> None:
        epoch = self._begin_user_turn()
        if epoch is None:
            logger.info(
                "user_text lock busy sid=%s turn_busy=%s busy_epoch=%s stream_epoch=%s",
                self.ctx.session_id,
                self.ctx.turn_busy,
                self.ctx.busy_epoch,
                self.ctx.stream_epoch,
            )
            await self.send(
                "info",
                message="The interviewer is still responding to the previous turn; please wait a moment",
            )
            return
        db = SessionLocal()
        try:
            session = self._load_session(db)
            if not session:
                logger.warning("user_text session missing sid=%s", self.ctx.session_id)
                await self.send(
                    "error",
                    message="Interview session not found; please re-enter the interview",
                    code="A2001",
                    retryable=False,
                )
                return
            self.rebind_runtime_session(session)
            await self.set_turn(TurnState.PROCESSING)
            await self.send("stt_final", text=text)
            await self._process_user_text(text, data, db, session)
        except Exception:
            logger.exception("user_text round failed sid=%s", self.ctx.session_id)
            try:
                if epoch == self.ctx.stream_epoch:
                    await self.set_turn(TurnState.USER_SPEAKING)
                    await self.send(
                        "error",
                        message="AI interviewer temporarily unavailable; please retry later",
                        code="C0001",
                        retryable=True,
                    )
            except Exception:
                logger.debug(
                    "user_text restore USER_SPEAKING failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
        finally:
            self._end_user_turn(epoch)
            try:
                db.close()
            except Exception:
                logger.debug(
                    "user_text DB close failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )


__all__ = ["TurnTextEntryMixin"]
