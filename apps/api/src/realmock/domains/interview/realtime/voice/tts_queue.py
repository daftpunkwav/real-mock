"""Sentence-level serial TTS queue (_SentenceTTSQueue).

Synthesizes and plays sentences one at a time in arrival order without blocking the LLM stream.
Memory management: when the queue length exceeds ``_MAX_QUEUE_SIZE``, discard the oldest sentence
to prevent unbounded memory growth when TTS is slow or the network is unstable.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Any

from realmock.platform.config import get_settings
from realmock.domains.interview.agents import strip_markers
from realmock.platform.capabilities.voice.tts import TtsCredentials, synthesize_speech
from realmock.platform.capabilities.voice.tts.providers.edge import (
    extract_emotion,
    _plain_text_for_tts,
)
from realmock.platform.capabilities.voice.tts.voice_resolve import VoiceProsody, with_emotion

logger = logging.getLogger(__name__)


class _SentenceTTSQueue:
    """Serial TTS queue: Ensure that sentences are synthesized and played one by one in the order of arrival, without blocking each other with the LLM stream."""

    # Bound queue to 50 sentences; drop oldest on overflow.
    _MAX_QUEUE_SIZE: int = 50

    # stop() waits for the grace period for workers to consume sentinels; if the synthesis is stuck and exceeds this time, it will be canceled directly.
    # worker (the caller's outer wait_for in lifecycle is 5s, so this must be shorter for the internal fallback to get a chance to run)
    _STOP_GRACE_SECONDS: float = 3.0

    def __init__(self) -> None:
        # (text, emotion) ;None ends with sentinel
        self._queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._dropped_count = 0
        self._prosody: VoiceProsody = VoiceProsody(voice=get_settings().tts_voice)
        self._fail_count = 0
        self._on_sent: Any = None
        self._speak_gen: int = 0
        self._tts_creds: TtsCredentials = TtsCredentials(handler="edge")
        self._send: Any = None

    def set_prosody(self, prosody: VoiceProsody) -> None:
        """Tie the baseline timbre and rhythm of this session."""
        self._prosody = prosody
        self._tts_creds.voice = prosody.voice

    def set_tts_creds(self, creds: TtsCredentials) -> None:
        """Bind the speech output processor credentials."""
        self._tts_creds = creds

    def set_on_sent(self, callback) -> None:
        """Callback every time a tts_audio is successfully sent (used to wait for the client to finish playing)."""
        self._on_sent = callback

    async def start(self, send_callback) -> None:
        """Starts the background worker; called once per WS connection initialization."""
        self._send = send_callback
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker())

    async def clear(self) -> None:
        """Candidate interruption: Discard unplayed sentences and invalidate synthesis in progress."""
        self._speak_gen += 1
        drained = 0
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is not None:
                drained += 1
            try:
                self._queue.task_done()
            except ValueError:
                pass
        if drained:
            logger.info("TTS queue cleared due to interruption %d sentence", drained)

    async def stop(self) -> None:
        """Stop the worker and discard sentences that have not been played.

        Empty the queue, then send the sentinel and wait for the worker to exit naturally; if the worker remains stuck in synthesis
        beyond the grace period, cancel it explicitly so it does not become an orphaned task retaining a connection reference.
        """
        await self.clear()
        if self._worker_task is not None and not self._worker_task.done():
            await self._queue.put(None)
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._worker_task),
                    timeout=self._STOP_GRACE_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning("TTS worker stop timeout, forced cancellation of sid level queue")
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
        if self._dropped_count:
            logger.info("TTS queue discards %d sentences (exceeds the upper limit)", self._dropped_count)

    async def enqueue(self, sentence: str, emotion: str | None = None) -> None:
        """Queue one sentence for serial synthesis (drops oldest past 50).

        Args:
            sentence: Raw sentence text (marker-stripped; empties skipped).
            emotion: Prosody hint; auto-detected from the text when omitted.
        """
        emo = (emotion or extract_emotion(sentence) or "neutral").strip().lower()
        clean = _plain_text_for_tts(strip_markers(sentence)).strip()
        if not clean:
            return
        # When the queue is too long, the oldest old sentences are discarded to avoid memory expansion.
        if self._queue.qsize() >= self._MAX_QUEUE_SIZE:
            try:
                dropped = self._queue.get_nowait()
                self._queue.task_done()
                self._dropped_count += 1
                dropped_snippet = dropped[0][:30] if dropped else "None"
                logger.warning(
                    "TTS queue overflow (size=%d >= %d), dropping oldest sentence: %r (total dropped: %d)",
                    self._queue.qsize() + 1,
                    self._MAX_QUEUE_SIZE,
                    dropped_snippet,
                    self._dropped_count,
                )
                if self._send is not None and self._dropped_count == 1:
                    try:
                        notify = asyncio.create_task(
                            self._send(
                                "info",
                                message="Speech synthesis queue is experiencing high latency; some audio segments skipped (text is preserved).",
                            )
                        )
                        # Fire-and-forget without losing failures: consume the
                        # result so a send-side error cannot surface as an
                        # unretrieved task exception.
                        def _consume_notify_result(t: asyncio.Task) -> None:
                            try:
                                exc = t.exception()
                            except asyncio.CancelledError:
                                return
                            if exc is not None:
                                logger.debug("TTS overflow info notify failed: %s", exc)

                        notify.add_done_callback(_consume_notify_result)
                    except Exception:
                        logger.debug("TTS overflow info notify spawn failed", exc_info=True)
            except asyncio.QueueEmpty:
                pass
        await self._queue.put((clean, emo))

    async def flush_remainder(self, sentence: str, emotion: str | None = None) -> None:
        """At the end of the round, add the remaining buffer to the queue and wait for the queue to be processed."""
        if sentence.strip():
            await self.enqueue(sentence, emotion=emotion)
        # join: Wait for the worker to call task_done on each put to actually empty the queue.
        await self._queue.join()

    async def _worker(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                if item is None:
                    return
                text, emotion = item
                gen = self._speak_gen
                p = with_emotion(self._prosody, emotion)
                async with self._lock:
                    if gen != self._speak_gen:
                        continue
                    try:
                        # replace() keeps every credential field (full_url / protocol / extra
                        # request overrides); only the per-emotion voice moves.
                        tts_creds = replace(
                            self._tts_creds,
                            voice=p.voice or self._tts_creds.voice,
                        )
                        audio_b64 = await synthesize_speech(
                            text, creds=tts_creds, rate=p.rate, pitch=p.pitch
                        )
                    except Exception as e:
                        self._fail_count += 1
                        logger.error("TTS failed voice=%s: %s", p.voice, e)
                        if self._fail_count <= 3:
                            try:
                                await self._send(
                                    "error",
                                    message="Speech synthesis failed; check network or retry later (text interview still works)",
                                    code="C2002",
                                    retryable=True,
                                )
                            except Exception:
                                logger.debug(
                                    "TTS error event failed to send voice=%s",
                                    p.voice,
                                    exc_info=True,
                                )
                        continue
                    if gen != self._speak_gen:
                        continue
                    if audio_b64:
                        try:
                            await self._send("tts_audio", data=audio_b64, sentence=text)
                            if callable(self._on_sent):
                                self._on_sent()
                        except Exception as e:
                            logger.warning("TTS sending failed: %s", e)
                    else:
                        try:
                            await self._send(
                                "tts_failed",
                                message="Speech synthesis returned empty audio; check network or type instead",
                            )
                        except Exception:
                            logger.debug(
                                "tts_failed event failed to send",
                                exc_info=True,
                            )
            finally:
                self._queue.task_done()


__all__ = ["_SentenceTTSQueue"]
