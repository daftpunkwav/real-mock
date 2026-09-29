"""Closing prompts tests for src/realmock/domains/interview/agents/closing_prompts.py.

Covers: CLOSING_BY_PERSONALITY, closing_system_prompt, jump_to_summary_phase
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace


from realmock.domains.interview.agents.closing_prompts import (
    CLOSING_BY_PERSONALITY,
    closing_system_prompt,
    jump_to_summary_phase,
)


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
