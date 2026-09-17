"""Opening runner tests for src/realmock/domains/interview/agents/runner_opening.py.

Covers: stream_opening streamed/early/say-first/tool-error/ledger-error paths
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realmock.domains.interview.agents.events import EventKind, StreamEvent
from realmock.domains.interview.agents.tool_round_runner import (
    ToolRoundResult,
    ToolRoundRunner,
)
from realmock.domains.interview.agents.turn_output import TurnOutput
from realmock.platform.config import Settings
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


@pytest.mark.asyncio
async def test_stream_opening_streamed_output_path() -> None:
    from realmock.domains.interview.agents.interviewer import runner_opening as romod

    runner = _opening_runner()
    streamed = TurnOutput(say="hello", phase_complete=False)
    result = ToolRoundResult([{"role": "user", "content": "x"}], None, streamed)

    async def _rounds(runner_, outcome, messages, db, temperature=0.8):
        outcome["value"] = result
        if False:
            yield

    with (
        patch.object(romod, "ensure_plan", new=AsyncMock()),
        patch.object(romod, "stream_tool_rounds", side_effect=_rounds),
        patch.object(romod, "maybe_fold_history", new=AsyncMock(return_value=False)),
        patch.object(romod, "append_turn", return_value={}),
    ):
        events = [e async for e in romod.stream_opening(runner, MagicMock())]
    assert any(e.kind == EventKind.TURN_COMPLETE for e in events)
    runner.agent.mark_active.assert_called_once()


@pytest.mark.asyncio
async def test_stream_opening_early_path_emits_token() -> None:
    from realmock.domains.interview.agents.interviewer import runner_opening as romod

    runner = _opening_runner()
    early = json.dumps({"say": "hi early", "v": 1})
    result = ToolRoundResult([{"role": "user", "content": "x"}], early, None)

    async def _rounds(runner_, outcome, messages, db, temperature=0.8):
        outcome["value"] = result
        if False:
            yield

    with (
        patch.object(romod, "ensure_plan", new=AsyncMock()),
        patch.object(romod, "stream_tool_rounds", side_effect=_rounds),
        patch.object(romod, "maybe_fold_history", new=AsyncMock(return_value=False)),
        patch.object(romod, "append_turn", return_value={}),
    ):
        events = [e async for e in romod.stream_opening(runner, MagicMock())]
    assert any(e.kind == EventKind.TOKEN and e.token == "hi early" for e in events)


@pytest.mark.asyncio
async def test_stream_opening_say_first_path_and_phase_advance() -> None:
    from realmock.domains.interview.agents.interviewer import runner_opening as romod

    runner = _opening_runner()
    result = ToolRoundResult([{"role": "user", "content": "x"}], None, None)

    async def _rounds(runner_, outcome, messages, db, temperature=0.8):
        outcome["value"] = result
        if False:
            yield

    async def _say(llm, tools, messages, temperature=0.8):
        yield StreamEvent.make_token("live")
        yield TurnOutput(say="live", phase_complete=True)

    with (
        patch.object(romod, "ensure_plan", new=AsyncMock()),
        patch.object(romod, "stream_tool_rounds", side_effect=_rounds),
        patch.object(romod, "stream_say_first", side_effect=_say),
        patch.object(romod, "maybe_fold_history", new=AsyncMock(return_value=False)),
        patch.object(romod, "append_turn", return_value={}),
    ):
        events = [e async for e in romod.stream_opening(runner, MagicMock())]
    assert any(e.kind == EventKind.TOKEN for e in events)
    runner.agent.advance_phase_if_needed.assert_called_once()


@pytest.mark.asyncio
async def test_stream_opening_tool_error_yields_error_event() -> None:
    from realmock.domains.interview.agents.interviewer import runner_opening as romod

    runner = _opening_runner()

    async def _rounds(runner_, outcome, messages, db, temperature=0.8):
        outcome["error"] = RuntimeError("tool down")
        if False:
            yield

    with (
        patch.object(romod, "ensure_plan", new=AsyncMock()),
        patch.object(romod, "stream_tool_rounds", side_effect=_rounds),
    ):
        events = [e async for e in romod.stream_opening(runner, MagicMock())]
    assert events[-1].kind == EventKind.ERROR
    assert events[-1].error_code == "C0001"


@pytest.mark.asyncio
async def test_stream_opening_ledger_failure_yields_error() -> None:
    from realmock.domains.interview.agents.interviewer import runner_opening as romod

    runner = _opening_runner()
    result = ToolRoundResult([{"role": "user", "content": "x"}], None, TurnOutput(say="hi"))

    async def _rounds(runner_, outcome, messages, db, temperature=0.8):
        outcome["value"] = result
        if False:
            yield

    with (
        patch.object(romod, "ensure_plan", new=AsyncMock()),
        patch.object(romod, "stream_tool_rounds", side_effect=_rounds),
        patch.object(romod, "maybe_fold_history", new=AsyncMock(return_value=False)),
        patch.object(romod, "append_turn", side_effect=RuntimeError("db down")),
    ):
        events = [e async for e in romod.stream_opening(runner, MagicMock())]
    assert events[-1].kind == EventKind.ERROR


# ---- stepfun backend ----














