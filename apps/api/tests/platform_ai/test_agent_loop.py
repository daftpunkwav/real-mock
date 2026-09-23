"""Shared Agent loop and working memory."""

from __future__ import annotations

import asyncio

import pytest

from realmock.platform.capabilities.ai.agent import WorkingMemory, run_agent_loop
from realmock.platform.capabilities.ai.agent.loop import AgentHalt
from realmock.platform.capabilities.ai.context.manager import prepare_llm_context


class _FakeLLM:
    def __init__(self, replies: list[dict]) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.seen_messages: list[list[dict]] = []

    async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
        del temperature, tools, kwargs
        self.seen_messages.append([dict(m) for m in messages])
        idx = min(self.calls, len(self.replies) - 1)
        self.calls += 1
        return self.replies[idx]


class _FakeStreamLLM(_FakeLLM):
    """Fake LLM with ``chat_message_stream`` that emits event streams by round.

    ``rounds[i]`` is the event list for round i (reasoning deltas + final message);
    after the rounds are exhausted, reuse the last round. ``chat_message`` only counts fallbacks and should not normally be called.
    """

    def __init__(self, rounds: list[list[dict]]) -> None:
        super().__init__(replies=[{"role": "assistant", "content": "fallback"}])
        self.rounds = rounds

    async def chat_message_stream(self, messages, temperature=0.7, tools=None, **kwargs):
        del messages, temperature, tools, kwargs
        idx = min(self.calls, len(self.rounds) - 1)
        self.calls += 1
        for event in self.rounds[idx]:
            yield event


@pytest.mark.asyncio
async def test_agent_loop_streams_reasoning_and_assembles_rounds() -> None:
    """Streaming rounds: emit reasoning deltas through real-time callbacks (adding separators between rounds), and drive tool execution with message events."""
    llm = _FakeStreamLLM(
        rounds=[
            [
                {"type": "reasoning", "text": "Think first"},
                {"type": "reasoning", "text": "What to look up"},
                {
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": "{}"},
                            }
                        ],
                    },
                },
            ],
            [
                {"type": "reasoning", "text": "Summary observations"},
                {
                    "type": "message",
                    "message": {"role": "assistant", "content": "Final answer." * 60},
                },
            ],
        ]
    )
    executed: list[str] = []
    seen_thinking: list[str] = []

    async def execute(name: str, args: dict) -> str:
        executed.append(name)
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=4,
        on_thinking=seen_thinking.append,
    )
    assert executed == ["lookup"]
    # Reasoning deltas arrive in real time; the first segment of the second round includes an inter-round separator
    assert seen_thinking == ["Think first", "What to look up", "\n\nSummary observations"]
    # The persistence channel concatenates content by round (without a display-only separator prefix)
    assert result.thinking == "Think firstWhat to look up\n\nSummary observations"
    assert result.final_content == "Final answer." * 60
    # Streaming was used end-to-end without falling back to non-streaming
    assert llm.seen_messages == []


@pytest.mark.asyncio
async def test_agent_loop_falls_back_when_stream_unsupported() -> None:
    """When the client declares streaming unsupported (NotImplementedError), fall back to non-streaming chat_message."""

    class _NoStreamLLM(_FakeLLM):
        async def chat_message_stream(self, *args, **kwargs):
            raise NotImplementedError("responses protocol does not support streaming toolwheel")
            yield  # pragma: no cover

    llm = _NoStreamLLM([{"role": "assistant", "content": "Direct answer." * 60, "tool_calls": None}])

    async def execute(name: str, args: dict) -> str:
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=3,
    )
    assert result.final_content == "Direct answer." * 60
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_agent_loop_first_round_content_skips_second_llm() -> None:
    llm = _FakeLLM([{"role": "assistant", "content": "Complete answer." * 60, "tool_calls": None}])
    executed: list[str] = []

    async def execute(name: str, args: dict) -> str:
        executed.append(name)
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "web_search"}}],
        execute=execute,
        max_rounds=3,
    )
    assert result.final_content == "Complete answer." * 60
    assert result.tool_used is False
    assert executed == []
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_agent_loop_drift_retry_nudges_short_preamble_once() -> None:
    """Opt-in correction: do not treat a short tool-free action narration as the final answer; inject a one-time prompt and retry;
    if the model insists on the same output, accept it as the final answer (bounded, with no infinite loop)."""
    preamble = "I will search recent interview experiences in parallel and compile the most frequent topics."
    llm = _FakeLLM([{"role": "assistant", "content": preamble, "tool_calls": None}])
    executed: list[str] = []

    async def execute(name: str, args: dict) -> str:
        executed.append(name)
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "Search recent interview notes"}],
        tools=[{"type": "function", "function": {"name": "web_search"}}],
        execute=execute,
        max_rounds=4,
        drift_retry=True,
    )
    assert result.final_content == preamble
    assert executed == []
    assert llm.calls == 2, "A short narration should trigger exactly one corrective retry"
    # Inject the corrective prompt only with the second call, and do not persist it in the message sequence
    assert "called no tool" in llm.seen_messages[1][-1]["content"]
    assert llm.seen_messages[0][-1].get("content") == "Search recent interview notes"
    assert not any(
        "called no tool" in str(m.get("content")) for m in result.messages
    )


