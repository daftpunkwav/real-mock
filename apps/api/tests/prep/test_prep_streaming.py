"""Streaming tests for realmock.domains.prep.agents.streaming.

Covers: make_display_filter, event_loopbacks on_content, _public_args, _display_result and stream_tool_rounds success/error/cancel paths
Conventions: No real LLM; background tasks faked where needed; rate limits reset per test
"""
from __future__ import annotations
import asyncio
import pytest
from realmock.domains.prep.agents.streaming import (
    _display_result,
    _public_args,
    event_loopbacks,
    make_display_filter,
    stream_tool_rounds,
)

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def test_feed_empty_returns_empty() -> None:
    filt = make_display_filter()
    assert filt.feed("") == ""

def test_oversized_unclosed_block_released_as_text() -> None:
    filt = make_display_filter()
    out = filt.feed("<tool_call>" + "x" * 5000)
    assert "x" * 100 in out
    # Filter is reusable after release.
    assert filt.flush() == ""

@pytest.mark.asyncio
async def test_on_content_noop_without_events_or_state() -> None:
    _, _, on_content = event_loopbacks(None, content_state=None)
    await on_content("hello")

    events: asyncio.Queue = asyncio.Queue()
    _, _, on_content2 = event_loopbacks(events, content_state=None)
    await on_content2("hello")
    assert events.empty()

    _, _, on_content3 = event_loopbacks(events, content_state={"filter": make_display_filter()})
    await on_content3("")
    assert events.empty()

@pytest.mark.asyncio
async def test_on_content_clears_status_once() -> None:
    events: asyncio.Queue = asyncio.Queue()
    state = {"filter": make_display_filter(), "streamed": False}
    _, _, on_content = event_loopbacks(events, content_state=state)
    await on_content("hello world")
    first = await events.get()
    assert first == {"type": "status", "text": ""}
    second = await events.get()
    assert second["type"] == "token"
    assert state["streamed"] is True
    # Second call does not re-emit status clear.
    await on_content(" more")
    third = await events.get()
    assert third["type"] == "token"

def test_public_args_non_dict_and_private_skipped() -> None:
    assert _public_args("not-a-dict") == {}  # type: ignore[arg-type]
    assert _public_args(None) == {}  # type: ignore[arg-type]
    out = _public_args({"_secret": "hide", "query": "hello", 123: "num"})
    assert "_secret" not in out
    assert out["query"] == "hello"
    assert out["123"] == "num"
    long_val = _public_args({"q": "y" * 900})
    assert len(long_val["q"]) == 500

def test_display_result_truncates_with_marker() -> None:
    assert _display_result("short") == "short"
    assert _display_result(None) == ""
    big = "z" * 25000
    out = _display_result(big)
    assert "display truncated" in out
    assert str(len(big)) in out
    assert len(out) < len(big)

@pytest.mark.asyncio
async def test_stream_tool_rounds_success_relays() -> None:
    events: asyncio.Queue = asyncio.Queue()
    outcome: dict = {}

    async def _run(*args, **kwargs):
        assert kwargs.get("events") is events
        return ("ok-value",)

    collected = [i async for i in stream_tool_rounds(_run, outcome, events)]
    assert collected == []
    assert outcome["value"] == ("ok-value",)

@pytest.mark.asyncio
async def test_stream_tool_rounds_failure_records_error() -> None:
    events: asyncio.Queue = asyncio.Queue()
    outcome: dict = {}

    async def _boom(*args, **kwargs):
        raise RuntimeError("wheel-boom")

    collected = [i async for i in stream_tool_rounds(_boom, outcome, events)]
    assert collected == []
    assert isinstance(outcome.get("error"), RuntimeError)

@pytest.mark.asyncio
async def test_stream_tool_rounds_cancel_while_running() -> None:
    events: asyncio.Queue = asyncio.Queue()
    outcome: dict = {}

    async def _slow(*args, **kwargs):
        await asyncio.sleep(0.5)
        return "never"

    async def _consume():
        count = 0
        async for item in stream_tool_rounds(_slow, outcome, events):
            count += 1
            if count >= 1:
                break
        return count

    # Put one event then let the consumer break early; finally must cancel the task.
    await events.put({"type": "thinking", "content": "hi"})
    assert await asyncio.wait_for(_consume(), timeout=5) == 1

@pytest.mark.asyncio
async def test_stream_tool_rounds_cancel_logs_generic(monkeypatch) -> None:
    import realmock.domains.prep.agents.streaming as streaming_mod

    events: asyncio.Queue = asyncio.Queue()
    outcome: dict = {}
    await events.put(streaming_mod._PRODUCE_DONE)

    class _FakeTask:
        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            pass

        def __await__(self):
            async def _raise():
                raise ValueError("background-gone")

            return _raise().__await__()

    def _fake_create(coro):
        try:
            coro.close()
        except Exception:
            pass
        return _FakeTask()

    monkeypatch.setattr(streaming_mod.asyncio, "create_task", _fake_create)
    # Coro is never awaited in this path; close it to avoid warnings.
    warnings: list[str] = []
    monkeypatch.setattr(
        streaming_mod.logger, "warning", lambda *a, **k: warnings.append(str(a[0]))
    )

    async def _run(*args, **kwargs):
        return "x"

    collected = [i async for i in stream_tool_rounds(_run, outcome, events)]

    assert collected == []
    assert any("background task ended" in w for w in warnings)
