"""WS inbound message dispatch (mixin): audio_chunk / stt_text / user_turn_end / various requests."""

from __future__ import annotations

import asyncio
import base64
import logging
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.domains.interview.capabilities.vision.agent import VisionAgent
from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.platform.core import constants as _platform_constants
from realmock.platform.core.constants import DEFAULT_LLM_RATE_LIMIT_PER_MINUTE, MAX_USER_TEXT_CHARS
from realmock.platform.core.ratelimit import try_rate_limit_by_id

if TYPE_CHECKING:
    from collections.abc import Mapping

    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)

# Single source: canonical value lives in platform.core.constants; this alias
# keeps the historic module name (ws_handler re-exports it and tests pin it).
AUDIO_BUFFER_MAX_BYTES: int = _platform_constants.AUDIO_BUFFER_MAX_BYTES
_WS_LLM_RATE_LIMIT = DEFAULT_LLM_RATE_LIMIT_PER_MINUTE


class MessageDispatcherMixin:
    """Distributed by message type; relies on ctx field and _spawn/send/set_turn."""

    ctx: "ConnectionContext"

    def _llm_rate_limited(self, *, limit: int) -> bool:
        if not try_rate_limit_by_id(
            key="llm",
            client_id=f"ws-{self.ctx.session_id}",
            limit=limit,
        ):
            return True
        return False

    # Message type -> admission wrapper name on the composed handler.
    # Table-driven dispatch keeps the branch list flat; unknown types warn.
    # Wrappers use the ``_start_*`` prefix to stay distinct from the ``_on_*``
    # turn workers they spawn (e.g. ``_start_user_turn_end`` vs ``_on_user_turn_end``).
    # The mapping is immutable so a subclass cannot corrupt dispatch for siblings.
    _MESSAGE_HANDLER_NAMES: "Mapping[str, str]" = MappingProxyType(
        {
            "audio_chunk": "_on_audio_chunk",
            "stt_text": "_on_stt_text",
            "pong": "_on_pong",
            "vision_update": "_on_vision_update",
            "user_turn_end": "_start_user_turn_end",
            "silence_timeout": "_on_silence_timeout",
            "barge_in": "_on_barge_in",
            "user_text": "_on_user_text",
            "request_hint": "_start_request_hint",
            "request_finish": "_start_request_finish",
            "tts_playback_done": "_on_tts_playback_done",
        }
    )

    async def _dispatch(
        self,
        data: dict[str, Any],
        db: Session | None = None,
        session: InterviewSession | None = None,
    ) -> None:
        """Distributed by message type; the round path builds a short life cycle db by itself, and this method does not use db/session."""
        msg_type = data.get("type", "")
        handler_name = self._MESSAGE_HANDLER_NAMES.get(msg_type)
        if handler_name is None:
            logger.warning("Unknown WS message type sid=%s type=%s", self.ctx.session_id, msg_type)
            return
        handler = getattr(self, handler_name, None)
        if handler is None:
            logger.warning(
                "Dispatch table points to missing handler sid=%s type=%s name=%s",
                self.ctx.session_id,
                msg_type,
                handler_name,
            )
            return
        await handler(data)

    async def _on_stt_text(self, data: dict[str, Any]) -> None:
        text = data.get("text", "").strip()
        if text:
            await self.send("stt_partial", text=text)

    async def _on_pong(self, data: dict[str, Any]) -> None:
        del data

    async def _on_vision_update(self, data: dict[str, Any]) -> None:
        face = data.get("face_analysis")
        if face:
            self.ctx.orchestrator.snapshot.merge_face(face)
            self.ctx.orchestrator.snapshot.vision_summary = VisionAgent.summarize(face)

    async def _start_user_turn_end(self, data: dict[str, Any]) -> None:
        if not self._can_start_user_turn():
            return
        if self._llm_rate_limited(limit=_WS_LLM_RATE_LIMIT):
            await self._send_rate_limited()
            return
        self._spawn(self._run_user_turn_end(data))

    async def _on_silence_timeout(self, data: dict[str, Any]) -> None:
        del data
        if self.ctx.turn_busy or self.ctx.closing:
            return
        self._spawn(self._on_silence_nudge())

    async def _on_barge_in(self, data: dict[str, Any]) -> None:
        del data
        if self.ctx.closing:
            return
        self._spawn(self._on_candidate_barge_in())

    async def _start_request_hint(self, data: dict[str, Any]) -> None:
        if self._llm_rate_limited(limit=max(5, _WS_LLM_RATE_LIMIT // 2)):
            # Terminal event (not the generic error): the room clears its
            # loading state instead of hanging until the client timeout.
            await self._hint_rate_limited(data)
            return
        self._spawn(self._on_request_hint(data))

    async def _start_request_finish(self, data: dict[str, Any]) -> None:
        del data
        if self.ctx.closing:
            return
        self._spawn(self._on_request_finish())

    async def _on_tts_playback_done(self, data: dict[str, Any]) -> None:
        client_gen = data.get("generation")
        if client_gen is None or client_gen == self.ctx.awaiting_playback_gen:
            self.ctx.playback_done.set()
            # The interviewer's voice just finished: silence timing starts here.
            self.ctx.speech_end_at = asyncio.get_event_loop().time()

    async def _send_rate_limited(self) -> None:
        await self.send(
            "error",
            message="Too many requests, please try again later",
            code="A0002",
            retryable=True,
        )

    async def _on_audio_chunk(self, data: dict[str, Any]) -> None:
        chunk = data.get("data", "")
        if not chunk:
            return
        try:
            new_bytes = len(base64.b64decode(chunk, validate=False))
        except (ValueError, TypeError):
            logger.debug(
                "audio_chunk not base64 session=%s", self.ctx.session_id, exc_info=True
            )
            new_bytes = 0
        if self.ctx.audio_buffer_bytes + new_bytes > AUDIO_BUFFER_MAX_BYTES:
            logger.warning(
                "audio_buffer exceeds the upper limit session=%s bytes=%s",
                self.ctx.session_id,
                self.ctx.audio_buffer_bytes + new_bytes,
            )
            await self.send(
                "error",
                message="Audio buffer exceeded; end the current turn first",
                code="A0004",
            )
            self.ctx.audio_buffer = []
            self.ctx.audio_buffer_bytes = 0
            return
        self.ctx.audio_buffer.append(chunk)
        self.ctx.audio_buffer_bytes += new_bytes

    async def _on_user_text(self, data: dict[str, Any]) -> None:
        text = data.get("text", "").strip()
        if len(text) > MAX_USER_TEXT_CHARS:
            await self.send(
                "error",
                message=f"Text too long (limit: {MAX_USER_TEXT_CHARS} characters)",
                code="A0003",
            )
            return
        if (
            text
            and self.ctx.turn_state == TurnState.USER_SPEAKING
            and self._can_start_user_turn()
        ):
            if self._llm_rate_limited(limit=_WS_LLM_RATE_LIMIT):
                await self._send_rate_limited()
                return
            self._spawn(self._run_user_text(text, data))


__all__ = ["MessageDispatcherMixin", "AUDIO_BUFFER_MAX_BYTES"]