@pytest.mark.asyncio
async def test_agent_loop_drift_retry_skips_after_tools_used() -> None:
    """A short closing response after tool use is a valid final answer and should not trigger correction."""
    llm = _FakeLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "function": {"name": "lookup", "arguments": "{}"}}
                ],
            },
            {"role": "assistant", "content": "Combined result", "tool_calls": None},
        ]
    )

    async def execute(name: str, args: dict) -> str:
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=4,
        drift_retry=True,
    )
    assert result.final_content == "Combined result"
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_agent_loop_drift_retry_off_by_default() -> None:
    """When drift_retry is disabled, preserve the original semantics: finalize short body text immediately without an additional call."""
    llm = _FakeLLM([{"role": "assistant", "content": "I'll search for it.", "tool_calls": None}])

    async def execute(name: str, args: dict) -> str:
        return "ok"

    await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "web_search"}}],
        execute=execute,
        max_rounds=3,
    )
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_agent_loop_forwards_reasoning_to_callback() -> None:
    """When message contains reasoning, invoke on_thinking for each round and aggregate the result into LoopResult.thinking."""
    llm = _FakeLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "reasoning": "First decide what to look up",
                "tool_calls": [
                    {"id": "c1", "function": {"name": "lookup", "arguments": "{}"}}
                ],
            },
            {
                "role": "assistant",
                "content": "Final answer." * 60,
                "reasoning": "Structure the answer",
                "tool_calls": None,
            },
        ]
    )

    async def execute(name: str, args: dict) -> str:
        return "ok"

    seen: list[str] = []
    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=3,
        on_thinking=seen.append,
    )
    assert seen == ["First decide what to look up", "\n\nStructure the answer"], (
        "The first segment of the second round in the display channel should include an inter-round separator"
    )
    assert result.thinking == "First decide what to look up\n\nStructure the answer"
    # Return reasoning for display only; do not write it to the message sequence
    assert all("reasoning" not in m for m in result.messages)


@pytest.mark.asyncio
async def test_agent_loop_content_after_tools_is_final() -> None:
    """When the model returns body text after using a tool, treat that text as the final answer and do not perform a second tool-free generation."""
    llm = _FakeLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {"name": "lookup", "arguments": '{"q":"x"}'},
                    }
                ],
            },
            {"role": "assistant", "content": "Combined result", "tool_calls": None},
        ]
    )

    async def execute(name: str, args: dict) -> str:
        assert name == "lookup"
        assert args.get("q") == "x"
        return "hit"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "Look it up"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=3,
    )
    assert result.tool_used is True
    assert result.final_content == "Combined result"
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert tool_msgs and "hit" in tool_msgs[0]["content"]
    # Exactly two LLM calls (tool round + closing round), with no extra generation
    assert llm.calls == 2


def test_working_memory_roundtrip_via_messages() -> None:
    mem = WorkingMemory()
    mem.remember("weak", "QPS was not explained clearly")
    mem.remember("asked", "Cache eviction policy")
    msgs = prepare_llm_context(
        [{"role": "system", "content": "Rules"}, {"role": "user", "content": "Hello"}],
        max_tokens=0,
        memory=mem,
    )
    loaded = WorkingMemory.load_from_messages(msgs)
    assert "QPS was not explained clearly" in loaded.weak_points
    assert loaded.asked


