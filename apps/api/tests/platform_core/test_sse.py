"""Unit tests for shared SSE error-event helpers and the queue pump."""

import asyncio

from realmock.platform.core.errors import ApiBusinessError, get_spec
from realmock.platform.core.sse import (
    QueuePut,
    format_sse_line,
    pump_queue_to_sse,
    sse_error_event,
    sse_streaming_response,
)


def test_business_error_keeps_catalog_fields():
    spec = get_spec("A1005")
    event = sse_error_event(
        ApiBusinessError(spec, message="Resume not found"),
        message="fallback copy",
    )
    assert event == {
        "type": "error",
        "code": "A1005",
        "message": "Resume not found",
        "retryable": spec.retryable,
    }


def test_business_error_empty_detail_falls_back_to_message():
    spec = get_spec("A1005")
    event = sse_error_event(
        ApiBusinessError(spec, message=""),
        message="fallback copy",
    )
    assert event["code"] == "A1005"
    assert event["message"] == "fallback copy"


def test_unexpected_error_uses_fallback_copy_and_catalog_flag():
    event = sse_error_event(ValueError("boom"), message="generic copy")
    assert event["type"] == "error"
    assert event["code"] == "C0001"
    assert event["message"] == "generic copy"
    assert event["retryable"] == get_spec("C0001").retryable


def test_unexpected_error_custom_code():
    event = sse_error_event(
        RuntimeError("boom"), message="report copy", code="C1001"
    )
    assert event["code"] == "C1001"
    assert event["message"] == "report copy"
    assert event["retryable"] == get_spec("C1001").retryable


def test_unexpected_error_explicit_retryable_override():
    event = sse_error_event(
        RuntimeError("boom"), message="copy", code="C1001", retryable=False
    )
    assert event["retryable"] is False


def test_unexpected_error_unknown_code_falls_back_to_b0001():
    event = sse_error_event(ValueError("boom"), message="copy", code="Z9999")
    assert event["code"] == "B0001"
    assert event["message"] == "copy"


def test_format_sse_line_exact_shape():
    assert format_sse_line({"type": "done"}) == 'data: {"type": "done"}\n\n'


class _Request:
    def __init__(self, disconnect_after: int | None = None) -> None:
        self.calls = 0
        self.disconnect_after = disconnect_after

    async def is_disconnected(self) -> bool:
        self.calls += 1
        return self.disconnect_after is not None and self.calls > self.disconnect_after


async def _collect(gen) -> list[str]:
    return [line async for line in gen]


async def test_pump_streams_events_until_sentinel() -> None:
    async def producer(put: QueuePut) -> None:
        await put({"type": "tool_step"})
        await put(None)

    lines = await _collect(pump_queue_to_sse(_Request(), producer, heartbeat_seconds=5.0))  # type: ignore[arg-type]
    assert lines == ['data: {"type": "tool_step"}\n\n']


async def test_pump_emits_heartbeat_while_idle() -> None:
    async def producer(put: QueuePut) -> None:
        await asyncio.sleep(0.15)
        await put(None)

    lines = await _collect(
        pump_queue_to_sse(_Request(), producer, heartbeat_seconds=0.05)  # type: ignore[arg-type]
    )
    # The None sentinel ends the stream silently; idle gaps surface as pings.
    assert any(line == ": ping\n\n" for line in lines)


async def test_pump_breaks_on_disconnect_and_cancels_producer() -> None:
    cancelled = asyncio.Event()

    async def producer(put: QueuePut) -> None:
        try:
            await asyncio.sleep(30.0)
            await put(None)  # pragma: no cover
        except asyncio.CancelledError:
            cancelled.set()
            raise

    lines = await asyncio.wait_for(
        _collect(pump_queue_to_sse(_Request(disconnect_after=2), producer, heartbeat_seconds=0.05)),  # type: ignore[arg-type]
        timeout=5.0,
    )
    assert all(line == ": ping\n\n" for line in lines)
    assert cancelled.is_set()


async def test_pump_unblocks_producer_that_pushes_during_cleanup() -> None:
    """A producer awaiting put() during unwind must not wedge the pump.

    Real producers report an error event and the None sentinel from their
    except/finally blocks. After a disconnect nobody drains the bounded queue,
    so those awaits would block forever and the unconditional gather below the
    pump would never return, leaking the response coroutine.
    """
    cleanup_done = asyncio.Event()

    async def producer(put: QueuePut) -> None:
        try:
            for i in range(100):
                await put({"i": i})
        except asyncio.CancelledError:
            await put({"type": "error"})
            await put(None)
            cleanup_done.set()
            raise

    await asyncio.wait_for(
        _collect(
            pump_queue_to_sse(
                _Request(disconnect_after=1),
                producer,
                heartbeat_seconds=5.0,
                max_queue=1,
            )  # type: ignore[arg-type]
        ),
        timeout=5.0,
    )
    assert cleanup_done.is_set()


def test_sse_streaming_response_headers() -> None:
    async def _empty():
        if False:
            yield ""

    resp = sse_streaming_response(_empty())
    assert resp.media_type == "text/event-stream"
    assert resp.headers["Cache-Control"] == "no-cache"
    assert resp.headers["X-Accel-Buffering"] == "no"
