"""Voice pipeline: STT text selection, echo detection, and short-utterance TTS.

See :mod:`tts_queue` for the sentence-level TTS queue.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from realmock.domains.interview.agents import strip_markers
from realmock.platform.capabilities.voice.tts import TtsCredentials, synthesize_speech
from realmock.platform.capabilities.voice.tts.edge import (
    extract_emotion,
    _plain_text_for_tts,
)
from realmock.platform.capabilities.voice.tts.voice_resolve import VoiceProsody, with_emotion

logger = logging.getLogger(__name__)


def _latin_letter_ratio(text: str) -> float:
    """The proportion of Latin characters in letters is used to determine English content."""
    letters = [c for c in text if c.isalpha() or "\u4e00" <= c <= "\u9fff"]
    if not letters:
        return 0.0
    latin = sum(1 for c in letters if "a" <= c.lower() <= "z")
    return latin / len(letters)


def _pick_stt_text(browser_text: str, asr_text: str) -> str:
    """Merge browser preview and cloud/local ASR: Priority will be given to final drafts of ASR (Browser Chinese is often misunderstood)."""
    browser = (browser_text or "").strip()
    asr = (asr_text or "").strip()
    if asr and not browser:
        return asr
    if browser and not asr:
        return browser
    if not browser and not asr:
        return ""

    wr = _latin_letter_ratio(asr)
    br = _latin_letter_ratio(browser)
    # Browsers zh-CN often hear English as garbled characters; ASR is used when ASR detects obvious English.
    if wr >= 0.35 and br < 0.25:
        return asr
    if wr >= 0.5:
        return asr
    # Chinese/Hongshuo: Third-party ASR is accepted by default (browser only for preview)
    if len(asr) >= 2:
        return asr
    return browser


def _normalize_echo_text(text: str) -> str:
    import re

    return re.sub(r"[\s\*\#`~，。！？、,.!?;:：；\"'“”‘’\-—…（）()【】\[\]]+", "", text).lower()


def _is_echo_of_assistant(user_text: str, assistant_text: str) -> bool:
    """Whether the candidate text is highly like the previous sentence the interviewer spoke (speaker pick-back)."""
    from difflib import SequenceMatcher

    u = _normalize_echo_text(user_text or "")
    a = _normalize_echo_text(assistant_text or "")
    if len(u) < 12 or len(a) < 12:
        return False
    probe_u = u[: min(40, len(u))]
    probe_a = a[: min(40, len(a))]
    if probe_u in a or probe_a in u:
        return True
    if SequenceMatcher(None, u[:120], a[:120]).ratio() >= 0.55:
        return True
    short = u[: min(24, len(u))]
    if len(short) >= 12 and short in a:
        return True
    return False


class VoicePipelineMixin:
    """Short-utterance TTS; depends on ctx.tts_voice / ctx.session_prosody / ctx.tts_creds / send."""

    if TYPE_CHECKING:
        from realmock.domains.interview.realtime.core.context import ConnectionContext

    ctx: "ConnectionContext"

    async def _speak_one(self, sentence: str) -> None:
        clean = _plain_text_for_tts(strip_markers(sentence))
        if not clean:
            return
        base = self.ctx.session_prosody or VoiceProsody(voice=self.ctx.tts_voice)
        emo = extract_emotion(sentence)
        p = with_emotion(base, emo)
        try:
            tts_creds = self.ctx.tts_creds or TtsCredentials(
                handler="edge", voice=p.voice
            )
            synth_t0 = time.perf_counter()
            audio_b64 = await synthesize_speech(
                clean,
                creds=TtsCredentials(
                    handler=tts_creds.handler,
                    mode=tts_creds.mode,
                    protocol=tts_creds.protocol,
                    api_base=tts_creds.api_base,
                    api_key=tts_creds.api_key,
                    model=tts_creds.model,
                    voice=p.voice or tts_creds.voice,
                    fallback_handler=tts_creds.fallback_handler,
                    fallback_mode=tts_creds.fallback_mode,
                ),
                rate=p.rate,
                pitch=p.pitch,
            )
        except Exception as e:
            logger.error("TTS short sentence failed: %s", e)
            await self.send(
                "error",
                message="Speech synthesis failed; check network (text content still available)",
                code="C2002",
                retryable=True,
            )
            return
        logger.debug(
            "tts_synth sid=%s ms=%.0f chars=%d",
            self.ctx.session_id,
            (time.perf_counter() - synth_t0) * 1000.0,
            len(clean),
        )
        if audio_b64:
            await self._tts_send("tts_audio", data=audio_b64, sentence=clean)
            self._mark_tts_sent()
        else:
            await self.send(
                "tts_failed",
                message="Speech synthesis returned empty audio; check network or type instead",
            )
