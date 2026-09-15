"""Interrupt tests for realtime/control/interrupt.py.

Covers: persist interrupt stats branches, candidate barge-in state/session/error paths.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_persist_interrupt_stats_branches():
    h = _make_handler()
    try:
        db = MagicMock()
        # with agent
        h.ctx.agent = MagicMock()
        h.ctx.agent.agent_state = {}
        h.ctx.candidate_interrupts = 2
        h.ctx.ai_interrupts = 1
        sess = MagicMock(agent_state="{}")
        h._persist_interrupt_stats(sess, db)
        assert json.loads(sess.agent_state)["candidate_interrupts"] == 2
        # without agent, session dict state
        h.ctx.agent = None
        sess2 = MagicMock(agent_state=json.dumps({"a": 1}))
        h._persist_interrupt_stats(sess2, db)
        assert json.loads(sess2.agent_state)["candidate_interrupts"] == 2
        # without agent, session non-dict state
        sess3 = MagicMock(agent_state=json.dumps([1, 2]))
        h._persist_interrupt_stats(sess3, db)
        # without agent, session empty state
        sess4 = MagicMock(agent_state="")
        h._persist_interrupt_stats(sess4, db)
        # exception + rollback exception swallowed
        db2 = MagicMock()
        db2.commit = MagicMock(side_effect=RuntimeError("commit boom"))
        db2.rollback = MagicMock(side_effect=RuntimeError("rollback boom"))
        h.ctx.agent = MagicMock()
        h.ctx.agent.agent_state = {}
        h._persist_interrupt_stats(MagicMock(agent_state="{}"), db2)
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_candidate_barge_in_branches():
    h = _make_handler()
    try:
        # wrong state -> noop
        h.ctx.turn_state = TurnState.USER_SPEAKING
        await h._on_candidate_barge_in()
        h.ctx.ws.send_json.assert_not_called()
        # success with session
        h.ctx.turn_state = TurnState.AI_SPEAKING
        h.ctx.candidate_interrupts = 0
        h.ctx.stream_epoch = 0
        h.ctx.tts_queue.clear = AsyncMock()  # type: ignore[method-assign]
        sess = MagicMock()
        db = MagicMock()
        db.close = MagicMock()
        h._load_session = MagicMock(return_value=sess)  # type: ignore[method-assign]
        h._persist_interrupt_stats = MagicMock()  # type: ignore[method-assign]
        with patch("realmock.domains.interview.realtime.control.interrupt.SessionLocal", return_value=db):
            await h._on_candidate_barge_in()
        assert h.ctx.candidate_interrupts == 1
        assert h.ctx.turn_state == TurnState.USER_SPEAKING
        # session None
        h2 = _make_handler()
        try:
            h2.ctx.turn_state = TurnState.PROCESSING
            h2.ctx.tts_queue.clear = AsyncMock()  # type: ignore[method-assign]
            h2._load_session = MagicMock(return_value=None)  # type: ignore[method-assign]
            db2 = MagicMock()
            db2.close = MagicMock()
            with patch("realmock.domains.interview.realtime.control.interrupt.SessionLocal", return_value=db2):
                await h2._on_candidate_barge_in()
            assert h2.ctx.turn_state == TurnState.USER_SPEAKING
        finally:
            await h2._cancel_bg_tasks()
        # load raises + close raises
        h3 = _make_handler()
        try:
            h3.ctx.turn_state = TurnState.AI_SPEAKING
            h3.ctx.tts_queue.clear = AsyncMock()  # type: ignore[method-assign]
            h3._load_session = MagicMock(side_effect=RuntimeError("load boom"))  # type: ignore[method-assign]
            db3 = MagicMock()
            db3.close = MagicMock(side_effect=RuntimeError("close boom"))
            with patch("realmock.domains.interview.realtime.control.interrupt.SessionLocal", return_value=db3):
                await h3._on_candidate_barge_in()
            assert h3.ctx.turn_state == TurnState.USER_SPEAKING
        finally:
            await h3._cancel_bg_tasks()
    finally:
        await h._cancel_bg_tasks()