@pytest.mark.asyncio
async def test_agent_halt_appends_observation_and_stops() -> None:
    llm = _FakeLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "function": {"name": "ask_user", "arguments": "{}"}}
                ],
            },
            {"role": "assistant", "content": "Should not be reached", "tool_calls": None},
        ]
    )

    async def execute(name: str, args: dict) -> str:
        raise AgentHalt("Asked the user")

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "ask_user"}}],
        execute=execute,
        max_rounds=3,
    )
    assert result.halted is True
    assert result.final_content is None
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert tool_msgs and "Asked the user" in tool_msgs[0]["content"]
    # Do not enter another LLM round after halt
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_parallel_tools_keep_pairing() -> None:
    llm = _FakeLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "function": {"name": "slow", "arguments": "{}"}},
                    {"id": "c2", "function": {"name": "fast", "arguments": "{}"}},
                ],
            },
            {"role": "assistant", "content": "done", "tool_calls": None},
        ]
    )

    async def execute(name: str, args: dict) -> str:
        if name == "slow":
            await asyncio.sleep(0.05)
            return "slow-result"
        return "fast-result"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[
            {"type": "function", "function": {"name": "slow"}},
            {"type": "function", "function": {"name": "fast"}},
        ],
        execute=execute,
        max_rounds=2,
    )
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2"]
    assert "slow-result" in tool_msgs[0]["content"]
    assert "fast-result" in tool_msgs[1]["content"]
    # Return the model's post-tool response body directly as the final answer
    assert result.final_content == "done"


@pytest.mark.asyncio
async def test_agent_loop_last_round_injects_wrap_up_hint() -> None:
    """Inject a closing prompt into the final round (visible only to this call) without writing it to the persistent message sequence."""
    llm = _FakeLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "function": {"name": "lookup", "arguments": "{}"}}
                ],
            },
            {"role": "assistant", "content": "Closing answer", "tool_calls": None},
        ]
    )

    async def execute(name: str, args: dict) -> str:
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=2,
    )
    # No prompt in the first round; the final round (the last tool opportunity) includes a closing prompt
    assert llm.seen_messages[0][-1]["role"] != "system"
    hint = llm.seen_messages[1][-1]
    assert hint["role"] == "system" and "last round of tool calling" in hint["content"]
    assert result.final_content == "Closing answer"
    assert not any(
        m.get("role") == "system" and "last round of tool calling" in str(m.get("content"))
        for m in result.messages
    ), "The closing prompt must not be persisted in the message sequence"


@pytest.mark.asyncio
async def test_agent_loop_no_hint_when_first_round() -> None:
    """Do not inject a prompt when only one round is available (there is no “budget nearly exhausted” semantic)."""
    llm = _FakeLLM([{"role": "assistant", "content": "Direct answer", "tool_calls": None}])

    async def execute(name: str, args: dict) -> str:
        return "ok"

    await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=1,
    )
    assert all(
        not (m.get("role") == "system" and "Final round" in str(m.get("content")))
        for call in llm.seen_messages
        for m in call
    )


@pytest.mark.asyncio
async def test_agent_loop_forwards_content_deltas_to_callback() -> None:
    """Speculative streaming: raw body-text deltas of every round reach ``on_content`` live."""
    llm = _FakeStreamLLM(
        rounds=[
            [
                {"type": "text", "text": "Working "},
                {"type": "text", "text": "on it"},
                {
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": "Working on it",
                        "tool_calls": [
                            {"id": "c1", "function": {"name": "lookup", "arguments": "{}"}}
                        ],
                    },
                },
            ],
            [
                {"type": "text", "text": "Final"},
                {"type": "message", "message": {"role": "assistant", "content": "Final"}},
            ],
        ]
    )
    seen: list[str] = []

    async def execute(name: str, args: dict) -> str:
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=3,
        on_content=seen.append,
    )
    # Round 1 text stays buffered (a pre-tool round may still be drift-retried);
    # round 2 is post-tool, so its content streams live.
    assert seen == ["Final"]
    assert result.final_content == "Final"
    assert result.tool_used is True


@pytest.mark.asyncio
async def test_agent_loop_budget_overflow_gets_synthetic_results() -> None:
    """Calls beyond ``max_tools_per_round`` are declared, then answered with an explicit
    budget observation so protocol pairing holds and the model knows they never ran."""
    calls = [
        {"id": f"c{i}", "function": {"name": "lookup", "arguments": "{}"}}
        for i in range(1, 6)
    ]
    llm = _FakeLLM([
        {"role": "assistant", "content": None, "tool_calls": calls},
        {"role": "assistant", "content": "done", "tool_calls": None},
    ])
    executed: list[str] = []

    async def execute(name: str, args: dict) -> str:
        executed.append(name)
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=3,
        max_tools_per_round=2,
    )
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2", "c3", "c4", "c5"]
    assert "Not executed" in tool_msgs[2]["content"]
    assert "Not executed" in tool_msgs[4]["content"]
    assert executed == ["lookup", "lookup"]
    assistant = next(
        m for m in result.messages if m.get("role") == "assistant" and m.get("tool_calls")
    )
    assert len(assistant["tool_calls"]) == 5, "all requested calls stay declared for pairing"
    assert result.final_content == "done"


