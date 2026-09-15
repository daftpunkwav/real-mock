"""TTS queue tests for realtime/voice/tts_queue.py.

Covers: setters, enqueue/clear/overflow, worker success/failure/empty,
stop timeout cancel, flush with send failure, clear ValueError,
overflow-empty, generation mismatch before/after synth.
Conventions: no real network/LLM (all external calls mocked); no handler needed.
"""

import asyncio

import pytest
from unittest.mock import MagicMock, patch
from realmock.domains.interview.realtime.voice.tts_queue import _SentenceTTSQueue
from realmock.platform.capabilities.voice.tts import TtsCredentials
from realmock.platform.capabilities.voice.tts.voice_resolve import VoiceProsody

# No handler fixture: _SentenceTTSQueue is exercised directly with mocked synth/send callbacks.

@pytest.mark.asyncio
async def test_setters_enqueue_clear_overflow():
    q = _SentenceTTSQueue()
    q.set_prosody(VoiceProsody(voice="v1"))
    q.set_tts_creds(TtsCredentials(handler="edge", voice="v1"))
    cb = MagicMock()
    q.set_on_sent(cb)
    assert q._on_sent is cb
    await q.enqueue("   ")
    assert q._queue.qsize() == 0
    await q.enqueue("Hello.")
    assert q._queue.qsize() == 1
    for _ in range(55):
        await q.enqueue("Sentence.")
    assert q._queue.qsize() <= 50 and q._dropped_count >= 1
    await q.clear()
    assert q._queue.qsize() == 0
    await q.stop()


@pytest.mark.asyncio
async def test_worker_success_and_failed_and_empty():
    async def _ok(text, creds=None, rate="+0%", pitch="+0Hz"):
        return f"audio:{text}"
    with patch("realmock.domains.interview.realtime.voice.tts_queue.synthesize_speech", _ok):
        q = _SentenceTTSQueue()
        sent = []
        async def _send(t, **p):
            sent.append((t, p.get("sentence")))
        q.set_on_sent(MagicMock())
        await q.start(_send)
        await q.enqueue("Hi there.")
        await q.flush_remainder("")
        await q.stop()
        assert ("tts_audio", "Hi there.") in [(t, s) for t, s in sent]
    async def _fail(text, creds=None, rate="+0%", pitch="+0Hz"):
        raise RuntimeError("synth down")
    with patch("realmock.domains.interview.realtime.voice.tts_queue.synthesize_speech", _fail):
        q2 = _SentenceTTSQueue()
        errs = []
        async def _send2(t, **p):
            errs.append(t)
        await q2.start(_send2)
        await q2.enqueue("Hello world.")
        await q2.flush_remainder("")
        await q2.stop()
        assert "error" in errs
    async def _empty(text, creds=None, rate="+0%", pitch="+0Hz"):
        return ""
    with patch("realmock.domains.interview.realtime.voice.tts_queue.synthesize_speech", _empty):
        q3 = _SentenceTTSQueue()
        got = []
        async def _send3(t, **p):
            got.append(t)
        await q3.start(_send3)
        await q3.enqueue("Hello world again.")
        await q3.flush_remainder("")
        await q3.stop()
        assert "tts_failed" in got


@pytest.mark.asyncio
async def test_stop_timeout_cancels_worker():
    async def _slow(text, creds=None, rate="+0%", pitch="+0Hz"):
        await asyncio.sleep(5)
        return "x"
    with patch("realmock.domains.interview.realtime.voice.tts_queue.synthesize_speech", _slow):
        q = _SentenceTTSQueue()
        q._STOP_GRACE_SECONDS = 0.05
        async def _send(t, **p):
            pass
        await q.start(_send)
        await q.enqueue("Long sentence for timeout.")
        await asyncio.sleep(0.05)
        await q.stop()
        assert q._worker_task is None or q._worker_task.done()


