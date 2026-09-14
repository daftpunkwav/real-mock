"""WS connection lifecycle (mixin): message send/receive primitives, main loop, and cleanup.

Responsibilities are split by dependency direction:
- :mod:`connection_auth` — authentication / session binding / pipeline assembly / opening progression;
- :mod:`heartbeat` — idle heartbeat and timeout disconnection;
- :mod:`message_dispatcher` — inbound message dispatch and audio buffering.

This module retains the main :meth:`handle` loop, send/receive primitives, and failure-close path.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import WebSocketDisconnect

from realmock.platform.core.logging import set_trace_id
from realmock.platform.database import SessionLocal
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.domains.interview.realtime.core.session_registry import release_session_connection

if TYPE_CHECKING:
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class ConnectionLifecycleMixin:
    """WS main loop: handshake, authentication assembly, message loop, cleanup."""

    ctx: "ConnectionContext"

    async def send(self, msg_type: str, **payload: Any) -> None:
        await self.ctx.ws.send_json({"type": msg_type, **payload})

    async def _tts_send(self, msg_type: str, **payload: Any) -> None:
        """TTS channel sending: comes with playback_generation for client to send back."""
        if msg_type == "tts_audio":
            payload.setdefault("playback_generation", self.ctx.awaiting_playback_gen)
        await self.send(msg_type, **payload)

    async def set_turn(self, state: TurnState) -> None:
        self.ctx.turn_state = state
        if state == TurnState.USER_SPEAKING:
            self.ctx.mic_opened_at = asyncio.get_event_loop().time()
        await self.send("turn_state", state=state.value)

    async def _fail_and_close(
        self,
        message: str,
        code: int = 4401,
        *,
        error_code: str = "B2001",
        retryable: bool = False,
    ) -> None:
        try:
            await self.send(
                "error",
                message=message,
                code=error_code,
                retryable=retryable,
            )
        except Exception:
            logger.debug(
                "fail_and_close failed to send error sid=%s",
                self.ctx.session_id,
                exc_info=True,
            )
        try:
            await self.ctx.ws.close(code=code)
        except Exception:
            logger.debug(
                "fail_and_close Failed to close WS sid=%s",
                self.ctx.session_id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------------

    async def handle(self) -> None:
        accept_kwargs: dict[str, str] = {}
        if self.ctx.ws_subprotocol:
            accept_kwargs["subprotocol"] = self.ctx.ws_subprotocol
        await self.ctx.ws.accept(**accept_kwargs)
        ws_tid = f"ws-{self.ctx.session_id}-{uuid.uuid4().hex[:8]}"
        set_trace_id(ws_tid)
        db = SessionLocal()
        try:
            session = await self.authenticate(db)
            if session is None:
                return
            if not await self.bind_pipeline(db, session):
                return
            await self.start_session_flow(session, db)
            # After the opening is completed, the main loop db is closed: each round of the message loop builds a short life cycle db and
            # Use rebind_runtime_session (see ConnectionAuthMixin) to avoid long-lived connections
            # Checkpoint will be delayed under SQLite WAL
            db.close()
            db = None
            while True:
                data = await self.next_message()
                if data is None:
                    break
                await self._dispatch(data)
        except WebSocketDisconnect:
            logger.info("WS disconnect session=%s", self.ctx.session_id)
        except Exception as e:
            logger.exception("WS Error: %s", e)
            try:
                await self.set_turn(TurnState.USER_SPEAKING)
                await self.send(
                    "error",
                    message="Server error; restored USER_SPEAKING",
                    code="B2001",
                    retryable=True,
                )
            except Exception:
                logger.debug(
                    "WS exception recovery notification failed to be sent sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
            try:
                db.rollback()
            except Exception:
                logger.debug(
                    "WS abnormal path rollback failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
        finally:
            await self._teardown(db)

    async def _teardown(self, db: Any) -> None:
        """Release the lease, cancel the background task, close the TTS queue and DB session (db may be None and has been closed early)."""
        try:
            await release_session_connection(self)
        except Exception:
            logger.exception("Failed to release session lease")
        try:
            await self._cancel_bg_tasks()
        except Exception:
            logger.exception("Failed to cancel background task")
        try:
            await asyncio.wait_for(self.ctx.tts_queue.stop(), timeout=5.0)
        except Exception:
            logger.exception("TTS queue shutdown failed")
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("DB shutdown failed")


__all__ = ["ConnectionLifecycleMixin"]