@pytest.mark.asyncio
async def test_agent_loop_drift_hint_quotes_narration() -> None:
    """The correction hint quotes the rejected narration — the model never saw that message."""
    preamble = "I will search recent interview experiences in parallel."
    llm = _FakeLLM([{"role": "assistant", "content": preamble, "tool_calls": None}])

    async def execute(name: str, args: dict) -> str:
        return "ok"

    await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "web_search"}}],
        execute=execute,
        max_rounds=4,
        drift_retry=True,
    )
    hint = llm.seen_messages[1][-1]
    assert hint["role"] == "system" and "called no tool" in hint["content"]
    assert preamble in hint["content"], "the unacted announcement must be quoted back"


@pytest.mark.asyncio
async def test_already_logged_tool_error_is_not_logged_again(monkeypatch) -> None:
    """A guard that persisted its own failure must not be double-counted here."""
    llm = _FakeLLM([
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "c1",
                "type": "function",
                "function": {"name": "lookup", "arguments": "{}"},
            }],
        },
        {"role": "assistant", "content": "Recovered." * 60, "tool_calls": None},
    ])
    logged: list[dict] = []
    monkeypatch.setattr(
        "realmock.platform.capabilities.ai.agent.loop.log_agent_error",
        lambda **kwargs: logged.append(kwargs),
    )

    class _GuardedFailure(Exception):
        def __init__(self) -> None:
            super().__init__("timed out after 30s")
            self.error_kind = "timeout"
            self.already_logged = True

    async def execute(name: str, args: dict) -> str:
        raise _GuardedFailure()

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=3,
    )
    assert logged == []  # the guard owns that record
    tool_msg = next(m for m in result.messages if m.get("role") == "tool")
    assert tool_msg["content"].startswith("Tool execution failed:")


@pytest.mark.asyncio
async def test_plain_tool_error_is_logged_once(monkeypatch) -> None:
    """An unmarked tool exception produces exactly one error record."""
    llm = _FakeLLM([
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "c1",
                "type": "function",
                "function": {"name": "lookup", "arguments": "{}"},
            }],
        },
        {"role": "assistant", "content": "Recovered." * 60, "tool_calls": None},
    ])
    logged: list[dict] = []
    monkeypatch.setattr(
        "realmock.platform.capabilities.ai.agent.loop.log_agent_error",
        lambda **kwargs: logged.append(kwargs),
    )

    async def execute(name: str, args: dict) -> str:
        raise RuntimeError("boom")

    await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=3,
        error_context={"domain": "interview", "session": "7"},
    )
    assert len(logged) == 1
    assert logged[0]["kind"] == "tool_failed"
    assert logged[0]["tool"] == "lookup"
    assert logged[0]["domain"] == "interview"


def _tool_call_reply(name: str = "lookup") -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "c1", "function": {"name": name, "arguments": "{}"}}],
    }


@pytest.mark.asyncio
async def test_agent_loop_final_round_omits_tools() -> None:
    """final_round_tool_free: the last request carries no tools; its text is the answer."""
    seen_tools: list = []

    class _RecordingLLM:
        calls = 0

        async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
            del messages, temperature, kwargs
            self.calls += 1
            seen_tools.append(tools)
            if self.calls == 1:
                return _tool_call_reply()
            return {"role": "assistant", "content": "final answer text", "tool_calls": None}

    llm = _RecordingLLM()

    async def execute(name: str, args: dict) -> str:
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=2,
        final_round_tool_free=True,
    )
    assert seen_tools[0] is not None, "tool rounds keep the tools parameter"
    assert seen_tools[1] is None, "the final round must not carry tools"
    assert result.final_content == "final answer text"


@pytest.mark.asyncio
async def test_agent_loop_round_retry_recovers_transient_failure() -> None:
    """One transient round failure is retried; the second attempt answers."""

    class _FlakyLLM(_FakeLLM):
        async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
            self.seen_messages.append([dict(m) for m in messages])
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("hung round")
            return self.replies[0]

    llm = _FlakyLLM([{"role": "assistant", "content": "recovered", "tool_calls": None}])

    async def execute(name: str, args: dict) -> str:
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=3,
        round_retries=1,
    )
    assert llm.calls == 2
    assert result.final_content == "recovered"


