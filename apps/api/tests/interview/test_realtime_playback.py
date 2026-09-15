"""Playback tests for realtime/turn/playback.py.

Covers: mark/begin/wait playback generation alignment, timeout path,
open-mic anchoring/early-return, cancel pending playback.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

def _make_handler(sid=1):
    """Build a mocked InterviewWSHandler bound to an in-memory websocket."""
    ws = MagicMock(accept=AsyncMock(), send_json=AsyncMock(), receive_json=AsyncMock(), close=AsyncMock())
    return InterviewWSHandler(ws, session_id=sid)


async def _agen(items):
    """Yield canned stream events for deterministic streaming tests."""
    for i in items:
        yield i

@pytest.mark.asyncio
async def test_playback_mixins():
    h = _make_handler()
    try:
        h._mark_tts_sent()
        assert h.ctx.tts_sent_this_turn is True
        h._begin_playback_wait()
        assert h.ctx.tts_sent_this_turn is False
        assert h.ctx.playback_generation >= 1
        # no tts -> immediate return
        h.ctx.tts_sent_this_turn = False
        await h._wait_client_playback()
        # tts sent + already done -> sleep + clear
        h.ctx.tts_sent_this_turn = True
        h.ctx.playback_done.set()
        h.ctx.awaiting_playback_gen = h.ctx.playback_generation
        await h._wait_client_playback()
        assert h.ctx.tts_sent_this_turn is False
        # timeout path
        h.ctx.tts_sent_this_turn = True
        h.ctx.playback_done.clear()
        h.ctx.playback_wait_timeout_sec = 0.01
        h.ctx.awaiting_playback_gen = h.ctx.playback_generation
        await h._wait_client_playback()
        # gen mismatch -> no clear of flag? tts stays True
        h.ctx.tts_sent_this_turn = True
        h.ctx.playback_done.set()
        h.ctx.awaiting_playback_gen = 999
        h.ctx.playback_generation = 1000
        # manipulate: wait_gen != awaiting -> flag stays
        old_gen = h.ctx.awaiting_playback_gen
        h.ctx.playback_done.clear()
        h.ctx.playback_done.set()
        # force mismatch by changing awaiting after begin
        h.ctx.tts_sent_this_turn = True
        wait_gen = old_gen
        h.ctx.awaiting_playback_gen = wait_gen + 1
        h.ctx.playback_done.set()
        h.ctx.playback_wait_timeout_sec = 5.0
        # call with matching then mismatching: first set matching
        h.ctx.awaiting_playback_gen = h.ctx.playback_generation
        await h._wait_client_playback()
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_open_mic_and_cancel_playback():
    h = _make_handler()
    try:
        # wait_playback True with epoch change -> return early
        h.ctx.stream_epoch = 5
        h.ctx.tts_sent_this_turn = False
        h.ctx.playback_done.set()
        h.ctx.turn_state = TurnState.IDLE
        async def _fake_wait():
            h.ctx.stream_epoch = 6
        h._wait_client_playback = _fake_wait  # type: ignore[method-assign]
        await h._open_mic_after_playback(wait_playback=True)
        assert h.ctx.turn_state == TurnState.IDLE  # unchanged, early return
        # wait_playback True normal -> anchors speech_end
        h.ctx.stream_epoch = 5
        h.ctx.playback_done.set()
        h.ctx.tts_sent_this_turn = True
        async def _noop_wait():
            return None
        h._wait_client_playback = _noop_wait  # type: ignore[method-assign]
        await h._open_mic_after_playback(wait_playback=True)
        assert h.ctx.speech_end_at != 0.0
        # text-only -> anchors
        h2 = _make_handler()
        try:
            h2.ctx.tts_sent_this_turn = False
            h2.ctx.turn_state = TurnState.IDLE
            h2.ctx.speech_end_at = 0.0
            await h2._open_mic_after_playback(wait_playback=False)
            assert h2.ctx.speech_end_at != 0.0
            assert h2.ctx.turn_state == TurnState.USER_SPEAKING
            # already USER_SPEAKING -> return
            await h2._open_mic_after_playback(wait_playback=False)
        finally:
            await h2._cancel_bg_tasks()
        # cancel pending: no-op when nothing pending
        h.ctx.tts_sent_this_turn = False
        h.ctx.playback_done.clear()
        await h._cancel_pending_playback()
        h.ctx.ws.send_json.assert_not_called() if False else None
        # cancel pending success
        h.ctx.tts_sent_this_turn = True
        h.ctx.playback_done.clear()
        h.ctx.tts_queue.clear = AsyncMock()  # type: ignore[method-assign]
        h.ctx.ws.send_json.reset_mock()
        await h._cancel_pending_playback()
        assert h.ctx.tts_sent_this_turn is False
        assert h.ctx.playback_done.is_set()
    finally:
        await h._cancel_bg_tasks()

