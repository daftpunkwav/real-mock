"""
@file factory.py
@description Factory for creating RealtimeAudioEngine instances based on configuration.

Responsibilities:
- Inspect session parameters or platform capabilities to select cascaded vs. native engine.
- Instantiate and configure the appropriate RealtimeAudioEngine instance.
"""

from __future__ import annotations

from typing import Any

from realmock.domains.interview.realtime.engine.base import AudioEngineMode, RealtimeAudioEngine
from realmock.domains.interview.realtime.engine.cascaded import CascadedAudioEngine
from realmock.domains.interview.realtime.engine.native import NativeRealtimeAudioEngine
from realmock.platform.capabilities.voice.tts import TtsCredentials
from realmock.platform.capabilities.voice.tts.voice_resolve import VoiceProsody


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
    normalized_mode = AudioEngineMode(mode) if isinstance(mode, str) else mode
    if normalized_mode == AudioEngineMode.NATIVE:
        return NativeRealtimeAudioEngine(
            model=native_model or "gpt-4o-realtime-preview",
            api_key=native_api_key,
            **kwargs,
        )
    return CascadedAudioEngine(prosody=prosody, tts_creds=tts_creds)
