"""Round verdict protocol: turn-output parsing, persistence onto the session row."""

from __future__ import annotations

from unittest.mock import MagicMock

from realmock.domains.interview.agents.turn_output import parse_turn_output
from realmock.domains.interview.agents.session_state import InterviewSessionState


def test_verdict_parsed_from_controls():
    output = parse_turn_output(
        {"v": 1, "interview_complete": True, "verdict": "passed"},
        say_text="恭喜你通过了一面",
    )
    assert output.verdict == "passed"
    assert output.interview_complete is True


def test_verdict_rejects_unknown_values():
    output = parse_turn_output({"verdict": "maybe"}, say_text="x")
    assert output.verdict is None

    output = parse_turn_output({"verdict": 3}, say_text="x")
    assert output.verdict is None

    output = parse_turn_output(None, say_text="x", degraded=True)
    assert output.verdict is None


def test_verdict_absent_by_default():
    output = parse_turn_output({"v": 1, "phase_complete": True}, say_text="下一阶段")
    assert output.verdict is None
    assert output.degraded is False


def test_note_verdict_persists_onto_session():
    session = MagicMock()
    agent = InterviewSessionState.__new__(InterviewSessionState)
    agent.session = session

    agent.note_verdict("failed")
    assert session.result == "failed"

    session.result = None
    agent.note_verdict("unsure")
    assert session.result is None

    session.result = None
    agent.note_verdict(None)
    assert session.result is None


def _state_with_agent_state(agent_state: dict) -> InterviewSessionState:
    agent = InterviewSessionState.__new__(InterviewSessionState)
    agent.session = MagicMock()
    agent.agent_state = agent_state
    return agent


def test_note_turn_output_accumulates_score_trajectory():
    agent = _state_with_agent_state({})
    output = parse_turn_output(
        {"turn_score": {"brief": "solid depth", "rating": 4, "weak_points": ["no numbers"]}},
        say_text="ok",
    )
    agent.note_turn_output(output)
    assert agent.agent_state["turn_scores"] == [
        {"brief": "solid depth", "rating": 4, "weak_points": ["no numbers"]}
    ]
    # No turn_score (opening/probe turn): trajectory untouched.
    agent.note_turn_output(parse_turn_output({}, say_text="next"))
    assert len(agent.agent_state["turn_scores"]) == 1


def test_score_trajectory_capped_at_40():
    agent = _state_with_agent_state({})
    for _ in range(45):
        agent.note_turn_output(
            parse_turn_output({"turn_score": {"brief": "b", "rating": 3}}, say_text="x")
        )
    assert len(agent.agent_state["turn_scores"]) == 40


def test_score_section_renders_trajectory():
    agent = _state_with_agent_state({
        "turn_scores": [
            {"brief": "solid depth", "rating": 4, "weak_points": ["no numbers"]},
            {"brief": "", "rating": 2, "weak_points": []},
        ]
    })
    section = agent._score_section()
    assert "1. 4/5 — solid depth (weak: no numbers)" in section
    assert "2. 2/5" in section


def test_score_section_empty_without_scores():
    assert _state_with_agent_state({})._score_section() == ""


def test_summary_phase_entry_carries_trajectory():
    agent = _state_with_agent_state({
        "turn_scores": [{"brief": "depth ok", "rating": 4, "weak_points": []}]
    })
    phase = MagicMock()
    phase.id = "summary"
    phase.name = "Summary"
    phase.description = "Wrap-up"
    phase.min_questions = 1
    phase.max_questions = 1
    message = agent._phase_entry_message(phase)
    assert "score trajectory" in message
    assert "4/5 — depth ok" in message
    assert "Ground your wrap-up evaluation" in message


def test_non_summary_phase_entry_has_no_trajectory():
    agent = _state_with_agent_state({
        "turn_scores": [{"brief": "depth ok", "rating": 4, "weak_points": []}]
    })
    phase = MagicMock()
    phase.id = "basic_knowledge"
    phase.name = "Fundamentals"
    phase.description = "Assess fundamentals"
    phase.min_questions = 2
    phase.max_questions = 4
    message = agent._phase_entry_message(phase)
    assert "score trajectory" not in message


def test_pace_message_fires_once_per_threshold():
    from datetime import datetime, timedelta, timezone

    agent = _state_with_agent_state({})
    agent.session.started_at = datetime.now(timezone.utc) - timedelta(minutes=31)

    first = agent.pace_message()
    assert first is not None and "31 minutes" in first
    assert agent.pace_message() is None  # same mark never repeats
    assert agent.agent_state["pace_marks"] == [30]


def test_pace_message_below_threshold_is_silent():
    from datetime import datetime, timedelta, timezone

    agent = _state_with_agent_state({})
    agent.session.started_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    assert agent.pace_message() is None


def test_pace_message_naive_started_at_treated_as_utc():
    from datetime import datetime, timedelta, timezone

    agent = _state_with_agent_state({})
    agent.session.started_at = (datetime.now(timezone.utc) - timedelta(minutes=50)).replace(tzinfo=None)
    first = agent.pace_message()
    assert first is not None  # 50 min crosses the 30 mark...
    second = agent.pace_message()
    assert second is not None  # ...then the 45 mark (60 not reached yet)
    assert agent.agent_state["pace_marks"] == [30, 45]
