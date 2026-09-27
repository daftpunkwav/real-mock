"""Interrupt tests for realtime/control/interrupt.py.

Covers: interrupt-stats persistence via the runner facade, candidate barge-in
state/persistence-failure paths.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

import json
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
async def test_persist_interrupt_stats_merges_via_facade(monkeypatch):
    """Counters merge through the runner facade; the same snapshot persists."""
    h = _make_handler()
    try:
        h.ctx.candidate_interrupts = 2
        h.ctx.ai_interrupts = 1
        runner = MagicMock()
        runner.record_interrupt_counts.return_value = {
            "candidate_interrupts": 2,
            "ai_interrupts": 1,
            "existing": True,
        }
        h.ctx.runner = runner
        captured: dict = {}

        def _fake_sync(session_id: int, state_json: str) -> bool:
            captured["sid"] = session_id
            captured["state"] = json.loads(state_json)
            return True

        monkeypatch.setattr(h, "_persist_interrupt_stats_sync", _fake_sync)
        await h._persist_interrupt_stats()
        runner.record_interrupt_counts.assert_called_once_with(candidate=2, ai=1)
        assert captured == {"sid": 1, "state": {"candidate_interrupts": 2, "ai_interrupts": 1, "existing": True}}

        # Without a runner there is nothing to record or persist.
        h.ctx.runner = None
        captured.clear()
        await h._persist_interrupt_stats()
        assert captured == {}
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
        # success: barge-in records through the facade, persistence is stubbed
        h.ctx.turn_state = TurnState.AI_SPEAKING
        h.ctx.runner = MagicMock()
        h._persist_interrupt_stats = AsyncMock()  # type: ignore[method-assign]
        await h._on_candidate_barge_in()
        assert h.ctx.candidate_interrupts == 1
        assert h.ctx.turn_state == TurnState.USER_SPEAKING
        h._persist_interrupt_stats.assert_awaited_once()
        # a persistence failure must not bubble out of the barge-in path
        h2 = _make_handler()
        try:
            h2.ctx.turn_state = TurnState.PROCESSING
            h2.ctx.tts_queue.clear = AsyncMock()  # type: ignore[method-assign]
            h2.ctx.runner = MagicMock()
            h2._persist_interrupt_stats = AsyncMock(
                side_effect=RuntimeError("persist boom"))  # type: ignore[method-assign]
            await h2._on_candidate_barge_in()
            assert h2.ctx.turn_state == TurnState.USER_SPEAKING
        finally:
            await h2._cancel_bg_tasks()
    finally:
        await h._cancel_bg_tasks()
