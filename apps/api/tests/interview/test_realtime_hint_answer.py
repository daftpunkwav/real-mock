"""Hint answer tests for agents/hint/hint_answer.py.

Covers: timeout/generic-exception None paths, no-tools None path,
tool trace trim with on_tool callbacks, execute path grounding.
Conventions: no real network/LLM (all external calls mocked); exercises _generate directly.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# No handler fixture: hint_answer helpers are exercised with mocked LLM/db/session.


@pytest.mark.asyncio
async def test_hint_answer_timeout_and_no_tools_and_note_trim():
    import realmock.domains.interview.agents.hint.hint_answer as mod

    # timeout -> None (patch inner _generate to raise TimeoutError)
    with patch.object(mod, "_generate", new=AsyncMock(side_effect=asyncio.TimeoutError())):
        assert (
            await mod.generate_full_reference_hint(
                llm=MagicMock(),
                db=MagicMock(),
                session=MagicMock(id=1),
                agent_state={},
                question="q",
                background="b",
                budget_seconds=0.01,
            )
            is None
        )

    # generic exception -> None
    with patch.object(mod, "_generate", new=AsyncMock(side_effect=RuntimeError("boom"))):
        assert (
            await mod.generate_full_reference_hint(
                llm=MagicMock(),
                db=MagicMock(),
                session=MagicMock(id=2),
                agent_state={},
                question="q",
                background="b",
            )
            is None
        )

    # empty writer answer -> None (zero-tool fast path)
    llm = MagicMock()
    llm.chat = AsyncMock(return_value="")
    session = MagicMock(id=3, company="", resume_id=None, profile_id=None)
    assert await mod._generate(llm, MagicMock(), session, {}, "q", "b", "zh") is None


@pytest.mark.asyncio
async def test_hint_answer_tool_trace_trim_and_on_tool(monkeypatch):
    from types import SimpleNamespace as NS

    import realmock.domains.interview.agents.hint.hint_answer as mod

    monkeypatch.setattr(mod, "github_tool_specs", lambda: [object()])
    monkeypatch.setattr(mod, "openai_tool", lambda spec: spec)

    seen = {}

    async def fake_loop(llm, messages, **kwargs):
        # exercise execute + on_tool via kwargs
        on_tool = kwargs.get("on_tool")
        execute = kwargs.get("execute")
        assert callable(on_tool) and callable(execute)
        # stub guard path: call on_tool directly
        await on_tool("lookup", {"a": 1}, "ok result", "tc1")
        await on_tool("lookup", {"a": 1}, "Tool execution failed: bad", "tc2")
        return NS(final_content="final answer", messages=[], tool_used=True)

    async def fake_execute(name, args, **kwargs):
        return "ok"

    monkeypatch.setattr(mod, "run_agent_loop", fake_loop)
    # prefill trace to hit trim branch (>40)
    state = {"tool_trace": [{"tool": "x", "ok": True}] * 45}
    out = await mod._generate(
        MagicMock(),
        MagicMock(),
        NS(id=9, company="", resume_id=None, profile_id=None),
        state,
        "github q?",
        "",
        "en",
    )
    assert out == "final answer"
    assert len(state["tool_trace"]) <= 41
    seen["ok"] = True
    assert seen["ok"]


@pytest.mark.asyncio
async def test_hint_answer_execute_path():
    from types import SimpleNamespace as NS

    import realmock.domains.interview.agents.hint.hint_answer as mod

    async def fake_loop(llm, messages, **kwargs):
        execute = kwargs.get("execute")
        assert callable(execute)
        # hit mod.execute (line 132): guard.run -> execute_interview_tool
        with patch.object(
            mod, "execute_interview_tool", new=AsyncMock(return_value="evidence ok")
        ) as m:
            out = await execute("lookup_profile", {"q": 1})
            assert out == "evidence ok"
            m.assert_awaited_once()
        return NS(final_content="grounded answer", messages=[], tool_used=True)

    with patch.object(mod, "run_agent_loop", new=fake_loop):
        with patch.object(mod, "github_tool_specs", lambda: [object()]):
            with patch.object(mod, "openai_tool", lambda spec: spec):
                out = await mod._generate(
                    MagicMock(),
                    MagicMock(),
                    NS(id=1, company="", resume_id=2, profile_id=3),
                    {},
                    "github Q?",
                    "bg",
                    "zh",
                )
            assert out == "grounded answer"
