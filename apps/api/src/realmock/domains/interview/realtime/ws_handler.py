"""WebSocket interview session handler (assembly shell).

See each mixin for subpackage responsibilities; this module only assembles stack + dispatcher + report_scheduler.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket
from sqlalchemy.orm import Session

from realmock.domains.interview.realtime.core.context import ConnectionContext
from realmock.domains.interview.realtime.core.message_dispatcher import (
    AUDIO_BUFFER_MAX_BYTES as _AUDIO_BUFFER_MAX_BYTES,
    MessageDispatcherMixin,
)
from realmock.domains.interview.realtime.report_scheduler import ReportSchedulerMixin
from realmock.domains.interview.realtime.core.session_registry import (
    claim_session_connection,
    get_ws_connection_registry,
    release_session_connection,
    reset_session_registry_for_tests,
    reset_ws_connection_registry,
    active_handlers_for_tests,
)
from realmock.domains.interview.realtime.stacks.connection_stack import ConnectionStackMixin
from realmock.domains.interview.realtime.stacks.media_stack import MediaStackMixin
from realmock.domains.interview.realtime.stacks.turn_stack import TurnStackMixin
from realmock.domains.interview.realtime.turn.streaming import _IMAGE_BASE64_MAX_LEN
from realmock.domains.interview.realtime.voice.tts_queue import _SentenceTTSQueue
from realmock.domains.interview.models import InterviewSession
from realmock.platform.capabilities.voice.tts.voice_resolve import VoiceProsody
from realmock.platform.config import get_settings


logger = logging.getLogger(__name__)


class InterviewWSHandler(
    ConnectionStackMixin,
    MessageDispatcherMixin,
    TurnStackMixin,
    MediaStackMixin,
    ReportSchedulerMixin,
):
    """Live Interview WebSocket Session façade."""

    def __init__(
        self,
        websocket: WebSocket,
        session_id: int,
        *,
        access_token: str | None = None,
        ws_subprotocol: str | None = None,
    ) -> None:
        cfg = get_settings()
        self.ctx = ConnectionContext(
            ws=websocket,
            session_id=session_id,
            client_access_token=(access_token or "").strip(),
            ws_subprotocol=ws_subprotocol,
            tts_voice=cfg.tts_voice,
            session_prosody=VoiceProsody(voice=cfg.tts_voice),
            whisper_model=cfg.whisper_model,
            nudge_cooldown_sec=float(max(5, int(getattr(cfg, "silence_nudge_seconds", 25) or 25))),
            tts_queue=_SentenceTTSQueue(),
        )

    @property
    def session_id(self) -> int:
        """Room's interview session id (delegated to the connection context)."""
        return self.ctx.session_id

    @property
    def ws(self) -> WebSocket:
        """Underlying socket (delegated to the connection context)."""
        return self.ctx.ws

    @property
    def _superseded(self) -> bool:
        return self.ctx.superseded

    @_superseded.setter
    def _superseded(self, value: bool) -> None:
        self.ctx.superseded = value

    @property
    def lease_token(self) -> str:
        """Single-tab lease token identifying this connection holder."""
        return self.ctx.lease_token

    def _spawn(self, coro) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self.ctx.bg_tasks.add(task)

        def _done(t: asyncio.Task[Any]) -> None:
            self.ctx.bg_tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                logger.exception("WS background task exception sid=%s: %s", self.ctx.session_id, exc)

        task.add_done_callback(_done)
        return task

    async def _cancel_bg_tasks(self) -> None:
        tasks = list(self.ctx.bg_tasks)
        if self.ctx.report_task is not None and not self.ctx.report_task.done():
            tasks.append(self.ctx.report_task)
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.ctx.bg_tasks.clear()
        self.ctx.report_task = None

    def _load_session(self, db: Session) -> InterviewSession | None:
        return (
            db.query(InterviewSession)
            .filter(InterviewSession.id == self.ctx.session_id)
            .first()
        )


__all__ = [
    "InterviewWSHandler",
    "_AUDIO_BUFFER_MAX_BYTES",
    "_IMAGE_BASE64_MAX_LEN",
    "claim_session_connection",
    "get_ws_connection_registry",
    "release_session_connection",
    "reset_session_registry_for_tests",
    "reset_ws_connection_registry",
    "active_handlers_for_tests",
]