@pytest.mark.asyncio
async def test_agent_loop_round_retry_exhausts_and_breaks() -> None:
    """With retries exhausted the loop breaks exactly like the old fail-fast."""

    class _BoomLLM:
        calls = 0

        async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
            del messages, temperature, tools, kwargs
            self.calls += 1
            raise RuntimeError("provider down")

    llm = _BoomLLM()

    async def execute(name: str, args: dict) -> str:
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=3,
        round_retries=1,
    )
    assert llm.calls == 2, "one initial attempt plus exactly one retry"
    assert result.final_content is None


@pytest.mark.asyncio
async def test_agent_loop_no_retry_by_default() -> None:
    """round_retries defaults to 0: other loops keep the fail-fast behavior."""

    class _BoomLLM:
        calls = 0

        async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
            del messages, temperature, tools, kwargs
            self.calls += 1
            raise RuntimeError("provider down")

    llm = _BoomLLM()

    async def execute(name: str, args: dict) -> str:
        return "ok"

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=3,
    )
    assert llm.calls == 1
    assert result.final_content is None


@pytest.mark.asyncio
async def test_agent_loop_countdown_ladder_tiers() -> None:
    """Outer countdown window is advisory, inner half urgent, last round wrap-up."""
    llm = _FakeLLM([_tool_call_reply() for _ in range(6)])

    async def execute(name: str, args: dict) -> str:
        return "ok"

    await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=6,
        countdown_rounds=4,
    )
    contents = [[str(m.get("content")) for m in call] for call in llm.seen_messages]
    soft = "Start concluding your evidence gathering"
    urgent = "Do not start new explorations"
    wrapup = "last round of tool calling"
    assert not any(soft in c or urgent in c for c in contents[0])
    assert any("Only 4" in c and soft in c for c in contents[1])
    assert any("Only 3" in c and soft in c for c in contents[2])
    assert any("Only 2" in c and urgent in c for c in contents[3])
    assert any("Only 1" in c and urgent in c for c in contents[4])
    assert any(wrapup in c for c in contents[5])
    assert not any(soft in c or urgent in c for c in contents[5])


@pytest.mark.asyncio
async def test_agent_loop_countdown_hint_lands_after_prepare() -> None:
    """The per-round nudge is appended after the prepare hook, not inside it.

    Domain prepare hooks rewrite/compact history; a per-round varying nudge
    that flows through them ends up in the stable head and breaks the
    provider prefix cache.
    """
    llm = _FakeLLM([_tool_call_reply() for _ in range(2)])

    async def execute(name: str, args: dict) -> str:
        return "ok"

    async def prepare(messages: list[dict]) -> list[dict]:
        return [*messages, {"role": "system", "content": "prepared-tail"}]

    await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=2,
        countdown_rounds=1,
        prepare_messages=prepare,
    )
    contents = [str(m.get("content")) for m in llm.seen_messages[0]]
    assert "prepared-tail" in contents
    assert contents.index("prepared-tail") < len(contents) - 1, (
        "the countdown nudge must be appended after the prepare hook"
    )
    assert "Only 1" in contents[-1]
    assert "Do not start new explorations" in contents[-1], (
        "countdown_rounds=1 has no outer half: its single in-window nudge "
        "must be urgent, not advisory"
    )


@pytest.mark.asyncio
async def test_agent_loop_wrap_up_hint_lands_after_prepare() -> None:
    """The closing prompt is appended after the prepare hook, like the countdown nudge.

    A domain compaction hook hoists system-role messages to the stable head;
    a closing prompt flowing through it would leave the strongest attention
    position exactly when the tool-free final answer matters most.
    """
    llm = _FakeLLM([
        _tool_call_reply(),
        {"role": "assistant", "content": "Closing answer", "tool_calls": None},
    ])

    async def execute(name: str, args: dict) -> str:
        return "ok"

    async def prepare(messages: list[dict]) -> list[dict]:
        return [*messages, {"role": "system", "content": "prepared-tail"}]

    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute=execute,
        max_rounds=2,
        wrap_up_hint={"role": "system", "content": "last round of tool calling"},
        prepare_messages=prepare,
    )
    contents = [str(m.get("content")) for m in llm.seen_messages[1]]
    assert "prepared-tail" in contents
    assert contents[-1].startswith("last round of tool calling"), (
        "the closing prompt must be appended after the prepare hook"
    )
    assert result.final_content == "Closing answer"
    assert not any(
        "last round of tool calling" in str(m.get("content")) for m in result.messages
    ), "The closing prompt must not be persisted in the message sequence"
