"""Playback wait (WS mixin): align TTS send generations and wait for client playback before opening the microphone.

Extracted from :mod:`...turn_coordinator`. Generations are shared with room hooks / the TTS queue
through ``ctx.playback_generation`` / ``ctx.awaiting_playback_gen``; do not introduce another counter.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from realmock.domains.interview.realtime.core.events import TurnState

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from typing import Any

    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class TurnPlaybackMixin:
    """Playback wait: Upgrade the generation, wait for ``tts_playback_done`` (or timeout), and then switch on the mic."""

    ctx: "ConnectionContext"

    if TYPE_CHECKING:
        # Members provided by sibling mixins of the composed InterviewWSHandler.
        set_turn: Callable[[TurnState], Coroutine[Any, Any, None]]
        send: Callable[..., Coroutine[Any, Any, None]]

    def _mark_tts_sent(self) -> None:
        self.ctx.tts_sent_this_turn = True
        self.ctx.last_tts_sent_at = asyncio.get_event_loop().time()

    def _begin_playback_wait(self) -> None:
        """A new round begins: raise the generation and clear the completion signal."""
        self.ctx.playback_generation += 1
        self.ctx.awaiting_playback_gen = self.ctx.playback_generation
        self.ctx.tts_sent_this_turn = False
        self.ctx.playback_done.clear()

    async def _wait_client_playback(self) -> None:
        """If TTS has been sent this round, wait for the client tts_playback_done (or timeout)."""
        if not self.ctx.tts_sent_this_turn:
            return
        wait_gen = self.ctx.awaiting_playback_gen
        if not self.ctx.playback_done.is_set():
            try:
                await asyncio.wait_for(
                    self.ctx.playback_done.wait(),
                    timeout=self.ctx.playback_wait_timeout_sec,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "tts_playback_done timeout sid=%s gen=%s, continue",
                    self.ctx.session_id,
                    wait_gen,
                )
        await asyncio.sleep(0.15)
        if self.ctx.awaiting_playback_gen == wait_gen:
            self.ctx.tts_sent_this_turn = False
            self.ctx.playback_done.clear()

    async def _open_mic_after_playback(self, *, wait_playback: bool = False) -> None:
        """Open the mic for the candidate.

        The default no longer waits for TTS synthesis/playback: the text
        (assistant_done) is complete, so the candidate may type immediately
        while pending audio keeps playing in the background. Pass
        ``wait_playback=True`` only for short single-sentence prompts that
        exist because the candidate is silent (silence nudge), where waiting
        out the playback is the point.
        """
        wait_epoch = self.ctx.stream_epoch
        if wait_playback:
            await self._wait_client_playback()
            if wait_epoch != self.ctx.stream_epoch:
                return
            # We just waited the speech out: anchor silence timing here.
            self.ctx.speech_end_at = asyncio.get_event_loop().time()
        elif not self.ctx.tts_sent_this_turn:
            # Text-only turn (no audio pending): speech is already "over".
            self.ctx.speech_end_at = asyncio.get_event_loop().time()
        # Audio turns without waiting: _on_tts_playback_done stamps the anchor
        # when the client reports the queue drained.
        if self.ctx.turn_state == TurnState.USER_SPEAKING:
            return
        await self.set_turn(TurnState.USER_SPEAKING)

    async def _cancel_pending_playback(self) -> None:
        """Stop audio still playing from the previous assistant turn.

        Called when the candidate replies by text while TTS audio may still
        be in flight: drop unsent sentences, invalidate in-progress synthesis
        (generation bump), and tell the client to stop playing so the new
        turn's audio does not overlap the old. No-op when nothing is pending.
        """
        if not self.ctx.tts_sent_this_turn or self.ctx.playback_done.is_set():
            return
        await self.ctx.tts_queue.clear()
        self.ctx.playback_generation += 1
        self.ctx.awaiting_playback_gen = self.ctx.playback_generation
        self.ctx.tts_sent_this_turn = False
        self.ctx.playback_done.set()
        await self.send(
            "tts_interrupted",
            reason="candidate_text_reply",
            playback_generation=self.ctx.awaiting_playback_gen,
        )


__all__ = ["TurnPlaybackMixin"]
