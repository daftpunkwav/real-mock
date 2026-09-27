"""Heartbeat tests for realtime/connection/heartbeat.py.

Covers: superseded short-circuit, lease failure B2003, success passthrough,
receive exception, timeout B2002, ping failure.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

import asyncio
import json

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
async def test_malformed_json_frame_is_rejected_not_fatal():
    """A malformed JSON frame is rejected with A0001 and the room stays up."""
    h = _make_handler()
    h.ctx.ws.receive_json = AsyncMock(
        side_effect=[json.JSONDecodeError("bad json", "{", 1), {"type": "pong"}]
    )
    h.send = AsyncMock()  # type: ignore[method-assign]
    with patch("realmock.domains.interview.realtime.connection.heartbeat.verify_connection_lease", AsyncMock(return_value=True)):
        assert await h.next_message() == {"type": "pong"}
    assert h.send.await_count == 1
    assert h.send.await_args.args[0] == "error"
    assert h.send.await_args.kwargs.get("code") == "A0001"


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

@pytest.mark.asyncio
async def test_sustained_malformed_frames_tear_down_the_room():
    """One bad frame is tolerated; a sustained stream is bounded."""
    h = _make_handler()
    h.send = AsyncMock()  # type: ignore[method-assign]
    h.ctx.ws.receive_json = AsyncMock(
        side_effect=json.JSONDecodeError("bad json", "{", 1)
    )
    with patch("realmock.domains.interview.realtime.connection.heartbeat.verify_connection_lease", AsyncMock(return_value=True)):
        with patch(
            "realmock.domains.interview.realtime.connection.heartbeat._HEARTBEAT_MAX_MALFORMED",
            3,
        ):
            assert await h.next_message() is None
    # One A0001 per tolerated frame plus the final B2004 close notice.
    codes = [c.kwargs.get("code") for c in h.send.await_args_list]
    assert codes == ["A0001", "A0001", "B2004"]

@pytest.mark.asyncio
async def test_lease_fail_notification_failure_still_ends():
    """A failing B2003 send on lease loss must not crash the loop end."""
    h = _make_handler()
    h.send = AsyncMock(side_effect=RuntimeError("socket gone"))  # type: ignore[method-assign]
    with patch("realmock.domains.interview.realtime.connection.heartbeat.verify_connection_lease", AsyncMock(return_value=False)):
        assert await h.next_message() is None


@pytest.mark.asyncio
async def test_heartbeat_timeout_notice_failure_still_ends():
    """A failing B2002 send on a vanished client must not crash the loop end.

    The heartbeat timeout is usually caused by the client disappearing, so
    the disconnect notice frequently cannot be delivered; the loop must end
    through the same graceful None path as the B2003 / B2004 notices.
    """
    h = _make_handler()
    h.send = AsyncMock(side_effect=RuntimeError("socket gone"))  # type: ignore[method-assign]

    async def _slow() -> dict[str, str]:
        await asyncio.sleep(0.05)
        return {"type": "x"}

    h.ctx.ws.receive_json = _slow
    with patch("realmock.domains.interview.realtime.connection.heartbeat.verify_connection_lease", AsyncMock(return_value=True)):
        with patch("realmock.domains.interview.realtime.connection.heartbeat._HEARTBEAT_TIMEOUT_SEC", 0.01):
            with patch("realmock.domains.interview.realtime.connection.heartbeat._HEARTBEAT_MAX_MISSES", 1):
                assert await h.next_message() is None
    assert h.send.await_args.kwargs.get("code") == "B2002"


@pytest.mark.asyncio
async def test_superseded_race_after_lease_check():
    """Superseded set between the lease check and receive: loop ends quietly."""
    h = _make_handler()
    h.ctx.superseded = True
    with patch("realmock.domains.interview.realtime.connection.heartbeat.verify_connection_lease", AsyncMock(return_value=True)):
        assert await h.next_message() is None
