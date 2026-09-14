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
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class TurnPlaybackMixin:
    """Playback wait: Upgrade the generation, wait for ``tts_playback_done`` (or timeout), and then switch on the mic."""

    ctx: "ConnectionContext"

    def _mark_tts_sent(self) -> None:
        self.ctx.tts_sent_this_turn = True

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

    async def _open_mic_after_playback(self) -> None:
        """After the server-side synthesis is completed, wait for the client to finish broadcasting (or timeout) before switching USER_SPEAKING to prevent mining."""
        wait_epoch = self.ctx.stream_epoch
        await self._wait_client_playback()
        if wait_epoch != self.ctx.stream_epoch:
            return
        if self.ctx.turn_state == TurnState.USER_SPEAKING:
            return
        await self.set_turn(TurnState.USER_SPEAKING)


__all__ = ["TurnPlaybackMixin"]
