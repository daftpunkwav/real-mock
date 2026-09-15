"""Report scheduler tests for realtime/report_scheduler.py.

Covers: schedule guards, missing session, frozen completed payload,
send failure swallow, lifecycle run/error/close-fail, post-lifecycle send fail.
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_schedule_report_generation_guards():
    h = _make_handler()
    try:
        # running task -> no new spawn
        running = MagicMock()
        running.done.return_value = False
        h.ctx.report_task = running  # type: ignore[assignment]
        h._spawn = MagicMock()  # type: ignore[method-assign]
        h._schedule_report_generation()
        h._spawn.assert_not_called()
        # done task -> spawn
        done = MagicMock()
        done.done.return_value = True
        h.ctx.report_task = done  # type: ignore[assignment]
        h._spawn = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]
        with patch.object(h, "_generate_report_bg", new=AsyncMock(return_value=None)):
            coro = h._generate_report_bg()
            h._schedule_report_generation()
            h._spawn.assert_called_once()
            # close coroutines to avoid warnings (spawn is mocked, real task not created)
            try:
                coro.close()
            except Exception:
                pass
            for c in [c.args[0] for c in h._spawn.call_args_list]:
                try:
                    c.close()
                except Exception:
                    pass
    finally:
        h.ctx.report_task = None
        await h._cancel_bg_tasks()
        reset_session_registry_for_tests()


@pytest.mark.asyncio
async def test_generate_report_bg_missing_session():
    h = _make_handler()
    try:
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        db.close = MagicMock()
        with patch("realmock.domains.interview.realtime.report_scheduler.SessionLocal", return_value=db):
            await h._generate_report_bg()
            db.close.assert_called_once()
        h.ctx.ws.send_json.assert_not_called()
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_generate_report_bg_frozen_completed_and_send_failure():
    h = _make_handler()
    try:
        sess = MagicMock(status="completed", overall_score=88, result="pass")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = sess
        db.close = MagicMock()
        with (
            patch("realmock.domains.interview.realtime.report_scheduler.SessionLocal", return_value=db),
            patch("realmock.domains.interview.realtime.report_scheduler.is_frozen", return_value=True),
        ):
            await h._generate_report_bg()
        payload = h.ctx.ws.send_json.await_args[0][0]
        assert payload["type"] == "interview_complete"
        assert payload["overall_score"] == 88
        # send failure swallowed
        h.ctx.ws.send_json.reset_mock()
        h.ctx.ws.send_json = AsyncMock(side_effect=RuntimeError("send boom"))
        h.ctx.ws = h.ctx.ws  # keep ref
        # need to rebind handler ws? ctx.ws is the mock
        with (
            patch("realmock.domains.interview.realtime.report_scheduler.SessionLocal", return_value=db),
            patch("realmock.domains.interview.realtime.report_scheduler.is_frozen", return_value=True),
        ):
            await h._generate_report_bg()
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_generate_report_bg_run_lifecycle_and_error_and_close_fail():
    h = _make_handler()
    try:
        sess = MagicMock(status="active", overall_score=70, result=None)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = sess
        db.close = MagicMock()
        with (
            patch("realmock.domains.interview.realtime.report_scheduler.SessionLocal", return_value=db),
            patch("realmock.domains.interview.realtime.report_scheduler.is_frozen", return_value=False),
            patch("realmock.domains.interview.realtime.report_scheduler.run_finish_lifecycle", return_value=None) as fl,
        ):
            await h._generate_report_bg()
            fl.assert_called_once()
        assert h.ctx.ws.send_json.await_count >= 1
        # lifecycle raises -> caught, no raise
        db2 = MagicMock()
        db2.query.return_value.filter.return_value.first.return_value = MagicMock(status="active")
        db2.close = MagicMock()
        with (
            patch("realmock.domains.interview.realtime.report_scheduler.SessionLocal", return_value=db2),
            patch("realmock.domains.interview.realtime.report_scheduler.is_frozen", return_value=False),
            patch("realmock.domains.interview.realtime.report_scheduler.run_finish_lifecycle", side_effect=RuntimeError("boom")),
        ):
            await h._generate_report_bg()
        # db.close raises -> swallowed
        db3 = MagicMock()
        db3.query.return_value.filter.return_value.first.return_value = None
        db3.close = MagicMock(side_effect=RuntimeError("close boom"))
        with patch("realmock.domains.interview.realtime.report_scheduler.SessionLocal", return_value=db3):
            await h._generate_report_bg()
    finally:
        await h._cancel_bg_tasks()


@pytest.mark.asyncio
async def test_report_scheduler_send_fail_after_lifecycle():
    h = _make_handler()
    try:
        sess = MagicMock(status="active", overall_score=70, result=None)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = sess
        db.close = MagicMock()
        h.ctx.ws.send_json = AsyncMock(side_effect=RuntimeError("send boom"))
        with (
            patch("realmock.domains.interview.realtime.report_scheduler.SessionLocal", return_value=db),
            patch("realmock.domains.interview.realtime.report_scheduler.is_frozen", return_value=False),
            patch("realmock.domains.interview.realtime.report_scheduler.run_finish_lifecycle", return_value={}),
        ):
            await h._generate_report_bg()  # covers report_scheduler.py 75-76
    finally:
        await h._cancel_bg_tasks()

