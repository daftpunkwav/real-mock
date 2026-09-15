"""Lifecycle tests for realtime/connection/lifecycle.py.

Covers: send/_tts_send playback generation, set_turn, fail-and-close,
handle auth-fail/teardown, exception recovery B2001, success loop,
disconnect, teardown exception swallowing, subprotocol bind.
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
async def test_send_tts_set_turn_fail_close():
    h = _make_handler()
    await h.send("hello", x=1)
    assert h.ctx.ws.send_json.await_args[0][0] == {"type": "hello", "x": 1}
    h.ctx.awaiting_playback_gen = 5
    await h._tts_send("tts_audio", data="d")
    assert h.ctx.ws.send_json.await_args[0][0]["playback_generation"] == 5
    await h.set_turn(TurnState.USER_SPEAKING)
    assert h.ctx.turn_state == TurnState.USER_SPEAKING
    h2 = _make_handler()
    h2.ctx.ws.send_json = AsyncMock(side_effect=RuntimeError("fail"))
    h2.ctx.ws.close = AsyncMock(side_effect=RuntimeError("fail"))
    await h2._fail_and_close("oops")
    h2.ctx.ws.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_auth_fail_and_teardown():
    h = _make_handler()
    h.ctx.ws.accept = AsyncMock()
    h.authenticate = AsyncMock(return_value=None)  # type: ignore[method-assign]
    db = MagicMock()
    with patch("realmock.domains.interview.realtime.connection.lifecycle.SessionLocal", return_value=db):
        await h.handle()
    db.close.assert_called()
    h2 = _make_handler()
    h2._cancel_bg_tasks = AsyncMock()  # type: ignore[method-assign]
    h2.ctx.tts_queue.stop = AsyncMock()
    await h2._teardown(MagicMock())
    h2._cancel_bg_tasks.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_exception_recovers():
    h = _make_handler()
    h.ctx.ws.accept = AsyncMock()
    h.authenticate = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    db = MagicMock()
    with patch("realmock.domains.interview.realtime.connection.lifecycle.SessionLocal", return_value=db):
        await h.handle()
    sent = [c.args[0] for c in h.ctx.ws.send_json.call_args_list]
    assert any(e.get("code") == "B2001" for e in sent)
    assert h.ctx.turn_state == TurnState.USER_SPEAKING


@pytest.mark.asyncio
async def test_handle_success_loop_and_disconnect():
    from fastapi import WebSocketDisconnect
    h = _make_handler()
    h.ctx.ws.accept = AsyncMock()
    h.authenticate = AsyncMock(return_value=MagicMock())  # type: ignore[method-assign]
    h.bind_pipeline = AsyncMock(return_value=True)  # type: ignore[method-assign]
    h.start_session_flow = AsyncMock()  # type: ignore[method-assign]
    h.next_message = AsyncMock(side_effect=[{"type": "pong"}, None])  # type: ignore[method-assign]
    h._dispatch = AsyncMock()  # type: ignore[method-assign]
    db = MagicMock()
    db.close = MagicMock()
    with patch("realmock.domains.interview.realtime.connection.lifecycle.SessionLocal", return_value=db):
        await h.handle()
    h._dispatch.assert_awaited_once()
    h2 = _make_handler()
    h2.ctx.ws.accept = AsyncMock()
    h2.authenticate = AsyncMock(side_effect=WebSocketDisconnect())  # type: ignore[method-assign]
    with patch("realmock.domains.interview.realtime.connection.lifecycle.SessionLocal", return_value=MagicMock()):
        await h2.handle()


@pytest.mark.asyncio
async def test_teardown_exceptions_covered():
    h = _make_handler()
    with patch("realmock.domains.interview.realtime.connection.lifecycle.release_session_connection", AsyncMock(side_effect=RuntimeError("r"))):
        h._cancel_bg_tasks = AsyncMock(side_effect=RuntimeError("c"))  # type: ignore[method-assign]
        h.ctx.tts_queue.stop = AsyncMock(side_effect=RuntimeError("s"))
        db = MagicMock()
        db.close = MagicMock(side_effect=RuntimeError("d"))
        await h._teardown(db)


@pytest.mark.asyncio
async def test_lifecycle_subprotocol_and_bind_fail() -> None:
    h = _make_handler()
    h.ctx.ws_subprotocol = "test-proto"
    h.ctx.ws.accept = AsyncMock()
    h.authenticate = AsyncMock(return_value=None)  # type: ignore[method-assign]
    db = MagicMock()
    with patch(
        "realmock.domains.interview.realtime.connection.lifecycle.SessionLocal",
        return_value=db,
    ):
        await h.handle()
    h.ctx.ws.accept.assert_awaited_once()
    assert h.ctx.ws.accept.await_args[1].get("subprotocol") == "test-proto"

    h2 = _make_handler()
    h2.ctx.ws.accept = AsyncMock()
    h2.authenticate = AsyncMock(return_value=MagicMock())  # type: ignore[method-assign]
    h2.bind_pipeline = AsyncMock(return_value=False)  # type: ignore[method-assign]
    with patch(
        "realmock.domains.interview.realtime.connection.lifecycle.SessionLocal",
        return_value=MagicMock(),
    ):
        await h2.handle()


@pytest.mark.asyncio
async def test_lifecycle_exception_recovery_failures() -> None:
    h = _make_handler()
    h.ctx.ws.accept = AsyncMock()
    h.authenticate = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    h.ctx.ws.send_json = AsyncMock(side_effect=RuntimeError("send down"))
    db = MagicMock()
    db.rollback = MagicMock(side_effect=RuntimeError("rollback down"))
    db.close = MagicMock()
    with patch(
        "realmock.domains.interview.realtime.connection.lifecycle.SessionLocal",
        return_value=db,
    ):
        await h.handle()
    assert db.rollback.called

