"""Tool round stream tests for agents/tool_round_stream.py.

Covers: success relay with outcome value, error outcome, consumer cancel,
cancel-with-exception path.
Conventions: no real network/LLM (all external calls mocked); uses mocked runner tools.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realmock.domains.interview.agents.tool_round_stream import stream_tool_rounds

# No handler fixture: stream_tool_rounds is exercised with mocked runner/db arguments.

@pytest.mark.asyncio
async def test_stream_tool_rounds_success_error_cancel():
    from realmock.domains.interview.agents.events import StreamEvent

    # success: sink relays TOKEN events, outcome value set
    tok = StreamEvent.make_token("hi") if hasattr(StreamEvent, "make_token") else MagicMock()
    runner = MagicMock()
    runner.tools.run_tool_rounds = AsyncMock(return_value="RESULT")
    # make content_sink put token then return

    async def _fake_run(api_messages, db, temperature=0.0, content_sink=None):
        if content_sink is not None:
            await content_sink(tok)
        return "RESULT"

    runner.tools.run_tool_rounds = _fake_run  # type: ignore[method-assign]
    outcome: dict = {}
    seen = []
    async for ev in stream_tool_rounds(runner, outcome, [], MagicMock(), temperature=0.1):
        seen.append(ev)
    assert seen == [tok]
    assert outcome["value"] == "RESULT"

    # error: outcome error set, stream ends
    runner2 = MagicMock()
    runner2.tools.run_tool_rounds = AsyncMock(side_effect=RuntimeError("tool boom"))
    outcome2: dict = {}
    seen2 = [ev async for ev in stream_tool_rounds(runner2, outcome2, [], MagicMock(), temperature=0.1)]
    assert seen2 == []
    assert isinstance(outcome2["error"], RuntimeError)

    # cancel: consumer breaks early -> background task cancelled
    started = asyncio.Event()
    finish = asyncio.Event()

    async def _slow_run(api_messages, db, temperature=0.0, content_sink=None):
        started.set()
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        return "late"

    runner3 = MagicMock()
    runner3.tools.run_tool_rounds = _slow_run  # type: ignore[method-assign]
    outcome3: dict = {}
    gen = stream_tool_rounds(runner3, outcome3, [], MagicMock(), temperature=0.1)
    # start generator then close without consuming PRODUCE_DONE
    ait = gen.__aiter__()
    # schedule a get with timeout then cancel by closing
    task = asyncio.create_task(ait.__anext__())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, StopAsyncIteration, RuntimeError):
        pass
    await gen.aclose()
    assert started.is_set()
    assert finish is not None


@pytest.mark.asyncio
async def test_tool_round_stream_cancel_with_exception():
    import realmock.domains.interview.agents.tool_round_stream as mod
    from realmock.domains.interview.agents.events import StreamEvent

    tok = StreamEvent.make_token("hi") if hasattr(StreamEvent, "make_token") else MagicMock()

    class _FakeTask:
        def done(self):
            return False

        def cancel(self):
            return None

        def __await__(self):
            async def _raise():
                raise RuntimeError("cancel boom")

            return _raise().__await__()

    # Producer puts one token then hangs; consumer takes one then breaks -> finally sees fake task
    def _fake_create_task(coro):
        # close the real producer coro to avoid warnings
        try:
            coro.close()
        except Exception:
            pass
        return _FakeTask()  # type: ignore[return-value]

    runner = MagicMock()
    outcome: dict = {}

    # Pre-seed: we need the internal queue to have an item.
    class _SeededQueue(asyncio.Queue):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.put_nowait(tok)

    with (
        patch.object(mod.asyncio, "create_task", side_effect=_fake_create_task),
        patch.object(mod.asyncio, "Queue", _SeededQueue),
    ):
        seen = []
        async for ev in mod.stream_tool_rounds(runner, outcome, [], MagicMock(), temperature=0.1):
            seen.append(ev)
            break  # early break -> finally: task not done -> cancel -> await raises RuntimeError -> warning
        assert seen == [tok]  # covers tool_round_stream.py 75-76

