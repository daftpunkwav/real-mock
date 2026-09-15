"""Finish tests for realtime/control/finish.py.

Covers: closing noop, missing session A2001, completed reschedule,
not-ready A0006, success closing, error reopen, exception propagation.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from realmock.domains.interview.agents.events import StreamEvent
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
async def test_finish_closing_and_missing_and_completed():
    h = _make_handler()
    h.ctx.closing = True
    await h._on_request_finish()
    h.ctx.ws.send_json.assert_not_called()
    h.ctx.closing = False
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch("realmock.domains.interview.realtime.control.finish.SessionLocal", return_value=db):
        await h._on_request_finish()
    assert h.ctx.ws.send_json.await_args[0][0]["code"] == "A2001"
    h2 = _make_handler()
    sess = MagicMock(status="completed", current_phase="p")
    db2 = MagicMock()
    db2.query.return_value.filter.return_value.first.return_value = sess
    h2.rebind_runtime_session = MagicMock()  # type: ignore[method-assign]
    h2._schedule_report_generation = MagicMock()  # type: ignore[method-assign]
    with patch("realmock.domains.interview.realtime.control.finish.SessionLocal", return_value=db2):
        await h2._on_request_finish()
    assert h2._schedule_report_generation.called


@pytest.mark.asyncio
async def test_finish_not_ready_and_success():
    h = _make_handler()
    sess = MagicMock(status="active")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = sess
    h.rebind_runtime_session = MagicMock()  # type: ignore[method-assign]
    h.ctx.runner = None
    h.ctx.llm = None
    with patch("realmock.domains.interview.realtime.control.finish.SessionLocal", return_value=db):
        await h._on_request_finish()
    assert h.ctx.ws.send_json.await_args[0][0]["code"] == "A0006"
    h2 = _make_handler()
    h2.rebind_runtime_session = MagicMock()  # type: ignore[method-assign]
    h2.ctx.runner = MagicMock()
    h2.ctx.llm = MagicMock(api_key="sk")
    h2.set_turn = AsyncMock()  # type: ignore[method-assign]
    done = StreamEvent.make_turn_done(content="bye", phase_id="p", is_complete=False, phase_changed=False)
    h2._stream_events_with_tts = AsyncMock(return_value=done)  # type: ignore[method-assign]
    h2._schedule_report_generation = MagicMock()  # type: ignore[method-assign]
    h2._spawn = MagicMock(side_effect=lambda c: (c.close(), MagicMock())[1])  # type: ignore[method-assign]
    h2._wait_client_playback = AsyncMock(return_value=None)  # type: ignore[method-assign]
    db2 = MagicMock()
    db2.query.return_value.filter.return_value.first.return_value = MagicMock(status="active")
    with patch("realmock.domains.interview.realtime.control.finish.SessionLocal", return_value=db2):
        await h2._on_request_finish()
    assert h2.ctx.closing is True
    assert h2._schedule_report_generation.called


@pytest.mark.asyncio
async def test_finish_error_and_exception():
    h = _make_handler()
    h.rebind_runtime_session = MagicMock()  # type: ignore[method-assign]
    h.ctx.runner = MagicMock()
    h.ctx.llm = MagicMock(api_key="sk")
    h.set_turn = AsyncMock()  # type: ignore[method-assign]
    h._open_mic_after_playback = AsyncMock()  # type: ignore[method-assign]
    err = StreamEvent.make_error("bad", code="C0001")
    h._stream_events_with_tts = AsyncMock(return_value=err)  # type: ignore[method-assign]
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(status="active")
    with patch("realmock.domains.interview.realtime.control.finish.SessionLocal", return_value=db):
        await h._on_request_finish()
    assert h.ctx.closing is False
    h2 = _make_handler()
    h2.rebind_runtime_session = MagicMock()  # type: ignore[method-assign]
    h2.ctx.runner = MagicMock()
    h2.ctx.llm = MagicMock(api_key="sk")
    h2.set_turn = AsyncMock()  # type: ignore[method-assign]
    h2._stream_events_with_tts = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    with patch("realmock.domains.interview.realtime.control.finish.SessionLocal", return_value=MagicMock(query=MagicMock(return_value=MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=MagicMock(status="active")))))))):
        try:
            await h2._on_request_finish()
            assert False
        except RuntimeError:
            assert h2.ctx.closing is False

