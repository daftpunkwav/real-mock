"""Lifecycle-hook tests for realmock.platform.contracts.lifecycle_hooks.

Covers: no-op defaults, sync/async handler dispatch, failure swallowing,
  and background scheduling with and without a running event loop.
Conventions: handlers stubbed in-memory; globals restored at test end.
"""

from __future__ import annotations

import pytest


class TestLifecycleHooksContract:
    @pytest.mark.asyncio
    async def test_lifecycle_hooks(self) -> None:
        import realmock.platform.contracts.lifecycle_hooks as lh
        from realmock.platform.contracts import InterviewFinishedPayload, ReportSummaryPayload

        # none registered -> no-op
        lh.set_on_interview_finished(None)
        lh.set_on_report_summary(None)
        lh.set_system_insights_provider(None)
        assert lh.get_on_interview_finished() is None
        assert lh.get_on_report_summary() is None
        assert lh.get_system_insights_provider() is None
        lh.notify_interview_finished(InterviewFinishedPayload(session_id=1))
        await lh.notify_report_summary(ReportSummaryPayload(session_id=1))

        # sync handler
        seen = []
        lh.set_on_interview_finished(lambda p: seen.append(p.session_id))
        lh.notify_interview_finished(InterviewFinishedPayload(session_id=3))
        assert seen == [3]

        # async handler without running loop scheduling uses asyncio.run internally;
        # inside async test there IS a running loop -> create_task path
        done = []

        async def _async_handler(payload):
            done.append(payload.session_id)

        lh.set_on_interview_finished(_async_handler)
        lh.notify_interview_finished(InterviewFinishedPayload(session_id=4))
        import asyncio as _aio

        await _aio.sleep(0)
        assert done == [4]

        # failing handler swallowed
        def _boom(payload):
            raise RuntimeError("x")

        lh.set_on_interview_finished(_boom)
        lh.notify_interview_finished(InterviewFinishedPayload(session_id=5))

        async def _aboom(payload):
            raise RuntimeError("y")

        lh.set_on_interview_finished(_aboom)
        lh.notify_interview_finished(InterviewFinishedPayload(session_id=6))
        await _aio.sleep(0)

        # report summary handlers
        lh.set_on_report_summary(lambda p: seen.append(p.session_id))
        await lh.notify_report_summary(ReportSummaryPayload(session_id=9))

        async def _rok(payload):
            seen.append(payload.session_id * 10)

        lh.set_on_report_summary(_rok)
        await lh.notify_report_summary(ReportSummaryPayload(session_id=2))
        assert 20 in seen

        def _rboom(payload):
            raise RuntimeError("z")

        lh.set_on_report_summary(_rboom)
        await lh.notify_report_summary(ReportSummaryPayload(session_id=11))

        async def _raboom(payload):
            raise RuntimeError("w")

        lh.set_on_report_summary(_raboom)
        await lh.notify_report_summary(ReportSummaryPayload(session_id=12))

        # schedule_or_run without running loop
        async def _solo():
            seen.append("solo")

        # run in thread without loop to hit asyncio.run branch
        import threading as _th

        def _target():
            lh._schedule_or_run(_solo(), label="t", sid=1)

        th = _th.Thread(target=_target)
        th.start()
        th.join()
        assert "solo" in seen

        async def _fail():
            raise RuntimeError("bg fail")

        def _target2():
            lh._schedule_or_run(_fail(), label="t", sid=2)

        th2 = _th.Thread(target=_target2)
        th2.start()
        th2.join()

        lh.set_on_interview_finished(None)
        lh.set_on_report_summary(None)
        lh.set_system_insights_provider(None)
