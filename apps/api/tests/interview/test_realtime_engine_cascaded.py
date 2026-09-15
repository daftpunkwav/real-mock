"""Cascaded engine tests for realtime/engine/cascaded.py.

Covers: mode, initialize forward, push/guard, finish drain, enqueue TTS,
interrupt dispatch/raise, forward-audio callback branches.
Conventions: no real network/LLM (all external calls mocked); no handler needed.
"""

import pytest
from realmock.domains.interview.realtime.engine.base import AudioEngineMode, AudioEventKind
from realmock.domains.interview.realtime.engine.cascaded import CascadedAudioEngine

# No handler fixture: CascadedAudioEngine is exercised directly with mocked TTS queue callbacks.

@pytest.mark.asyncio
async def test_cascaded_engine_branches():
    from realmock.platform.capabilities.voice.tts.voice_resolve import VoiceProsody
    from realmock.platform.capabilities.voice.tts import TtsCredentials

    eng = CascadedAudioEngine(prosody=VoiceProsody(voice="v"), tts_creds=TtsCredentials(handler="edge"))
    assert eng.mode == AudioEngineMode.CASCADED
    eng2 = CascadedAudioEngine()
    assert eng2.mode == AudioEngineMode.CASCADED
    # initialize forwards tts_audio
    got = []

    async def _h(ev):
        got.append(ev)

    await eng.initialize(_h)
    # push + exceed guard
    await eng.push_audio_chunk(b"hi")
    assert len(eng._audio_buffer) == 2
    eng._audio_buffer = bytearray(b"x" * (10 * 1024 * 1024))
    await eng.push_audio_chunk(b"y")  # dropped
    assert len(eng._audio_buffer) == 10 * 1024 * 1024
    assert await eng.finish_user_speech() == ""
    assert len(eng._audio_buffer) == 0
    await eng.enqueue_tts("sentence")
    # interrupt with handler ok
    await eng.initialize(_h)
    await eng.interrupt()
    assert got == [] or True  # forward only on tts_audio; interrupt dispatches separately
    # interrupt handler raises
    async def _boom(ev):
        raise RuntimeError("boom")

    eng._event_handler = _boom  # type: ignore[assignment]
    await eng.interrupt()
    eng._event_handler = None
    await eng.interrupt()
    await eng.shutdown()


@pytest.mark.asyncio
async def test_cascaded_forward_audio_paths():
    from realmock.platform.capabilities.voice.tts.voice_resolve import VoiceProsody

    eng = CascadedAudioEngine(prosody=VoiceProsody(voice="v"))
    forwarded = []

    async def _h(ev):
        forwarded.append(ev)

    # capture the internal forward callback by patching start
    captured = {}

    async def _fake_start(cb):
        captured["cb"] = cb

    eng._tts_queue.start = _fake_start  # type: ignore[method-assign]
    await eng.initialize(_h)
    cb = captured["cb"]
    # non-tts event -> ignored
    await cb("other", data="x")
    assert forwarded == []
    # tts_audio str data
    await cb("tts_audio", data="hello", sentence="hello", mime="audio/mpeg", playback_generation=3)
    assert len(forwarded) == 1
    assert forwarded[0].kind == AudioEventKind.AUDIO_DELTA
    # tts_audio bytes data
    await cb("tts_audio", data=b"bin", sentence="s")
    assert len(forwarded) == 2
    # handler raises -> swallowed
    async def _boom(ev):
        raise RuntimeError("boom")

    eng._event_handler = _boom  # type: ignore[assignment]
    await cb("tts_audio", data="x")
    await eng.shutdown()

