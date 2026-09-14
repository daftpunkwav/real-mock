"""End-of-turn STT (WS mixin): PCM limit / loopback-capture detection / recognition failure and turn admission.

Extracted from :mod:`...turn_coordinator`. The PCM and browser-text paths share the same
``transcribe_utterance_result`` binding (a module-level name here; tests
patch ``realmock.domains.interview.realtime.turn.stt_finish.transcribe_utterance_result``),
and finally share ``_pick_stt_text`` → loopback-capture detection → ``_process_user_text``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.platform.core.constants import AUDIO_BUFFER_MAX_BYTES
from realmock.platform.database import SessionLocal
from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.platform.capabilities.voice.stt import transcribe_utterance_result
from realmock.domains.interview.realtime.voice.pipeline import _is_echo_of_assistant, _pick_stt_text

if TYPE_CHECKING:
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)

# Single source: canonical value lives in platform.core.constants.
_AUDIO_BUFFER_MAX_BYTES: int = AUDIO_BUFFER_MAX_BYTES

#: Minimum gap between two C2001 "not recognized" frames on one connection.
_STT_ERROR_RESEND_SECONDS = 10.0


class TurnSttFinishMixin:
    """Candidate voice round ending: STT, recovery, failure count; enter the round after successful clearing."""

    ctx: "ConnectionContext"

    async def _run_user_turn_end(
        self,
        data: dict[str, Any],
    ) -> None:
        epoch = self._begin_user_turn()
        if epoch is None:
            return
        db = SessionLocal()
        try:
            session = self._load_session(db)
            if not session:
                return
            self.rebind_runtime_session(session)
            await self._on_user_turn_end(data, db, session)
        except Exception:
            logger.exception("user_turn_end failed sid=%s", self.ctx.session_id)
            try:
                if epoch == self.ctx.stream_epoch:
                    await self.set_turn(TurnState.USER_SPEAKING)
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
        if self.ctx.turn_state == TurnState.PROCESSING:
            return
        if self.ctx.turn_state == TurnState.AI_SPEAKING:
            logger.info("Ignore user_turn_end sid=%s during AI_SPEAKING", self.ctx.session_id)
            return
        await self.set_turn(TurnState.PROCESSING)

        browser_text = (data.get("text") or "").strip()
        pcm_b64 = data.get("pcm") or data.get("data") or ""
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
        if pcm_b64:
            raw_sr = data.get("sample_rate") or 16000
            try:
                sample_rate = int(raw_sr)
            except (TypeError, ValueError):
                sample_rate = 16000
            if sample_rate < 8000 or sample_rate > 96000:
                sample_rate = 16000
            stt_result = await transcribe_utterance_result(
                pcm_b64,
                sample_rate=sample_rate,
                creds=self.ctx.stt_creds,
            )
            asr_text = stt_result.text
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
            stt_result = await transcribe_utterance_result(
                pcm,
                creds=self.ctx.stt_creds,
            )
            asr_text = stt_result.text
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
            self.ctx.stt_fail_streak += 1
            # Back off the error frame: the candidate is silent (not deaf) —
            # the silence nudge owns follow-ups, so don't spam C2001. The turn
            # still returns to USER_SPEAKING either way.
            now = asyncio.get_event_loop().time()
            if now - self.ctx.last_stt_error_at >= _STT_ERROR_RESEND_SECONDS:
                self.ctx.last_stt_error_at = now
                await self.send(
                    "error",
                    message="Could not recognize the speech; speak again or type instead",
                    code="C2001",
                    retryable=True,
                )
            await self.set_turn(TurnState.USER_SPEAKING)
            return

        self.ctx.stt_fail_streak = 0
        await self._process_user_text(text, data, db, session)

    def _last_assistant_content(self) -> str:
        """The most recent interviewer's statement in the message history (recovery judgment anchor point; compatible with dict/ORM format)."""
        if not (self.ctx.agent and self.ctx.agent.messages):
            return ""
        for m in reversed(self.ctx.agent.messages):
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
        return True


__all__ = ["TurnSttFinishMixin", "_AUDIO_BUFFER_MAX_BYTES"]
