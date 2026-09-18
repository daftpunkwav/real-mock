"""TTS serial-queue unit tests.

Patch synthesize_speech to verify that queued playback is serialized without blocking enqueue operations.
"""

from __future__ import annotations

import asyncio

from realmock.domains.interview.realtime.voice.tts_queue import _SentenceTTSQueue


async def _fake_synth(sentence: str, *, creds=None, rate="+0%", pitch="+0Hz", emotion="neutral") -> str:
    return f"audio:{sentence}"


async def test_enqueue_processes_in_order(monkeypatch) -> None:
    monkeypatch.setattr(
        "realmock.domains.interview.realtime.voice.tts_queue.synthesize_speech", _fake_synth,
    )

    sent: list[tuple[str, str]] = []

    async def send_cb(msg_type, **payload):
        sent.append((payload["sentence"], payload["data"]))

    q = _SentenceTTSQueue()
    await q.start(send_cb)
    await q.enqueue("Hello.")
    await q.enqueue("Welcome to the interview.")
    await q.flush_remainder("")
    await q.stop()

    assert sent == [
        ("Hello.", "audio:Hello."),
        ("Welcome to the interview.", "audio:Welcome to the interview."),
    ]


async def test_enqueue_skips_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        "realmock.domains.interview.realtime.voice.tts_queue.synthesize_speech", _fake_synth,
    )
    sent: list[str] = []

    async def send_cb(msg_type, **payload):
        sent.append(payload["sentence"])

    q = _SentenceTTSQueue()
    await q.start(send_cb)
    await q.enqueue("   ")
    await q.enqueue("")
    await q.flush_remainder("  ")
    await q.stop()

    assert sent == []


async def test_enqueue_does_not_block_producer(monkeypatch) -> None:
    """Enqueue operations should be non-blocking so producers are not delayed by TTS synthesis."""

    async def slow_synth(sentence, *, creds=None, rate="+0%", pitch="+0Hz", emotion="neutral"):
        await asyncio.sleep(0.2)
        return f"audio:{sentence}"

    monkeypatch.setattr(
        "realmock.domains.interview.realtime.voice.tts_queue.synthesize_speech", slow_synth,
    )

    sent: list[str] = []

    async def send_cb(msg_type, **payload):
        sent.append(payload["sentence"])

    q = _SentenceTTSQueue()
    await q.start(send_cb)

    import time

    t0 = time.monotonic()
    for i in range(5):
        await q.enqueue(f"Sentence{i}。")
    elapsed = time.monotonic() - t0

    # Five enqueue operations should not be blocked by TTS synthesis and should take < 0.1s
    assert elapsed < 0.1, f"Enqueue latency too high: {elapsed:.3f}s"

    await q.flush_remainder("")
    await q.stop()

    assert len(sent) == 5


async def test_enqueue_overflow_drops_and_notifies() -> None:
    events: list[tuple[str, dict]] = []

    async def send_cb(msg_type, **payload):
        events.append((msg_type, payload))

    q = _SentenceTTSQueue()
    q._MAX_QUEUE_SIZE = 3
    await q.start(send_cb)

    for i in range(5):
        await q.enqueue(f"Sentence {i}")

    await asyncio.sleep(0.05)
    await q.stop()

    info_events = [e for e in events if e[0] == "info"]
    assert len(info_events) >= 1
    assert "latency" in info_events[0][1]["message"]
    assert q._dropped_count == 2

