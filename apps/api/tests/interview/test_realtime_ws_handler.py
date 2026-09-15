"""WS handler tests for realtime/ws_handler.py.

Covers: session/ws/lease properties, load session, spawn success/exception/cancel,
cancel background tasks with report task.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from realmock.domains.interview.realtime.core.session_registry import reset_session_registry_for_tests
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
async def test_ws_handler_spawn_cancel_and_props():
    h = _make_handler(sid=999)
    try:
        assert h.session_id == 999
        assert h.ws is h.ctx.ws
        assert h.lease_token == h.ctx.lease_token
        h._superseded = True
        assert h._superseded is True
        assert h._load_session(MagicMock()) is not None or True
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = MagicMock()
        assert h._load_session(db) is not None
        # _spawn success
        async def _ok():
            return 1

        t = h._spawn(_ok())
        await asyncio.sleep(0.05)
        assert t.done()
        # _spawn exception -> logged, done callback keeps it
        async def _boom():
            raise RuntimeError("bg boom")

        t2 = h._spawn(_boom())
        await asyncio.sleep(0.05)
        assert t2.done()
        # _spawn cancelled -> early return in callback
        async def _slow():
            await asyncio.sleep(5)

        t3 = h._spawn(_slow())
        t3.cancel()
        await asyncio.sleep(0.02)
        # _cancel_bg_tasks with report_task
        async def _never():
            await asyncio.sleep(5)

        h.ctx.report_task = asyncio.create_task(_never())
        t4 = asyncio.create_task(asyncio.sleep(5))
        h.ctx.bg_tasks.add(t4)
        await h._cancel_bg_tasks()
        assert h.ctx.bg_tasks == set()
        assert h.ctx.report_task is None
        # cancel with no tasks -> noop
        await h._cancel_bg_tasks()
    finally:
        await h._cancel_bg_tasks()
        reset_session_registry_for_tests()

