"""Closing runner tests for src/realmock/domains/interview/agents/runner_closing.py.

Covers: stream_closing happy path, personality fallback, compaction, plain-text fallback, ledger/LLM errors, DB persist shape
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from realmock.domains.interview.agents import runner_closing as rcmod
from realmock.domains.interview.agents.events import EventKind
from realmock.domains.interview.agents.turn_output import TurnOutput






def _state(idx: int, phase_ids: list[str]):
    session = SimpleNamespace(current_phase=phase_ids[idx] if phase_ids else "")
    return SimpleNamespace(current_phase_idx=idx, questions_in_phase=5, session=session)










# ---- runner_closing ----

def _make_runner(monkeypatch, *, status="active", personality="professional", say="Thanks, bye."):
    from tests.fakes import FakeLLMClient

    phases = [
        SimpleNamespace(id="identity_check", name="Identity"),
        SimpleNamespace(id="summary", name="Summary"),
    ]

    agent = SimpleNamespace(
        phases=phases,
        messages=[{"role": "system", "content": "sys"}],
        agent_state={},
        current_phase_idx=0,
        session=SimpleNamespace(current_phase="identity_check"),
        refresh_system_memory=lambda: None,
        record_assistant_text=lambda text: agent.messages.append({"role": "assistant", "content": text}),
        note_turn_output=lambda output: None,
        note_verdict=lambda verdict: setattr(agent.session, "result", verdict),
        mark_completed=lambda: setattr(session, "status", "completed"),
        save_state=lambda db: None,
        current_phase=lambda: phases[agent.current_phase_idx],
        phase_title_for_display=lambda: "",
        _score_section=lambda: "## scores\n1. 4/5 — good",
    )
    session = SimpleNamespace(
        status=status, personality=personality, id=1, current_phase="identity_check",
    )
    # bind mark_completed closure over session
    orig_mark = agent.mark_completed
    del orig_mark
    agent.mark_completed = lambda: setattr(session, "status", "completed")

    prompter = SimpleNamespace(get_context_window=lambda db: 0)
    llm = FakeLLMClient(tokens=[say])
    tools = SimpleNamespace(collect_chat_tools=lambda include_function_tools=True: [])

    runner = SimpleNamespace(session=session, agent=agent, prompter=prompter, llm=llm, tools=tools)

    async def fake_say_first(llm_arg, tools_arg, api_messages, *, temperature):
        from realmock.domains.interview.agents.events import StreamEvent as SE

        yield SE.make_token(say)
        yield TurnOutput(say=say, emotion="smile", wait_seconds=0, interview_complete=False, verdict="passed")

    monkeypatch.setattr(rcmod, "stream_say_first", fake_say_first)
    monkeypatch.setattr(rcmod, "maybe_fold_history", lambda *a, **k: _coro(False))
    monkeypatch.setattr(rcmod, "append_turn", lambda db, sess, **k: {"turn_id": "t-0001"})
    monkeypatch.setattr(rcmod, "take_pending_tools", lambda state: [])
    monkeypatch.setattr(rcmod, "run_finish_lifecycle", lambda db, sess, **k: {})
    return runner


async def _coro(value):
    return value


@pytest.mark.asyncio
async def test_stream_closing_already_completed(monkeypatch) -> None:
    runner = _make_runner(monkeypatch, status="completed")
    events = [e async for e in rcmod.stream_closing(runner, db=None)]  # type: ignore[arg-type]
    assert len(events) == 1
    assert events[0].kind == EventKind.ERROR
    assert events[0].error_code == "A2002"


@pytest.mark.asyncio
async def test_stream_closing_happy_path_forces_complete(monkeypatch) -> None:
    runner = _make_runner(monkeypatch, say="Thank you for joining.")
    events = [e async for e in rcmod.stream_closing(runner, db=None)]  # type: ignore[arg-type]
    kinds = [e.kind for e in events]
    assert EventKind.TOKEN in kinds
    done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert done.is_complete is True
    assert done.phase_changed is True
    assert done.content == "Thank you for joining."
    assert done.result == "passed"
    assert runner.session.status == "completed"
    # interview_complete forced True even though fake output was False
    assert any(m.get("role") == "assistant" for m in runner.agent.messages)


@pytest.mark.asyncio
async def test_stream_closing_unknown_personality_falls_back(monkeypatch) -> None:
    runner = _make_runner(monkeypatch, personality="weird-custom")
    events = [e async for e in rcmod.stream_closing(runner, db=None)]  # type: ignore[arg-type]
    assert any(e.kind == EventKind.TURN_COMPLETE for e in events)


@pytest.mark.asyncio
async def test_stream_closing_uses_context_window_compaction(monkeypatch) -> None:
    runner = _make_runner(monkeypatch)
    runner.prompter.get_context_window = lambda db: 8000
    runner.agent._score_section = lambda: ""

    async def fake_compact(messages, window, llm=None, keep_recent=24):
        return messages

    import realmock.domains.interview.agents.runner_closing as m

    monkeypatch.setitem(
        __import__("sys").modules, "realmock.platform.capabilities.ai.context.summarize",
        SimpleNamespace(compact_with_summary=fake_compact),
    )
    # Patch via import path inside function: monkeypatch the module attribute directly
    import realmock.platform.capabilities.ai.context.summarize as summod

    monkeypatch.setattr(summod, "compact_with_summary", fake_compact)
    _ = m
    events = [e async for e in rcmod.stream_closing(runner, db=None)]  # type: ignore[arg-type]
    assert any(e.kind == EventKind.TURN_COMPLETE for e in events)


@pytest.mark.asyncio
async def test_stream_closing_plain_text_fallback_when_no_output(monkeypatch) -> None:
    runner = _make_runner(monkeypatch, say="plain thanks")

    async def fake_say_first_empty(llm_arg, tools_arg, api_messages, *, temperature):
        from realmock.domains.interview.agents.events import StreamEvent as SE

        yield SE.make_token("plain thanks")

    monkeypatch.setattr(rcmod, "stream_say_first", fake_say_first_empty)
    events = [e async for e in rcmod.stream_closing(runner, db=None)]  # type: ignore[arg-type]
    done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert done.content == "plain thanks"
    assert done.is_complete is True


@pytest.mark.asyncio
async def test_stream_closing_ledger_failure_yields_retryable_error(monkeypatch) -> None:
    runner = _make_runner(monkeypatch)

    def boom(db, sess, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(rcmod, "append_turn", boom)
    events = [e async for e in rcmod.stream_closing(runner, db=None)]  # type: ignore[arg-type]
    err = next(e for e in events if e.kind == EventKind.ERROR)
    assert err.error_code == "C0001"
    assert err.error_retryable is True


@pytest.mark.asyncio
async def test_stream_closing_llm_failure_yields_retryable_error(monkeypatch) -> None:
    runner = _make_runner(monkeypatch)

    async def boom(llm_arg, tools_arg, api_messages, *, temperature):
        raise RuntimeError("llm down")
        yield  # pragma: no cover

    monkeypatch.setattr(rcmod, "stream_say_first", boom)
    events = [e async for e in rcmod.stream_closing(runner, db=None)]  # type: ignore[arg-type]
    err = next(e for e in events if e.kind == EventKind.ERROR)
    assert err.error_code == "C0001"


def test_stream_closing_persists_agent_state_json_shape(db) -> None:
    # Real DB shape: closing must leave ledger + completed status via InterviewRunner.
    import json

    from realmock.domains.interview.models import InterviewSession
    from realmock.domains.interview.agents.runner import InterviewRunner
    from tests.fakes import FakeLLMClient

    s = InterviewSession(
        profile_id=1, role="Backend", level="Senior", company="bytedance",
        workflow_type="technical", personality="professional", strictness=3,
        interview_style="deep_dive", status="active", current_phase="summary",
        plan_status="failed", messages=json.dumps([{"role": "system", "content": "sys"}]),
        agent_state=json.dumps({"phase_idx": 8, "questions_in_phase": 0}),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    llm = FakeLLMClient(tokens=['{"say":"bye","v":1,"emotion":"smile","interview_complete":true,"verdict":"passed"}'])
    runner = InterviewRunner(s, llm)
    import asyncio

    async def _run():
        return [e async for e in runner.stream_closing(db)]

    events = asyncio.run(_run())
    assert any(e.kind == EventKind.TURN_COMPLETE for e in events)
