"""Closing prompts tests for src/realmock/domains/interview/agents/closing_prompts.py.

Covers: CLOSING_BY_PERSONALITY, closing_system_prompt, jump_to_summary_phase
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace


from realmock.domains.interview.agents import runner_closing as rcmod
from realmock.domains.interview.agents.closing_prompts import (
    CLOSING_BY_PERSONALITY,
    closing_system_prompt,
    jump_to_summary_phase,
)
from realmock.domains.interview.agents.turn_output import TurnOutput


def test_closing_by_personality_covers_all() -> None:
    for key in ("gentle", "professional", "pressure", "hr", "expert"):
        assert key in CLOSING_BY_PERSONALITY
        assert isinstance(CLOSING_BY_PERSONALITY[key], str)


def test_closing_system_prompt_contains_requirements() -> None:
    out = closing_system_prompt("Professional and restrained; thank them.")
    assert "End interview" in out
    assert "Professional and restrained" in out
    assert "interview_complete" in out
    assert "verdict" in out


def _state(idx: int, phase_ids: list[str]):
    session = SimpleNamespace(current_phase=phase_ids[idx] if phase_ids else "")
    return SimpleNamespace(current_phase_idx=idx, questions_in_phase=5, session=session)


def test_jump_to_summary_static_flow() -> None:
    ids = ["identity_check", "self_intro", "summary"]
    st = _state(0, ids)
    assert jump_to_summary_phase(st, ids) is True
    assert st.current_phase_idx == 2
    assert st.questions_in_phase == 0
    assert st.session.current_phase == "summary"


def test_jump_to_summary_agent_planned_last_step() -> None:
    ids = ["s01", "s02", "s03"]
    st = _state(0, ids)
    assert jump_to_summary_phase(st, ids) is True
    assert st.current_phase_idx == 2


def test_jump_to_summary_already_there_no_jump() -> None:
    ids = ["identity_check", "summary"]
    st = _state(1, ids)
    assert jump_to_summary_phase(st, ids) is False
    assert st.current_phase_idx == 1


def test_jump_to_summary_empty_ids_stays_zero() -> None:
    st = _state(0, [])
    # len([])-1 = -1 -> max(0,-1)=0, no advance
    assert jump_to_summary_phase(st, []) is False


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
