@pytest.mark.asyncio
async def test_flush_with_text_and_send_fail():
    async def _ok(text, creds=None, rate="+0%", pitch="+0Hz"):
        return "audio:x"
    with patch("realmock.domains.interview.realtime.voice.tts_queue.synthesize_speech", _ok):
        q = _SentenceTTSQueue()
        async def _bad_send(t, **p):
            raise RuntimeError("send down")
        await q.start(_bad_send)
        await q.flush_remainder("Hello world flush.")
        await q.stop()
        q._queue.put_nowait(None)
        await q.clear()


@pytest.mark.asyncio
async def test_tts_clear_value_error_branch() -> None:
    q = _SentenceTTSQueue()
    q._queue.put_nowait(("hello", "neutral"))

    orig_done = q._queue.task_done

    def _boom():
        raise ValueError("no unfinished")

    q._queue.task_done = _boom  # type: ignore[method-assign]
    await q.clear()
    q._queue.task_done = orig_done  # type: ignore[method-assign]
    await q.stop()


@pytest.mark.asyncio
async def test_tts_enqueue_overflow_empty_branch() -> None:
    q = _SentenceTTSQueue()
    q._MAX_QUEUE_SIZE = 0  # type: ignore[assignment]
    await q.enqueue("Hello world.")
    assert q._queue.qsize() == 1
    await q.clear()
    await q.stop()


@pytest.mark.asyncio
async def test_tts_worker_gen_mismatch_before_synth(monkeypatch) -> None:
    from realmock.domains.interview.realtime.voice import tts_queue as mod

    async def _ok(text, creds=None, rate="+0%", pitch="+0Hz"):
        return "audio:x"

    monkeypatch.setattr(mod, "synthesize_speech", _ok)
    q = _SentenceTTSQueue()

    orig_with_emotion = mod.with_emotion

    def _bump(prosody, emotion):
        q._speak_gen += 1
        return orig_with_emotion(prosody, emotion)

    monkeypatch.setattr(mod, "with_emotion", _bump)
    sent: list = []

    async def _send(t, **p):
        sent.append(t)

    await q.start(_send)
    await q.enqueue("Hello world again.")
    await q.flush_remainder("")
    await q.stop()
    assert sent == []


@pytest.mark.asyncio
async def test_tts_worker_send_failure_branches() -> None:
    from realmock.domains.interview.realtime.voice import tts_queue as mod

    async def _fail(text, creds=None, rate="+0%", pitch="+0Hz"):
        raise RuntimeError("synth down")

    async def _bad_send(t, **p):
        raise RuntimeError("send down")

    with patch.object(mod, "synthesize_speech", _fail):
        q = _SentenceTTSQueue()

        async def _send(t, **p):
            raise RuntimeError("send down")

        await q.start(_send)
        await q.enqueue("Hello world.")
        await q.flush_remainder("")
        await q.stop()

    async def _empty(text, creds=None, rate="+0%", pitch="+0Hz"):
        return ""

    with patch.object(mod, "synthesize_speech", _empty):
        q2 = _SentenceTTSQueue()
        await q2.start(_bad_send)
        await q2.enqueue("Hello world again.")
        await q2.flush_remainder("")
        await q2.stop()


@pytest.mark.asyncio
async def test_tts_worker_gen_mismatch_after_synth(monkeypatch) -> None:
    from realmock.domains.interview.realtime.voice import tts_queue as mod

    async def _bump_synth(text, creds=None, rate="+0%", pitch="+0Hz"):
        # Simulate interruption during synthesis: stale result must be dropped (184).
        q_ref[0]._speak_gen += 1
        return "audio:x"

    q = _SentenceTTSQueue()
    q_ref = [q]
    monkeypatch.setattr(mod, "synthesize_speech", _bump_synth)
    sent: list = []

    async def _send(t, **p):
        sent.append(t)

    await q.start(_send)
    await q.enqueue("Hello world.")
    await q.flush_remainder("")
    await q.stop()
    assert "tts_audio" not in sent


# ---- streaming (97, 105, 144, 146-149, 151, 170) ----

