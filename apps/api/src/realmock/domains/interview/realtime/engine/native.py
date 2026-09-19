"""Native duplex realtime audio engine adapter skeleton.

Responsibilities:
- Provide the full-duplex streaming bridge for native speech-to-speech models (OpenAI Realtime / Gemini Live).
- Manage client PCM streaming uplink and server audio delta downlink.
- Handle server VAD, speech-started, speech-stopped, and instantaneous barge-in cancellation.
"""

from __future__ import annotations

import asyncio
import logging

from realmock.domains.interview.realtime.engine.base import (
    AudioEngineEvent,
    AudioEngineMode,
    AudioEventKind,
    EventHandler,
    RealtimeAudioEngine,
)

logger = logging.getLogger(__name__)

# Max inbound queue size to prevent memory leaks during slow uplink consumer processing
_MAX_INBOUND_FRAMES = 500


class NativeRealtimeAudioEngine(RealtimeAudioEngine):
    """Native end-to-end full duplex audio engine adapter.

    Prepares the infrastructure for OpenAI Realtime API (ws:// / WebRTC) or Gemini Live API.
    """

    def __init__(
        self,
        *,
        model: str = "gpt-4o-realtime-preview",
        voice: str = "alloy",
        sample_rate: int = 24000,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.voice = voice
        self.sample_rate = sample_rate
        self.api_key = api_key
        self._event_handler: EventHandler | None = None
        self._is_active = False
        self._generation = 0
        self._inbound_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=_MAX_INBOUND_FRAMES)

    @property
    def mode(self) -> AudioEngineMode:
        return AudioEngineMode.NATIVE

    async def initialize(self, event_handler: EventHandler) -> None:
        self._event_handler = event_handler
        self._is_active = True
        logger.info(
            "NativeRealtimeAudioEngine initialized for model=%s voice=%s sample_rate=%d",
            self.model,
            self.voice,
            self.sample_rate,
        )

    async def push_audio_chunk(self, pcm_bytes: bytes) -> None:
        """Forward PCM audio chunks directly to the model input audio buffer."""
        if not self._is_active:
            return
        try:
            self._inbound_queue.put_nowait(pcm_bytes)
        except asyncio.QueueFull:
            logger.warning("Native inbound audio queue full; dropping frame")

    async def finish_user_speech(self) -> str:
        """Commit user audio buffer to trigger native model inference."""
        if not self._is_active:
            return ""
        # In native protocol, server VAD or client commit initiates response.create
        return ""

    async def enqueue_tts(self, sentence: str, *, emotion: str = "neutral") -> None:
        """In native duplex mode, speech is synthesized natively alongside text generation.

        This method supports injecting synthetic text prompts or system instructions.
        """
        logger.debug("Native engine prompt injection: %s (emotion=%s)", sentence, emotion)

    async def interrupt(self) -> None:
        """Trigger native barge-in: cancel active response generation and truncate buffer."""
        self._generation += 1
        # Drain pending inbound queue
        while not self._inbound_queue.empty():
            try:
                self._inbound_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        if self._event_handler:
            try:
                await self._event_handler(
                    AudioEngineEvent(
                        kind=AudioEventKind.INTERRUPTED,
                        generation=self._generation,
                    )
                )
            except Exception as exc:
                logger.warning("Native audio engine failed to dispatch interrupt event: %s", exc)

    async def shutdown(self) -> None:
        self._is_active = False
        while not self._inbound_queue.empty():
            try:
                self._inbound_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
