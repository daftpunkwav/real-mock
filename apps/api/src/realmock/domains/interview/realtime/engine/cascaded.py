"""Cascaded realtime audio engine implementation (ASR -> LLM -> Sentence TTS).

Responsibilities:
- Wrap the sentence-level TTS queue and ASR audio ingestion into RealtimeAudioEngine.
- Emit standardized audio events (transcriptions, playback audio frames, interruptions).
- Provide low-latency pipelined synthesis without blocking conversational turns.
"""

from __future__ import annotations

import logging
from typing import Any

from realmock.domains.interview.realtime.engine.base import (
    AudioEngineEvent,
    AudioEngineMode,
    AudioEventKind,
    EventHandler,
    RealtimeAudioEngine,
)
from realmock.domains.interview.realtime.voice.tts_queue import _SentenceTTSQueue
from realmock.platform.capabilities.voice.tts import TtsCredentials
from realmock.platform.capabilities.voice.tts.voice_resolve import VoiceProsody

logger = logging.getLogger(__name__)

# Defense against runaway uncommitted audio buffers (10 MB ceiling)
_MAX_AUDIO_BUFFER_BYTES = 10 * 1024 * 1024


class CascadedAudioEngine(RealtimeAudioEngine):
    """Cascaded audio engine using ASR and sentence-level serial TTS."""

    def __init__(
        self,
        *,
        prosody: VoiceProsody | None = None,
        tts_creds: TtsCredentials | None = None,
    ) -> None:
        self._tts_queue = _SentenceTTSQueue()
        if prosody is not None:
            self._tts_queue.set_prosody(prosody)
        if tts_creds is not None:
            self._tts_queue.set_tts_creds(tts_creds)
        self._event_handler: EventHandler | None = None
        self._audio_buffer = bytearray()
        self._generation = 0

    @property
    def mode(self) -> AudioEngineMode:
        return AudioEngineMode.CASCADED

    async def initialize(self, event_handler: EventHandler) -> None:
        self._event_handler = event_handler

        async def _forward_audio(event_type: str, **kwargs: Any) -> None:
            if event_type == "tts_audio" and self._event_handler:
                try:
                    await self._event_handler(
                        AudioEngineEvent(
                            kind=AudioEventKind.AUDIO_DELTA,
                            audio_bytes=kwargs.get("data", "").encode("utf-8") if isinstance(kwargs.get("data"), str) else kwargs.get("data", b""),
                            generation=kwargs.get("playback_generation", self._generation),
                            metadata={"sentence": kwargs.get("sentence", ""), "mime": kwargs.get("mime", "audio/mpeg")},
                        )
                    )
                except Exception as exc:
                    logger.warning("Cascaded audio engine failed to dispatch audio event: %s", exc)

        await self._tts_queue.start(_forward_audio)

    async def push_audio_chunk(self, pcm_bytes: bytes) -> None:
        if len(self._audio_buffer) < _MAX_AUDIO_BUFFER_BYTES:
            self._audio_buffer.extend(pcm_bytes)
        else:
            logger.warning("Cascaded audio buffer exceeded %d bytes; dropping incoming chunk", _MAX_AUDIO_BUFFER_BYTES)

    async def finish_user_speech(self) -> str:
        # Buffer reset upon speech completion; final transcription handled by caller/ASR service
        self._audio_buffer.clear()
        return ""

    async def enqueue_tts(self, sentence: str, *, emotion: str = "neutral") -> None:
        await self._tts_queue.enqueue(sentence, emotion=emotion)

    async def interrupt(self) -> None:
        self._generation += 1
        await self._tts_queue.clear()
        if self._event_handler:
            try:
                await self._event_handler(
                    AudioEngineEvent(
                        kind=AudioEventKind.INTERRUPTED,
                        generation=self._generation,
                    )
                )
            except Exception as exc:
                logger.warning("Cascaded audio engine failed to dispatch interrupt event: %s", exc)

    async def shutdown(self) -> None:
        await self._tts_queue.stop()
        self._audio_buffer.clear()
