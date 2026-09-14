"""In-process live progress events for report generation (pub-sub).

The debrief runner publishes stage / tool / thinking events; the SSE stream
endpoint subscribes while a report is generating. Single-process only (the
app is a local modular monolith); subscribers that never drain are bounded
by queue size to avoid unbounded memory.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_QUEUE_SIZE = 200


def _key(session_id: int) -> str:
    return f"report:{int(session_id)}"


_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)


def subscribe(session_id: int) -> asyncio.Queue:
    """Register a queue for live report events of one session."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_SIZE)
    _subscribers[_key(session_id)].add(queue)
    return queue


def unsubscribe(session_id: int, queue: asyncio.Queue) -> None:
    """Remove a subscriber; drop the bucket when empty."""
    key = _key(session_id)
    _subscribers[key].discard(queue)
    if not _subscribers[key]:
        _subscribers.pop(key, None)


async def publish(session_id: int, event: dict) -> None:
    """Fan out one event; slow subscribers drop the oldest (best-effort)."""
    for queue in list(_subscribers.get(_key(session_id), ())):
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(event)


def publisher(session_id: int) -> Callable[[dict], Awaitable[None]]:
    """Return an ``on_event`` callback bound to one session."""

    async def _publish(event: dict) -> None:
        await publish(session_id, event)

    return _publish


__all__ = ["publish", "publisher", "subscribe", "unsubscribe"]
