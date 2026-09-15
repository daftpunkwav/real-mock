"""Engine base tests for realtime/engine/base.py.

Covers: abstract contract where every method raises NotImplementedError.
Conventions: no real network/LLM (all external calls mocked); uses _Concrete stub for the abstract base.
"""

import pytest
from realmock.domains.interview.realtime.engine.base import AudioEngineMode, RealtimeAudioEngine
from realmock.platform.core.ratelimit import reset_rate_limit

@pytest.fixture(autouse=True)
def _clean_limits():
    """Reset rate limits around each test for isolation."""
    reset_rate_limit()
    yield
    reset_rate_limit()


class _Concrete(RealtimeAudioEngine):
    """Concrete subclass delegating to the abstract base to hit raise branches."""

    @property
    def mode(self):  # type: ignore[override]
        return super().mode

    async def initialize(self, event_handler):  # type: ignore[override]
        return await super().initialize(event_handler)

    async def push_audio_chunk(self, pcm_bytes):  # type: ignore[override]
        return await super().push_audio_chunk(pcm_bytes)

    async def finish_user_speech(self):  # type: ignore[override]
        return await super().finish_user_speech()

    async def enqueue_tts(self, sentence, *, emotion="neutral"):  # type: ignore[override]
        return await super().enqueue_tts(sentence, emotion=emotion)

    async def interrupt(self):  # type: ignore[override]
        return await super().interrupt()

    async def shutdown(self):  # type: ignore[override]
        return await super().shutdown()

@pytest.mark.asyncio
async def test_engine_base_all_raises() -> None:
    eng = _Concrete()
    with pytest.raises(NotImplementedError):
        eng.mode
    with pytest.raises(NotImplementedError):
        await eng.initialize(None)  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError):
        await eng.push_audio_chunk(b"\x00\x01")
    with pytest.raises(NotImplementedError):
        await eng.finish_user_speech()
    with pytest.raises(NotImplementedError):
        await eng.enqueue_tts("hi")
    with pytest.raises(NotImplementedError):
        await eng.interrupt()
    with pytest.raises(NotImplementedError):
        await eng.shutdown()
    assert AudioEngineMode.CASCADED.value == "cascaded"

