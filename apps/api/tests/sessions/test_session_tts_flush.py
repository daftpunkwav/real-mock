"""Session fix: TTS flush_remainder actually drains the queue."""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_flush_waits_for_all_enqueued(monkeypatch: pytest.MonkeyPatch) -> None:
    from realmock.domains.interview.realtime.voice.tts_queue import _SentenceTTSQueue

    order: list[str] = []
    delays = {"Hello.": 0.05, "Second sentence.": 0.05, "Third sentence.": 0.05}

    async def slow_synth(sentence: str, *, creds=None, rate="+0%", pitch="+0Hz", emotion="neutral") -> str:
        await asyncio.sleep(delays.get(sentence, 0.01))
        return f"audio:{sentence}"

    monkeypatch.setattr(
        "realmock.domains.interview.realtime.voice.tts_queue.synthesize_speech",
        slow_synth,
    )

    async def send_cb(msg_type, **payload):
        order.append(payload["sentence"])

    q = _SentenceTTSQueue()
    await q.start(send_cb)
    await q.enqueue("Hello.")
    await q.enqueue("Second sentence.")
    await q.enqueue("Third sentence.")
    await q.flush_remainder("")
    # The entire queue should be processed when flush returns
    assert order == ["Hello.", "Second sentence.", "Third sentence."]
    await q.stop()


@pytest.mark.asyncio
async def test_flush_remainder_enqueues_trailing(monkeypatch: pytest.MonkeyPatch) -> None:
    from realmock.domains.interview.realtime.voice.tts_queue import _SentenceTTSQueue

    sent: list[str] = []

    async def synth(sentence: str, *, creds=None, rate="+0%", pitch="+0Hz", emotion="neutral") -> str:
        return f"a:{sentence}"

    monkeypatch.setattr("realmock.domains.interview.realtime.voice.tts_queue.synthesize_speech", synth)

    async def send_cb(msg_type, **payload):
        sent.append(payload["sentence"])

    q = _SentenceTTSQueue()
    await q.start(send_cb)
    await q.flush_remainder("Final sentence.")
    await q.stop()
    assert sent == ["Final sentence."]
