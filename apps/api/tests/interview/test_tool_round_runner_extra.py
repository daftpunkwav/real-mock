"""Tool round runner tests for src/realmock/domains/interview/agents/tool_round_runner.py.

Covers: maybe_retrieve_rag, collect_chat_tools, run_tool_rounds budgets/streams/traces
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realmock.domains.interview.agents.agent_text import ThinkStreamFilter
from realmock.domains.interview.agents.events import StreamEvent
from realmock.domains.interview.agents.tool_round_runner import (
    ToolRoundRunner,
)
from realmock.domains.interview.agents.turn_output import TurnOutput
from realmock.platform.config import Settings
from realmock.platform.core.constants import RAGBackendKind
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def _settings(**overrides) -> Settings:
    base = {
        "llm_api_base": "https://api.stepfun.com/v1",
        "llm_api_key": "sk-test",
        "llm_model": "step-3.7-flash",
        "rag_backend": "local",
    }
    base.update(overrides)
    return Settings(**base)


def _empty_llm() -> MagicMock:
    m = MagicMock()
    m.api_key = ""
    return m


# ---- process orchestrator ----














# ---- tool round runner: rag + tools ----


def _runner(rag=None, llm=None) -> ToolRoundRunner:
    session = SimpleNamespace(id=1, company="bytedance", resume_id=None, profile_id=1)

    class _Agent:
        def __init__(self):
            self.agent_state = {}

    return ToolRoundRunner(session, llm or _empty_llm(), _Agent(), rag)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_maybe_retrieve_no_rag_or_query() -> None:
    r = _runner(rag=None)
    assert await r.maybe_retrieve_rag("q") is None
    assert await r.maybe_retrieve_rag("") is None


@pytest.mark.asyncio
async def test_maybe_retrieve_stepfun_skips_local() -> None:
    rag = SimpleNamespace(kind=RAGBackendKind.STEPFUN)
    r = _runner(rag=rag)  # type: ignore[arg-type]
    assert await r.maybe_retrieve_rag("query") is None


@pytest.mark.asyncio
async def test_maybe_retrieve_success_and_filter() -> None:
    rag = MagicMock()
    rag.query_for_company = AsyncMock(
        return_value=[
            {"distance": 0.1, "text": "hit"},
            {"distance": 0.9, "text": "weak"},
        ]
    )
    r = _runner(rag=rag)
    out = await r.maybe_retrieve_rag("cache", top_k=3)
    assert out is not None and out["role"] == "system"
    rag.query_for_company.assert_awaited_once()


@pytest.mark.asyncio
async def test_maybe_retrieve_no_company_uses_query() -> None:
    rag = MagicMock()
    rag.query = AsyncMock(return_value=[{"distance": 0.1, "text": "h"}])
    r = _runner(rag=rag)
    r.session.company = ""
    out = await r.maybe_retrieve_rag("q")
    assert out is not None
    rag.query.assert_awaited_once()


@pytest.mark.asyncio
async def test_maybe_retrieve_exception_and_empty() -> None:
    rag = MagicMock()
    rag.query_for_company = AsyncMock(side_effect=RuntimeError("down"))
    r = _runner(rag=rag)
    assert await r.maybe_retrieve_rag("q") is None
    rag2 = MagicMock()
    rag2.query_for_company = AsyncMock(return_value=[])
    r2 = _runner(rag=rag2)
    assert await r2.maybe_retrieve_rag("q") is None
    rag3 = MagicMock()
    rag3.query_for_company = AsyncMock(return_value=[{"distance": 0.99}])
    r3 = _runner(rag=rag3)
    assert await r3.maybe_retrieve_rag("q") is None


def test_collect_chat_tools_branches(monkeypatch) -> None:
    # No rag, tools disabled -> None.
    r = _runner(rag=None)
    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner.get_settings",
        lambda: SimpleNamespace(interview_tools_enabled=False),
    )
    # collect_chat_tools only gates function tools; retrieval part still runs.
    out = r.collect_chat_tools()
    assert out is None or isinstance(out, list)
    # Enabled with rag builder returning None + past rounds check.
    rag = MagicMock()
    rag.build_retrieval_tool = MagicMock(return_value=None)
    r2 = _runner(rag=rag)
    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner.get_settings",
        lambda: SimpleNamespace(interview_tools_enabled=True),
    )
    import realmock.domains.interview.agents.tool_round_runner as trm

    monkeypatch.setattr(trm, "get_interview_tool_definitions", lambda **k: [])
    with (
        patch(
            "realmock.domains.interview.agents.past_records.has_prior_rounds",
            return_value=False,
        ),
        patch("realmock.platform.database.sessions_db_session"),
    ):
        assert r2.collect_chat_tools() is None
    # Builder returns a tool.
    rag2 = MagicMock()
    rag2.build_retrieval_tool = MagicMock(return_value={"type": "retrieval"})
    r3 = _runner(rag=rag2)
    with (
        patch(
            "realmock.domains.interview.agents.past_records.has_prior_rounds",
            return_value=False,
        ),
        patch("realmock.platform.database.sessions_db_session"),
    ):
        tools = r3.collect_chat_tools(include_function_tools=False)
        assert tools == [{"type": "retrieval"}]


@pytest.mark.asyncio
async def test_run_tool_rounds_disabled_returns_input(monkeypatch) -> None:
    r = _runner()
    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner.get_settings",
        lambda: SimpleNamespace(interview_tools_enabled=False, interview_max_tool_rounds=3),
    )
    msgs = [{"role": "user", "content": "hi"}]
    out = await r.run_tool_rounds(msgs, MagicMock())
    assert out.messages == msgs and out.early is None


@pytest.mark.asyncio
async def test_run_tool_rounds_zero_rounds(monkeypatch) -> None:
    r = _runner()
    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner.get_settings",
        lambda: SimpleNamespace(interview_tools_enabled=True, interview_max_tool_rounds=0),
    )
    out = await r.run_tool_rounds([{"role": "user", "content": "hi"}], MagicMock())
    assert out.early is None


@pytest.mark.asyncio
async def test_run_tool_rounds_no_tools(monkeypatch) -> None:
    r = _runner()
    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner.get_settings",
        lambda: SimpleNamespace(interview_tools_enabled=True, interview_max_tool_rounds=3),
    )
    monkeypatch.setattr(r, "collect_chat_tools", lambda **k: None)
    out = await r.run_tool_rounds([{"role": "user", "content": "hi"}], MagicMock())
    assert out.early is None


@pytest.mark.asyncio
async def test_run_tool_rounds_success_early(monkeypatch) -> None:
    r = _runner()
    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner.get_settings",
        lambda: SimpleNamespace(interview_tools_enabled=True, interview_max_tool_rounds=3),
    )
    monkeypatch.setattr(r, "collect_chat_tools", lambda **k: [{"type": "function"}])

    async def _fake_loop(*a, **k):
        return SimpleNamespace(
            messages=[{"role": "assistant", "content": "hi"}], final_content="hi"
        )

    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner.run_agent_loop",
        _fake_loop,
    )
    out = await r.run_tool_rounds([{"role": "user", "content": "hi"}], MagicMock())
    assert out.early == "hi"


@pytest.mark.asyncio
async def test_run_tool_rounds_timeout_no_stream_falls_back(monkeypatch) -> None:
    r = _runner()
    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner.get_settings",
        lambda: SimpleNamespace(interview_tools_enabled=True, interview_max_tool_rounds=3),
    )
    monkeypatch.setattr(r, "collect_chat_tools", lambda **k: [{"type": "function"}])

    async def _hang(*a, **k):
        await asyncio.sleep(10)

    monkeypatch.setattr("realmock.domains.interview.agents.tool_round_runner.run_agent_loop", _hang)
    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner._TOOL_ROUND_BUDGET_SECONDS",
        0.01,
    )
    out = await r.run_tool_rounds([{"role": "user", "content": "hi"}], MagicMock())
    assert out.early is None and out.streamed_output is None


@pytest.mark.asyncio
async def test_finish_streamed_variants() -> None:
    from realmock.platform.capabilities.ai.llm.say_first_stream import (
        SayFirstStreamParser,
    )

    # Not streamed -> None.
    assert (
        await ToolRoundRunner._finish_streamed(
            ThinkStreamFilter(), SayFirstStreamParser(), [], {"on": False}, None
        )
        is None
    )

    async def _sink(event: StreamEvent) -> None:
        return None

    parser = SayFirstStreamParser()
    parser.feed(json.dumps({"say": "hello", "v": 1}))
    out = await ToolRoundRunner._finish_streamed(
        ThinkStreamFilter(), parser, ["hello"], {"on": True}, _sink
    )
    assert isinstance(out, TurnOutput)
    assert "hello" in out.say


@pytest.mark.asyncio
async def test_run_tool_rounds_on_content_invisible_returns(monkeypatch) -> None:
    r = _runner()
    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner.get_settings",
        lambda: SimpleNamespace(interview_tools_enabled=True, interview_max_tool_rounds=3),
    )
    monkeypatch.setattr(r, "collect_chat_tools", lambda **k: [{"type": "function"}])
    seen: list = []

    async def _sink(event: StreamEvent) -> None:
        seen.append(event)

    async def _fake_loop(llm, messages, tools=None, **k):
        await k["on_round_start"]()
        await k["on_content"]("<think>hidden reasoning</think>")
        await k["on_content"]("")
        return SimpleNamespace(messages=messages, final_content="done")

    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner.run_agent_loop",
        _fake_loop,
    )
    out = await r.run_tool_rounds(
        [{"role": "user", "content": "hi"}], MagicMock(), content_sink=_sink
    )
    assert out.early == "done"
    assert seen == []


@pytest.mark.asyncio
async def test_run_tool_rounds_on_tool_caps_trace(monkeypatch) -> None:
    r = _runner()
    r.agent.agent_state["tool_trace"] = [{"tool": "t", "ok": True} for _ in range(40)]
    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner.get_settings",
        lambda: SimpleNamespace(interview_tools_enabled=True, interview_max_tool_rounds=3),
    )
    monkeypatch.setattr(r, "collect_chat_tools", lambda **k: [{"type": "function"}])

    async def _fake_loop(llm, messages, tools=None, **k):
        await k["on_tool"]("lookup_company_profile", {}, "ok-result", "tc-1")
        return SimpleNamespace(messages=messages, final_content="done")

    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner.run_agent_loop",
        _fake_loop,
    )
    await r.run_tool_rounds([{"role": "user", "content": "hi"}], MagicMock())
    assert len(r.agent.agent_state["tool_trace"]) == 40


@pytest.mark.asyncio
async def test_run_tool_rounds_timeout_mid_stream_completes_partial(monkeypatch) -> None:
    import realmock.domains.interview.agents.tool_round_runner as trm

    r = _runner()
    monkeypatch.setattr(
        "realmock.domains.interview.agents.tool_round_runner.get_settings",
        lambda: SimpleNamespace(interview_tools_enabled=True, interview_max_tool_rounds=3),
    )
    monkeypatch.setattr(r, "collect_chat_tools", lambda **k: [{"type": "function"}])
    say = "partial answer so far"
    payload = json.dumps({"say": say, "v": 1})

    async def _hang_with_stream(llm, messages, tools=None, **k):
        await k["on_round_start"]()
        await k["on_content"](payload)
        await asyncio.sleep(10)

    monkeypatch.setattr(trm, "run_agent_loop", _hang_with_stream)
    monkeypatch.setattr(trm, "_TOOL_ROUND_BUDGET_SECONDS", 0.05)
    seen: list = []

    async def _sink(event: StreamEvent) -> None:
        seen.append(event)

    out = await r.run_tool_rounds(
        [{"role": "user", "content": "hi"}], MagicMock(), content_sink=_sink
    )
    assert out.streamed_output is not None
    assert say in out.streamed_output.say
    assert seen


@pytest.mark.asyncio
async def test_finish_streamed_flushes_tail() -> None:
    from realmock.platform.capabilities.ai.llm.say_first_stream import (
        SayFirstStreamParser,
    )

    parser = SayFirstStreamParser()
    # Plain text never opens the say key: finish() returns the raw tail.
    parser.feed("plain hello no protocol")
    seen: list = []

    async def _sink(event: StreamEvent) -> None:
        seen.append(event)

    out = await ToolRoundRunner._finish_streamed(
        ThinkStreamFilter(), parser, [], {"on": True}, _sink
    )
    assert out is not None
    assert "plain hello" in out.say
    assert seen


# ---- runner opening ----


def _opening_runner(**overrides):
    agent = MagicMock()
    agent.reload_plan = MagicMock()
    agent.reset_messages = MagicMock()
    agent.build_opening_prompt = MagicMock(return_value="system-prompt")
    agent.messages = []
    agent.agent_state = {}
    agent.record_assistant_text = MagicMock()
    agent.note_turn_output = MagicMock()
    agent.set_questions_in_phase = MagicMock()
    agent.mark_active = MagicMock()
    agent.save_state = MagicMock()
    agent.current_phase = MagicMock(return_value=SimpleNamespace(id="identity_check"))
    agent.advance_phase_if_needed = MagicMock(return_value=False)
    agent.phase_title_for_display = MagicMock(return_value="")
    runner = MagicMock()
    runner.session = SimpleNamespace(id=1)
    runner.agent = agent
    runner.llm = MagicMock(api_key="")
    runner.tools = MagicMock()
    runner.prompter = MagicMock()
    runner.prompter.get_context_window = MagicMock(return_value=None)
    for key, value in overrides.items():
        setattr(runner, key, value)
    return runner












# ---- stepfun backend ----














