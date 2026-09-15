"""User text tests for realtime/control/user_text.py.

Covers: process user text superseded/complete/incomplete branches,
error and scheduled report paths.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from realmock.domains.interview.agents.events import EventKind
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
async def test_process_user_text_branches():
    # superseded without owner -> reopen mic
    h = _make_handler()
    try:
        h.ctx.runner = MagicMock()
        h.ctx.stream_epoch = 1
        h.ctx.turn_state = TurnState.PROCESSING
        h.ctx.turn_busy = False
        h._cancel_pending_playback = AsyncMock()  # type: ignore[method-assign]
        h.set_turn = AsyncMock()  # type: ignore[method-assign]
        h._open_mic_after_playback = AsyncMock()  # type: ignore[method-assign]

        async def _fake_stream(*a, **k):
            h.ctx.stream_epoch = 2  # simulate barge-in during stream
            return MagicMock(kind=EventKind.TURN_COMPLETE, is_complete=True)

        h._stream_events_with_tts = _fake_stream  # type: ignore[method-assign]
        await h._process_user_text("hi", {}, MagicMock(), MagicMock())
        h._open_mic_after_playback.assert_awaited_once()
        # already USER_SPEAKING after stream -> return
        h.ctx.ws.send_json.reset_mock() if hasattr(h.ctx.ws.send_json, "reset_mock") else None
        h2 = _make_handler()
        try:
            h2.ctx.runner = MagicMock()
            h2.ctx.stream_epoch = 1
            h2.ctx.turn_state = TurnState.USER_SPEAKING
            h2._cancel_pending_playback = AsyncMock()  # type: ignore[method-assign]
            h2.set_turn = AsyncMock()  # type: ignore[method-assign]
            h2._open_mic_after_playback = AsyncMock()  # type: ignore[method-assign]
            h2._stream_events_with_tts = AsyncMock(return_value=MagicMock(kind=EventKind.TURN_COMPLETE, is_complete=True))  # type: ignore[method-assign]
            # force post-stream state USER_SPEAKING
            orig_stream = h2._stream_events_with_tts

            async def _to_speaking(*a, **k):
                h2.ctx.turn_state = TurnState.USER_SPEAKING
                return MagicMock(kind=EventKind.TURN_COMPLETE, is_complete=True)

            h2._stream_events_with_tts = _to_speaking  # type: ignore[method-assign]
            await h2._process_user_text("hi", {}, MagicMock(), MagicMock())
            h2._open_mic_after_playback.assert_not_called()
            assert orig_stream is not None
        finally:
            await h2._cancel_bg_tasks()
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_process_user_text_error_complete_incomplete():
    for kind, is_complete, expect in [
        (EventKind.ERROR, False, "open_mic"),
        (None, False, "open_mic"),
        (EventKind.TURN_COMPLETE, True, "scheduled"),
        (EventKind.TURN_COMPLETE, False, "open_mic"),
    ]:
        h = _make_handler()
        try:
            h.ctx.runner = MagicMock()
            h.ctx.stream_epoch = 1
            h.ctx.turn_state = TurnState.IDLE
            h.ctx.turn_busy = False
            h._cancel_pending_playback = AsyncMock()  # type: ignore[method-assign]
            h.set_turn = AsyncMock()  # type: ignore[method-assign]
            h._open_mic_after_playback = AsyncMock()  # type: ignore[method-assign]
            h._schedule_report_generation = MagicMock()  # type: ignore[method-assign]
            if kind is None:
                last = None
            else:
                last = MagicMock(kind=kind, is_complete=is_complete)
            h._stream_events_with_tts = AsyncMock(return_value=last)  # type: ignore[method-assign]
            if expect == "scheduled":
                h._spawn = MagicMock(side_effect=lambda c: (c.close(), MagicMock())[1])  # type: ignore[method-assign]
            await h._process_user_text("hello", {}, MagicMock(), MagicMock())
            if expect == "open_mic":
                h._open_mic_after_playback.assert_awaited_once()
            else:
                h._schedule_report_generation.assert_called_once()
                h._spawn.assert_called_once()
        finally:
            await h._cancel_bg_tasks()

