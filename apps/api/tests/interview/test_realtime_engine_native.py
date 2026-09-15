"""Native engine tests for realtime/engine/native.py.

Covers: push inactive noop, finish inactive, initialize/queue-full drop,
TTS enqueue, interrupt dispatch/raise/no-handler, shutdown, queue-empty race.
Conventions: no real network/LLM (all external calls mocked); no handler needed.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from realmock.domains.interview.realtime.engine.base import AudioEngineMode, AudioEventKind
from realmock.domains.interview.realtime.engine.native import NativeRealtimeAudioEngine

# No handler fixture: NativeRealtimeAudioEngine is exercised directly with mocked callbacks.

@pytest.mark.asyncio
async def test_native_engine_branches():
    eng = NativeRealtimeAudioEngine(model="m", voice="v", sample_rate=16000, api_key="k")
    assert eng.mode == AudioEngineMode.NATIVE
    # push inactive -> noop
    await eng.push_audio_chunk(b"abc")
    assert eng._inbound_queue.empty()
    # finish inactive -> ""
    assert await eng.finish_user_speech() == ""
    await eng.initialize(AsyncMock())
    assert eng._is_active is True
    await eng.push_audio_chunk(b"abc")
    assert not eng._inbound_queue.empty()
    # queue full -> drop with warning
    for _ in range(600):
        await eng.push_audio_chunk(b"x" * 10)
    assert eng._inbound_queue.qsize() <= 500
    assert await eng.finish_user_speech() == ""
    await eng.enqueue_tts("hello", emotion="happy")
    # interrupt drains + dispatches
    events = []

    async def _h(ev):
        events.append(ev)

    eng._event_handler = _h  # type: ignore[assignment]
    await eng.push_audio_chunk(b"z")
    await eng.interrupt()
    assert events and events[-1].kind == AudioEventKind.INTERRUPTED
    # interrupt handler raises -> swallowed
    async def _boom(ev):
        raise RuntimeError("boom")

    eng._event_handler = _boom  # type: ignore[assignment]
    await eng.interrupt()
    # interrupt without handler
    eng._event_handler = None
    await eng.interrupt()
    await eng.shutdown()
    assert eng._is_active is False
    assert eng._inbound_queue.empty()


@pytest.mark.asyncio
async def test_native_queueempty_race_interrupt_and_shutdown():
    eng = NativeRealtimeAudioEngine()
    await eng.initialize(AsyncMock())
    # force empty()->False then get_nowait raises -> hits except break
    eng._inbound_queue.empty = MagicMock(return_value=False)  # type: ignore[method-assign]
    eng._inbound_queue.get_nowait = MagicMock(side_effect=asyncio.QueueEmpty())  # type: ignore[method-assign]
    await eng.interrupt()  # covers native.py 96-97
    await eng.shutdown()  # covers native.py 112-115
    assert eng._is_active is False

