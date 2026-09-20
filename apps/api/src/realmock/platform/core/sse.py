"""Shared SSE helpers: error envelopes, queue pump, and streaming responses.

Single pipeline for streaming error envelopes: business errors surface their
catalog code / message / retryable flag; unexpected errors fall back to a
caller-provided generic copy (per-route wording is preserved) with the
catalog default code. Keeps route modules from re-implementing the branch
and from bypassing the error catalog.

``pump_queue_to_sse`` additionally owns the generic producer/consumer loop
(background task, disconnect checks, heartbeat pings, cancellation) so
routes only provide domain events.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from realmock.platform.core.errors import ApiBusinessError, get_spec


def sse_error_event(
    exc: BaseException,
    *,
    message: str,
    code: str = "C0001",
    retryable: bool | None = None,
) -> dict[str, Any]:
    """Build an SSE ``error`` event dict from any exception.

    :param exc: caught exception; :class:`ApiBusinessError` keeps its own
        code / detail / retryable flag.
    :param message: generic user-facing copy for unexpected errors.
    :param code: fallback catalog code for unexpected errors.
    :param retryable: override the catalog retryable flag; None follows it.
    """
    if isinstance(exc, ApiBusinessError):
        return {
            "type": "error",
            "code": exc.error_code,
            "message": str(exc.detail or message),
            "retryable": bool(exc.error_retryable),
        }
    spec = get_spec(code)
    return {
        "type": "error",
        "code": spec.code,
        "message": message,
        "retryable": spec.retryable if retryable is None else retryable,
    }


def format_sse_line(event: dict[str, Any]) -> str:
    """Render one SSE ``data:`` line from an event dict."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


QueuePut = Callable[[dict[str, Any] | None], Awaitable[None]]
QueueProducer = Callable[[QueuePut], "Coroutine[Any, Any, None]"]


async def pump_queue_to_sse(
    request: Request,
    producer: QueueProducer,
    *,
    heartbeat_seconds: float,
    max_queue: int = 200,
) -> AsyncIterator[str]:
    """Run ``producer`` as a background task and yield its events as SSE lines.

    The producer pushes event dicts and a final ``None`` sentinel through the
    given put callback. A bounded queue applies backpressure to fast producers
    instead of growing memory without bound. Heartbeat comments keep idle
    connections alive; client disconnects and producer completion both end
    the stream, and the producer task is always cancelled on exit.
    """
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=max_queue)
    # Flipped once the consumer stops draining. A producer that awaits put() in
    # its own cleanup would otherwise block forever on a full queue nobody reads
    # again, and the gather below would never return.
    abandoned = False

    async def _put(event: dict[str, Any] | None) -> None:
        if abandoned:
            return
        await queue.put(event)

    task = asyncio.create_task(producer(_put))
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except asyncio.TimeoutError:
                # A producer that died without pushing the None sentinel must not
                # leave the stream pinging forever; end the stream once it is
                # done and the queue is fully drained.
                if task.done() and queue.empty():
                    break
                yield ": ping\n\n"
                continue
            if event is None:
                break
            yield format_sse_line(event)
    finally:
        abandoned = True
        if not task.done():
            task.cancel()
        # Await unconditionally so cancellation lands and a producer exception
        # is retrieved (avoids "exception was never retrieved" warnings).
        await asyncio.gather(task, return_exceptions=True)


def sse_streaming_response(body: AsyncIterator[str]) -> StreamingResponse:
    """Wrap an SSE line iterator with the standard no-buffering headers."""
    return StreamingResponse(
        body,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = [
    "QueueProducer",
    "QueuePut",
    "format_sse_line",
    "pump_queue_to_sse",
    "sse_error_event",
    "sse_streaming_response",
]
