"""Heartbeat tests for realtime/connection/heartbeat.py.

Covers: superseded short-circuit, lease failure B2003, success passthrough,
receive exception, timeout B2002, ping failure.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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
async def test_next_superseded_and_lease_fail():
    h = _make_handler()
    h.ctx.superseded = True
    assert await h.next_message() is None
    h2 = _make_handler()
    with patch("realmock.domains.interview.realtime.connection.heartbeat.verify_connection_lease", AsyncMock(return_value=False)):
        assert await h2.next_message() is None
        sent = [c.args[0] for c in h2.ctx.ws.send_json.call_args_list]
        assert any(e.get("code") == "B2003" for e in sent)


@pytest.mark.asyncio
async def test_next_success_and_exception():
    h = _make_handler()
    h.ctx.ws.receive_json = AsyncMock(return_value={"type": "pong"})
    with patch("realmock.domains.interview.realtime.connection.heartbeat.verify_connection_lease", AsyncMock(return_value=True)):
        assert await h.next_message() == {"type": "pong"}
    h2 = _make_handler()
    h2.ctx.ws.receive_json = AsyncMock(side_effect=RuntimeError("recv down"))
    with patch("realmock.domains.interview.realtime.connection.heartbeat.verify_connection_lease", AsyncMock(return_value=True)):
        assert await h2.next_message() is None


@pytest.mark.asyncio
async def test_heartbeat_timeout_and_ping():
    h = _make_handler()
    async def _slow():
        await asyncio.sleep(0.05)
        return {"type": "x"}
    h.ctx.ws.receive_json = _slow
    with patch("realmock.domains.interview.realtime.connection.heartbeat.verify_connection_lease", AsyncMock(return_value=True)):
        with patch("realmock.domains.interview.realtime.connection.heartbeat._HEARTBEAT_TIMEOUT_SEC", 0.01):
            with patch("realmock.domains.interview.realtime.connection.heartbeat._HEARTBEAT_MAX_MISSES", 3):
                assert await h.next_message() is None
                sent = [c.args[0] for c in h.ctx.ws.send_json.call_args_list]
                assert any(e.get("code") == "B2002" for e in sent)
    h2 = _make_handler()
    h2.ctx.ws.receive_json = _slow
    h2.send = AsyncMock(side_effect=RuntimeError("ping fail"))  # type: ignore[method-assign]
    with patch("realmock.domains.interview.realtime.connection.heartbeat.verify_connection_lease", AsyncMock(return_value=True)):
        with patch("realmock.domains.interview.realtime.connection.heartbeat._HEARTBEAT_TIMEOUT_SEC", 0.01):
            with patch("realmock.domains.interview.realtime.connection.heartbeat._HEARTBEAT_MAX_MISSES", 5):
                assert await h2.next_message() is None

