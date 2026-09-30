"""End-of-turn STT (WS mixin): PCM limit / loopback-capture detection / recognition failure and turn admission.

The PCM and browser-text paths share the same
``transcribe_utterance_result`` binding (a module-level name here; tests
patch ``realmock.domains.interview.realtime.turn.stt_finish.transcribe_utterance_result``),
and finally share ``_pick_stt_text`` → loopback-capture detection → ``_process_user_text``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.platform.core.constants import AUDIO_BUFFER_MAX_BYTES, MAX_USER_TEXT_CHARS
from realmock.platform.database import SessionLocal
from realmock.domains.interview.constants import BUSY_TURN_NOTICE
from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.platform.capabilities.voice.stt import transcribe_utterance_result
from realmock.platform.capabilities.voice.stt.providers.whisper import local_stt_unavailable_reason
from realmock.domains.interview.realtime.voice.pipeline import _is_echo_of_assistant, _pick_stt_text

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)

# Single source: canonical value lives in platform.core.constants.
_AUDIO_BUFFER_MAX_BYTES: int = AUDIO_BUFFER_MAX_BYTES

#: Minimum gap between two C2001 "not recognized" frames on one connection.
_STT_ERROR_RESEND_SECONDS = 10.0


class TurnSttFinishMixin:
    """Candidate voice round ending: STT, recovery, failure count; enter the round after successful clearing."""

    ctx: "ConnectionContext"

    if TYPE_CHECKING:
        # Members provided by sibling mixins of the composed InterviewWSHandler.
        _begin_user_turn: Callable[..., int | None]
        _end_user_turn: Callable[..., None]
        send: Callable[..., Coroutine[Any, Any, None]]
        set_turn: Callable[[TurnState], Coroutine[Any, Any, None]]
        _load_session: Callable[..., InterviewSession | None]
        rebind_runtime_session: Callable[..., None]
        restore_turn_timers_after_incomplete_turn: Callable[..., None]
        _process_user_text: Callable[..., Coroutine[Any, Any, None]]

    async def _run_user_turn_end(
        self,
        data: dict[str, Any],
    ) -> None:
        epoch = self._begin_user_turn()
        if epoch is None:
            logger.info(
                "user_turn_end lock busy sid=%s turn_busy=%s busy_epoch=%s stream_epoch=%s",
                self.ctx.session_id,
                self.ctx.turn_busy,
                self.ctx.busy_epoch,
                self.ctx.stream_epoch,
            )
            await self.send(
                "info",
                message=BUSY_TURN_NOTICE,
            )
            return
        db = SessionLocal()
        try:
            session = self._load_session(db)
            if not session:
                logger.warning("user_turn_end session missing sid=%s", self.ctx.session_id)
                await self.send(
                    "error",
                    message="Interview session not found; please re-enter the interview",
                    code="A2001",
                    retryable=False,
                )
                return
            self.rebind_runtime_session(session)
            await self._on_user_turn_end(data, db, session)
        except Exception:
            logger.exception("user_turn_end failed sid=%s", self.ctx.session_id)
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
                    "user_turn_end restore USER_SPEAKING failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
        finally:
            self._end_user_turn(epoch)
            try:
                db.close()
            except Exception:
                logger.debug(
                    "user_turn_end DB close failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )

    async def _on_user_turn_end(
        self, data: dict[str, Any], db: Session, session: InterviewSession
    ) -> None:
        if self.ctx.turn_state == TurnState.PROCESSING or self.ctx.turn_state == TurnState.AI_SPEAKING:
            # Never drop silently: the client cleared its input on send, so it
            # needs a frame explaining why the turn was not admitted. Drained
            # buffered audio cannot leak into the next turn's STT input.
            logger.info(
                "Ignore user_turn_end sid=%s during %s",
                self.ctx.session_id,
                self.ctx.turn_state.value,
            )
            self.ctx.audio_buffer = []
            self.ctx.audio_buffer_bytes = 0
            try:
                await self.send(
                    "info",
                    message=BUSY_TURN_NOTICE,
                )
            except Exception:
                # A dead socket must not leak into the epoch-restore handler.
                logger.debug(
                    "busy notice failed to send sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
            return
        await self.set_turn(TurnState.PROCESSING)

        # Inbound frames are untrusted: coerce to str like every other
        # dispatcher entry (a non-string ``text`` must not raise mid-turn),
        # then apply the same cap as the typed ``user_text`` path so one
        # oversized frame cannot reach the prompt, the ledger, or the LLM.
        browser_text = str(data.get("text") or "").strip()
        if len(browser_text) > MAX_USER_TEXT_CHARS:
            await self.send(
                "error",
                message=f"Text too long (limit: {MAX_USER_TEXT_CHARS} characters)",
                code="A0003",
            )
            await self.set_turn(TurnState.USER_SPEAKING)
            return
        pcm_b64 = data.get("pcm") or ""
        if isinstance(pcm_b64, str) and len(pcm_b64) > _AUDIO_BUFFER_MAX_BYTES:
            logger.warning(
                "user_turn_end pcm exceeds limit sid=%s len=%d",
                self.ctx.session_id,
                len(pcm_b64),
            )
            await self.send(
                "error",
                message="Audio too large; speak in shorter turns or type instead",
                code="A0004",
            )
            await self.set_turn(TurnState.USER_SPEAKING)
            return

        asr_text = ""
        stt_provider = ""
        if pcm_b64:
            raw_sr = data.get("sample_rate") or 16000
            try:
                sample_rate = int(raw_sr)
            except (TypeError, ValueError):
                sample_rate = 16000
            if sample_rate < 8000 or sample_rate > 96000:
                sample_rate = 16000
            stt_t0 = time.perf_counter()
            stt_result = await transcribe_utterance_result(
                pcm_b64,
                sample_rate=sample_rate,
                creds=self.ctx.stt_creds,
            )
            logger.info(
                "stt sid=%s ms=%.0f provider=%s fallback=%s chars=%d",
                self.ctx.session_id,
                (time.perf_counter() - stt_t0) * 1000.0,
                getattr(stt_result, "provider", "?"),
                getattr(stt_result, "fallback", False),
                len(getattr(stt_result, "text", "") or ""),
            )
            asr_text = stt_result.text
            stt_provider = getattr(stt_result, "provider", "") or ""
            if stt_result.fallback:
                await self.send(
                    "info",
                    message=(
                        f"Recognition fell back to {stt_result.provider}"
                        + (
                            f" (was configured as {stt_result.requested_provider})"
                            if stt_result.requested_provider
                            else ""
                        )
                    ),
                    fallback=True,
                    provider=stt_result.provider,
                    requested_provider=stt_result.requested_provider,
                )
        elif self.ctx.audio_buffer and not browser_text:
            pcm = "".join(self.ctx.audio_buffer)
            self.ctx.audio_buffer = []
            self.ctx.audio_buffer_bytes = 0
            if len(pcm) > _AUDIO_BUFFER_MAX_BYTES:
                await self.send(
                    "error",
                    message="Audio too large; speak in shorter turns or type instead",
                    code="A0004",
                )
                await self.set_turn(TurnState.USER_SPEAKING)
                return
            stt_t0 = time.perf_counter()
            stt_result = await transcribe_utterance_result(
                pcm,
                creds=self.ctx.stt_creds,
            )
            logger.info(
                "stt sid=%s ms=%.0f provider=%s fallback=%s chars=%d",
                self.ctx.session_id,
                (time.perf_counter() - stt_t0) * 1000.0,
                getattr(stt_result, "provider", "?"),
                getattr(stt_result, "fallback", False),
                len(getattr(stt_result, "text", "") or ""),
            )
            asr_text = stt_result.text
            stt_provider = getattr(stt_result, "provider", "") or ""
            if stt_result.fallback:
                await self.send(
                    "info",
                    message=f"Recognition fell back to {stt_result.provider}",
                    fallback=True,
                    provider=stt_result.provider,
                )
        elif self.ctx.audio_buffer:
            self.ctx.audio_buffer = []
            self.ctx.audio_buffer_bytes = 0

        text = _pick_stt_text(browser_text, asr_text)
        if text:
            if await self._reject_probable_echo(text):
                return
            await self.send("stt_final", text=text)
        else:
            # Back off the error frame: the candidate is silent (not deaf) —
            # the silence nudge owns follow-ups, so don't spam C2001. The turn
            # still returns to USER_SPEAKING either way.
            now = asyncio.get_event_loop().time()
            if now - self.ctx.last_stt_error_at >= _STT_ERROR_RESEND_SECONDS:
                self.ctx.last_stt_error_at = now
                message = "Could not recognize the speech; speak again or type instead"
                # A local model that failed to load always yields empty text;
                # telling the candidate to "speak again" would loop forever, so
                # surface the load failure instead (same C2001 code, so the
                # client-side STT-failure handling stays unchanged).
                load_error = (
                    local_stt_unavailable_reason() if stt_provider == "local" else None
                )
                if load_error:
                    message = (
                        "Local recognition is unavailable (model load failed: "
                        f"{load_error}); type instead or fix the local model"
                    )
                await self.send(
                    "error",
                    message=message,
                    code="C2001",
                    retryable=True,
                )
            await self.set_turn(TurnState.USER_SPEAKING)
            # Nothing was recognized — the candidate is still mid-answer: the
            # server-owned timers must survive STT failures, or follow-ups
            # would depend on the fragile client clock again.
            self.restore_turn_timers_after_incomplete_turn()
            return

        await self._process_user_text(text, data, db, session)

    def _last_assistant_content(self) -> str:
        """The most recent interviewer's statement in the message history (recovery judgment anchor point; compatible with dict/ORM format)."""
        history = self.ctx.runner.message_history() if self.ctx.runner else []
        if not history:
            return ""
        for m in reversed(history):
            role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)
            content = getattr(m, "content", None) or (
                m.get("content") if isinstance(m, dict) else None
            )
            if role == "assistant" and content:
                return str(content)
        return ""

    async def _reject_probable_echo(self, text: str) -> bool:
        """Loudspeaker response judgment: if hit, prompts to answer again and resume opening the microphone, returns True (the caller terminates the turn)."""
        last_assistant = self._last_assistant_content()
        if not last_assistant or not _is_echo_of_assistant(text, last_assistant):
            return False
        logger.warning(
            "Discard suspected recovery sid=%s text=%s",
            self.ctx.session_id,
            text[:80],
        )
        await self.send(
            "error",
            message="Possible echo of the interviewer audio; please speak again or type",
            code="C2001",
            retryable=True,
        )
        await self.set_turn(TurnState.USER_SPEAKING)
        self.restore_turn_timers_after_incomplete_turn()
        return True


__all__ = ["TurnSttFinishMixin", "_AUDIO_BUFFER_MAX_BYTES"]
