"""Fire-and-forget background task spawning (crash-logged, GC-safe).

Holding a reference to every in-flight task is required: a bare
``asyncio.create_task`` result can be garbage-collected mid-flight, silently
killing the work. Every agent that schedules background work shares this.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_tasks: set[asyncio.Task] = set()


def spawn_background(coro, *, label: str) -> asyncio.Task:
    """Schedule ``coro`` as a background task; exceptions are logged, never raised.

    The task keeps a module-level reference until done so the event loop cannot
    garbage-collect it before completion.
    """

    async def _runner():
        try:
            await coro
        except Exception:
            logger.exception("Background task crashed: %s", label)

    task = asyncio.create_task(_runner())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


__all__ = ["spawn_background"]
