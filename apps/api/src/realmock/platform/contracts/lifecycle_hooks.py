"""Composition-root lifecycle hooks for cross-domain callbacks.

- Interview finish -> records via ``set_on_interview_finished`` /
  ``notify_interview_finished`` (sync; schedules async handlers).
- Records ready -> growth via ``notify_report_summary``.
- Optional ``set_system_insights_provider`` for interview runner injection.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from realmock.platform.contracts.interview_finished import InterviewFinishedPayload
from realmock.platform.contracts.report_summary import ReportSummaryPayload

logger = logging.getLogger(__name__)

InterviewFinishedHandler = Callable[[InterviewFinishedPayload], Awaitable[None] | None]
ReportSummaryHandler = Callable[[ReportSummaryPayload], Awaitable[None] | None]
SystemInsightsProvider = Callable[..., Any]

_on_interview_finished: InterviewFinishedHandler | None = None
_on_report_summary: ReportSummaryHandler | None = None
_system_insights_provider: SystemInsightsProvider | None = None


def set_on_interview_finished(handler: InterviewFinishedHandler | None) -> None:
    """Register (or clear) the records ingest handler for interview finish."""
    global _on_interview_finished
    _on_interview_finished = handler


def set_on_report_summary(handler: ReportSummaryHandler | None) -> None:
    """Register (or clear) the growth handler for report-summary ready."""
    global _on_report_summary
    _on_report_summary = handler


def set_system_insights_provider(provider: SystemInsightsProvider | None) -> None:
    """Register (or clear) the system-insights callable for interview runners."""
    global _system_insights_provider
    _system_insights_provider = provider


def get_system_insights_provider() -> SystemInsightsProvider | None:
    """Return the registered system-insights provider, if any."""
    return _system_insights_provider


def _schedule_or_run(awaitable: Awaitable[None], *, label: str, sid: int) -> None:
    """Fire-and-forget an async handler; never raise into the caller."""

    def _done(task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except Exception:
            logger.exception("%s background task failed sid=%s", label, sid)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(awaitable)
        except Exception:
            logger.exception("%s failed sid=%s", label, sid)
        return
    task = loop.create_task(awaitable)
    task.add_done_callback(_done)


def notify_interview_finished(payload: InterviewFinishedPayload) -> None:
    """Invoke the registered interview-finished handler (sync entrypoint).

    Async handlers are scheduled on the running loop so finish stays non-blocking.
    """
    handler = _on_interview_finished
    if handler is None:
        logger.debug("no interview-finished handler registered sid=%s", payload.session_id)
        return
    try:
        result = handler(payload)
        if inspect.isawaitable(result):
            _schedule_or_run(result, label="interview-finished", sid=payload.session_id)
    except Exception:
        logger.exception(
            "interview-finished handler failed sid=%s", payload.session_id
        )


async def notify_report_summary(payload: ReportSummaryPayload) -> None:
    """Invoke the registered report-summary handler if any.

    Failures are logged and swallowed so the records persist path stays robust.
    """
    handler = _on_report_summary
    if handler is None:
        logger.debug("no report-summary handler registered sid=%s", payload.session_id)
        return
    try:
        result = handler(payload)
        if inspect.isawaitable(result):
            await result
    except Exception:
        logger.exception("report-summary handler failed sid=%s", payload.session_id)


def get_on_interview_finished() -> InterviewFinishedHandler | None:
    """Return the current interview-finished handler (tests / diagnostics)."""
    return _on_interview_finished


def get_on_report_summary() -> ReportSummaryHandler | None:
    """Return the current report-summary handler (tests / diagnostics)."""
    return _on_report_summary
