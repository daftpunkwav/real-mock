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
