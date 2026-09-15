"""Realtime audio engine abstraction for the interview realtime domain.

Responsibilities:
- Define the abstract RealtimeAudioEngine contract for duplex and cascaded audio pipelines.
- Standardize audio chunking, interruption, and transcription events.
- Provide capability declarations for native multimodal vs. cascaded speech processing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


class AudioEngineMode(str, Enum):
    """Audio execution mode."""
    CASCADED = "cascaded"  # WebSpeech/Whisper -> LLM text -> Sentence TTS
    NATIVE = "native"      # End-to-end full duplex audio model (e.g. OpenAI Realtime / Gemini Live)


class AudioEventKind(str, Enum):
    """Event kinds emitted by the realtime audio engine."""
    TRANSCRIPTION_PARTIAL = "transcription_partial"
    TRANSCRIPTION_FINAL = "transcription_final"
    AUDIO_DELTA = "audio_delta"
    SPEECH_STARTED = "speech_started"
    SPEECH_STOPPED = "speech_stopped"
    INTERRUPTED = "interrupted"
    ERROR = "error"


@dataclass(frozen=True)
class AudioEngineEvent:
    """Standardized event emitted by RealtimeAudioEngine to the connection handler."""
    kind: AudioEventKind
    text: str = ""
    audio_bytes: bytes = b""
    sample_rate: int = 24000
    generation: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


EventHandler = Callable[[AudioEngineEvent], Coroutine[Any, Any, None]]


class RealtimeAudioEngine(ABC):
    """Abstract contract for Realtime Audio Engines (cascaded or native)."""

    @property
    @abstractmethod
    def mode(self) -> AudioEngineMode:
        """The operating mode of this engine."""
        raise NotImplementedError

    @abstractmethod
    async def initialize(self, event_handler: EventHandler) -> None:
        """Initialize the engine and bind the event emission handler."""
        raise NotImplementedError

    @abstractmethod
    async def push_audio_chunk(self, pcm_bytes: bytes) -> None:
        """Push raw microphone PCM audio bytes from the client to the engine."""
        raise NotImplementedError

    @abstractmethod
    async def finish_user_speech(self) -> str:
        """Notify the engine that candidate speech has completed and retrieve final text."""
        raise NotImplementedError

    @abstractmethod
    async def enqueue_tts(self, sentence: str, *, emotion: str = "neutral") -> None:
        """Enqueue speech synthesis (cascaded mode) or forward synthesized prompt."""
        raise NotImplementedError

    @abstractmethod
    async def interrupt(self) -> None:
        """Cancel ongoing speech synthesis or active model response immediately."""
        raise NotImplementedError

    @abstractmethod
    async def shutdown(self) -> None:
        """Release underlying resources, workers, or network streams."""
        raise NotImplementedError
