"""Text entry tests for realtime/turn/text_entry.py.

Covers: busy-info feedback, missing session A2001, success stt_final dispatch,
exception recovery C0001.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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
async def test_run_busy_sends_info():
    h = _make_handler()
    h.ctx.turn_busy = True
    h.ctx.busy_epoch = h.ctx.stream_epoch
    await h._run_user_text("hello", {})
    assert h.ctx.ws.send_json.await_args[0][0]["type"] == "info"


@pytest.mark.asyncio
async def test_run_missing_session_sends_a2001():
    h = _make_handler()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch("realmock.domains.interview.realtime.turn.text_entry.SessionLocal", return_value=db):
        await h._run_user_text("hello", {})
    assert h.ctx.ws.send_json.await_args[0][0]["code"] == "A2001"
    assert h.ctx.turn_busy is False


@pytest.mark.asyncio
async def test_run_success_sends_final_and_processes():
    h = _make_handler()
    db = MagicMock()
    sess = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = sess
    h.rebind_runtime_session = MagicMock()  # type: ignore[method-assign]
    h._process_user_text = AsyncMock()  # type: ignore[method-assign]
    with patch("realmock.domains.interview.realtime.turn.text_entry.SessionLocal", return_value=db):
        await h._run_user_text("hello world", {"a": 1})
    sent = [c.args[0] for c in h.ctx.ws.send_json.call_args_list]
    assert any(e.get("type") == "stt_final" for e in sent)
    h._process_user_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_exception_recovers_c0001():
    h = _make_handler()
    db = MagicMock()
    sess = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = sess
    h.rebind_runtime_session = MagicMock()  # type: ignore[method-assign]
    h._process_user_text = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    with patch("realmock.domains.interview.realtime.turn.text_entry.SessionLocal", return_value=db):
        await h._run_user_text("hello", {})
    sent = [c.args[0] for c in h.ctx.ws.send_json.call_args_list]
    assert any(e.get("code") == "C0001" for e in sent)
    assert h.ctx.turn_state == TurnState.USER_SPEAKING

