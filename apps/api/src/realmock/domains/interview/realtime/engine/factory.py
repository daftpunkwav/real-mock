"""Factory for creating RealtimeAudioEngine instances based on configuration.

Responsibilities:
- Inspect session parameters or platform capabilities to select cascaded vs. native engine.
- Instantiate and configure the appropriate RealtimeAudioEngine instance with safe fallbacks.
"""

from __future__ import annotations

import logging
from typing import Any

from realmock.domains.interview.realtime.engine.base import AudioEngineMode, RealtimeAudioEngine
from realmock.domains.interview.realtime.engine.cascaded import CascadedAudioEngine
from realmock.domains.interview.realtime.engine.native import NativeRealtimeAudioEngine
from realmock.platform.capabilities.voice.tts import TtsCredentials
from realmock.platform.capabilities.voice.tts.voice_resolve import VoiceProsody

logger = logging.getLogger(__name__)


def create_audio_engine(
    mode: AudioEngineMode | str = AudioEngineMode.CASCADED,
    *,
    prosody: VoiceProsody | None = None,
    tts_creds: TtsCredentials | None = None,
    native_model: str | None = None,
    native_api_key: str | None = None,
    **kwargs: Any,
) -> RealtimeAudioEngine:
    """Factory to instantiate the appropriate RealtimeAudioEngine."""
    try:
        normalized_mode = AudioEngineMode(mode) if isinstance(mode, str) else mode
    except (ValueError, KeyError):
        logger.warning("Unknown audio engine mode %r; falling back to CASCADED", mode)
        normalized_mode = AudioEngineMode.CASCADED

    if normalized_mode == AudioEngineMode.NATIVE:
        return NativeRealtimeAudioEngine(
            model=native_model or "gpt-4o-realtime-preview",
            api_key=native_api_key,
            **kwargs,
        )
    return CascadedAudioEngine(prosody=prosody, tts_creds=tts_creds)
