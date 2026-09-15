"""
@file test_audio_engine.py
@description Unit tests for RealtimeAudioEngine abstractions and factory.
"""

import pytest
from realmock.domains.interview.realtime.engine import (
    AudioEngineEvent,
    AudioEngineMode,
    AudioEventKind,
    CascadedAudioEngine,
    NativeRealtimeAudioEngine,
    create_audio_engine,
)


@pytest.mark.asyncio
async def test_cascaded_audio_engine_lifecycle():
    engine = create_audio_engine(AudioEngineMode.CASCADED)
    assert engine.mode == AudioEngineMode.CASCADED
    assert isinstance(engine, CascadedAudioEngine)

    events: list[AudioEngineEvent] = []

    async def _handler(evt: AudioEngineEvent):
        events.append(evt)

    await engine.initialize(_handler)
    await engine.push_audio_chunk(b"\x00" * 320)
    await engine.finish_user_speech()
    await engine.interrupt()

    assert any(e.kind == AudioEventKind.INTERRUPTED for e in events)
    await engine.shutdown()


@pytest.mark.asyncio
async def test_native_audio_engine_lifecycle():
    engine = create_audio_engine(
        AudioEngineMode.NATIVE,
        native_model="gpt-4o-realtime-preview",
        native_api_key="test_key",
    )
    assert engine.mode == AudioEngineMode.NATIVE
    assert isinstance(engine, NativeRealtimeAudioEngine)

    events: list[AudioEngineEvent] = []

    async def _handler(evt: AudioEngineEvent):
        events.append(evt)

    await engine.initialize(_handler)
    await engine.push_audio_chunk(b"\x01" * 160)
    await engine.interrupt()

    assert any(e.kind == AudioEventKind.INTERRUPTED for e in events)
    await engine.shutdown()
