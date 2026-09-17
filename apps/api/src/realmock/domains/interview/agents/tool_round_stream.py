"""Tool-round speculative streaming bridge: relay say-first TOKEN events live.

Runs :meth:`ToolRoundRunner.run_tool_rounds` in a background task while the
caller (``stream_turn`` / ``stream_opening``) yields speculative tokens to the
WS layer through a bounded queue. The task's outcome lands in the caller-owned
``outcome`` dict behind a sentinel, so orchestration failures surface after the
relay instead of being swallowed; client disconnects cancel the background loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.domains.interview.agents.events import StreamEvent

if TYPE_CHECKING:
    from realmock.domains.interview.agents.interviewer.runner import InterviewRunner

logger = logging.getLogger(__name__)

# Backpressure when the WS consumer lags instead of unbounded memory growth.
TOOL_EVENT_QUEUE_MAXSIZE = 256

# Producer end sentinel (stream_tool_rounds event queue).
PRODUCE_DONE = object()


async def stream_tool_rounds(
    runner: "InterviewRunner",
    outcome: dict[str, Any],
    api_messages: list[dict[str, Any]],
    db: Session,
    *,
    temperature: float,
) -> AsyncIterator[StreamEvent]:
    """Run one tool loop in the background and relay its speculative TOKEN events.

    ``outcome["value"]`` receives the :class:`ToolRoundResult` (or
    ``outcome["error"]`` the exception) for the caller to consume after the
    relay ends — a tool-round failure does not interrupt the stream itself.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=TOOL_EVENT_QUEUE_MAXSIZE)

    async def sink(event: StreamEvent) -> None:
        await queue.put(event)

    async def produce() -> None:
        try:
            outcome["value"] = await runner.tools.run_tool_rounds(
                api_messages, db, temperature=temperature, content_sink=sink,
            )
        except Exception as e:
            outcome["error"] = e
        await queue.put(PRODUCE_DONE)

    task = asyncio.create_task(produce())
    try:
        while True:
            item = await queue.get()
            if item is PRODUCE_DONE:
                break
            yield item
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("Interview tool-round background task ended: %s", e)


__all__ = ["PRODUCE_DONE", "TOOL_EVENT_QUEUE_MAXSIZE", "stream_tool_rounds"]
