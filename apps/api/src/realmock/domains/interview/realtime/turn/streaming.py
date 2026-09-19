"""Round streaming consumption and TTS enqueue (WS mixin)."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.agents import strip_markers
from realmock.domains.interview.agents.events import EventKind, StreamEvent
from realmock.platform.capabilities.voice.tts.providers.edge import (
    next_soft_min,
    should_flush_sentence_buffer,
)

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable, Coroutine

    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)

_IMAGE_BASE64_MAX_LEN: int = 300_000


class TurnStreamingMixin:
    """Consume a round stream; depends on ctx.runner/orchestrator/tts_queue/stream_epoch, etc."""

    ctx: "ConnectionContext"

    if TYPE_CHECKING:
        # Members provided by sibling mixins of the composed InterviewWSHandler.
        _begin_playback_wait: Callable[..., None]
        send: Callable[..., Coroutine[Any, Any, None]]
        _spawn: Callable[..., "asyncio.Task[Any]"]
        _on_request_hint: Callable[..., Coroutine[Any, Any, None]]
        arm_turn_timers: Callable[..., None]

    async def _consume_runner_opening(self, db: Session):
        assert self.ctx.runner is not None
        async for event in self.ctx.runner.stream_opening(db):
            yield event

    async def _consume_runner_turn(
        self,
        text: str,
        data: dict[str, Any],
        db: Session,
    ):
        assert self.ctx.runner is not None
        face = data.get("face_analysis") or self.ctx.orchestrator.snapshot.face_analysis
        image_b64 = data.get("image_base64")
        if isinstance(image_b64, str) and len(image_b64) > _IMAGE_BASE64_MAX_LEN:
            logger.warning(
                "WS image_base64 exceeds limit sid=%s len=%d, discarded",
                self.ctx.session_id,
                len(image_b64),
            )
            image_b64 = None
        self.ctx.orchestrator.snapshot.last_user_text = text
        self.ctx.orchestrator.snapshot.merge_face(face)

        async for event in self.ctx.runner.stream_turn(
            text,
            db,
            face=face,
            image_b64=image_b64,
        ):
            yield event

    async def _stream_events_with_tts(
        self,
        events,
        *,
        db: Session | None = None,
        session: InterviewSession | None = None,
        auto_hint: bool = True,
    ) -> StreamEvent | None:
        """Enqueue TTS sentence by sentence; return the final TURN_COMPLETE/ERROR.

        runner has already parsed the say-first protocol: every TOKEN is plaintext say content (think removed),
        and TURN_COMPLETE carries control fields (emotion/wait_seconds/sources).
        """
        self._begin_playback_wait()
        t0 = time.perf_counter()
        first_token_ms: float | None = None
        sentence_buf = ""
        last: StreamEvent | None = None
        turn_emotion = "neutral"
        epoch = self.ctx.stream_epoch
        soft_min, self.ctx.tts_soft_idx = next_soft_min(self.ctx.tts_soft_idx)
        async for event in events:
            if epoch != self.ctx.stream_epoch:
                return None
            if event.kind == EventKind.TOKEN:
                visible = event.token or ""
                if visible:
                    if first_token_ms is None:
                        first_token_ms = (time.perf_counter() - t0) * 1000.0
                    await self.send("assistant_token", token=visible)
                    sentence_buf += visible
                    if should_flush_sentence_buffer(sentence_buf, soft_min=soft_min):
                        if epoch != self.ctx.stream_epoch:
                            return None
                        await self.ctx.tts_queue.enqueue(
                            sentence_buf, emotion=turn_emotion
                        )
                        sentence_buf = ""
                        soft_min, self.ctx.tts_soft_idx = next_soft_min(self.ctx.tts_soft_idx)
            elif event.kind == EventKind.TURN_COMPLETE:
                if epoch != self.ctx.stream_epoch:
                    return None
                if event.emotion:
                    turn_emotion = event.emotion
                clean = strip_markers(event.content or "")
                await self.send(
                    "assistant_done",
                    content=clean,
                    phase=event.phase_id,
                    is_complete=event.is_complete,
                    emotion=event.emotion,
                    wait_seconds=event.wait_seconds,
                    answer_wait_seconds=event.answer_wait_seconds,
                    sources=list(event.sources),
                    result=event.result,
                    phase_title=event.phase_title or None,
                    playback_generation=self.ctx.awaiting_playback_gen,
                )
                if event.phase_id:
                    await self.send(
                        "phase_changed",
                        phase=event.phase_id,
                        phase_title=event.phase_title or None,
                    )
                if (
                    auto_hint
                    and not event.is_complete
                    and clean.strip()
                ):
                    self._spawn(self._on_request_hint({"question": clean}))
                # Latest per-question wait estimate drives the silence timer
                # (frontend waitMs + backend nudge cooldown, clamped 7-60s).
                self.ctx.last_wait_seconds = float(event.wait_seconds or 0)
                self.ctx.last_answer_wait_seconds = float(event.answer_wait_seconds or 0)
                if not event.is_complete:
                    self.arm_turn_timers()
                total_ms = (time.perf_counter() - t0) * 1000.0
                logger.info(
                    "turn_stream sid=%s first_token_ms=%s total_ms=%.0f",
                    self.ctx.session_id,
                    f"{first_token_ms:.0f}" if first_token_ms is not None else "-",
                    total_ms,
                )
                if epoch != self.ctx.stream_epoch:
                    return None
                if sentence_buf.strip():
                    await self.ctx.tts_queue.enqueue(
                        sentence_buf, emotion=turn_emotion
                    )
                    sentence_buf = ""
                if epoch != self.ctx.stream_epoch:
                    return None
                # Drain the TTS queue in the background: the mic opens as soon as the
                # text is complete (assistant_done above), without waiting for every
                # sentence to be synthesized or played. Pending audio keeps playing;
                # a user reply cancels it via _cancel_pending_playback, and barge-in
                # clears the queue, so the stale drain just joins an empty queue.
                self._spawn(
                    self.ctx.tts_queue.flush_remainder("", emotion=turn_emotion)
                )
                last = event
            elif event.kind == EventKind.ERROR:
                await self.send(
                    "error",
                    message=event.error,
                    code=event.error_code or "C0001",
                    retryable=event.error_retryable,
                )
                last = event
        if epoch != self.ctx.stream_epoch:
            return None
        return last
