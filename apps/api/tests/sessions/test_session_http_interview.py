"""Session fix: HTTP interview start/message uses InterviewRunner, with no agent.start/respond."""

from __future__ import annotations

import inspect

from realmock.domains.interview.routes import turns as interview_api
from realmock.domains.interview.services.interview import session_state as agent_mod


def test_interview_agent_has_no_start_or_respond() -> None:
    assert not hasattr(agent_mod.InterviewSessionState, "start")
    assert not hasattr(agent_mod.InterviewSessionState, "respond")
    assert not hasattr(agent_mod.InterviewSessionState, "get_phases_remaining")
    assert hasattr(agent_mod.InterviewSessionState, "phases_remaining")


def test_start_interview_source_uses_runner() -> None:
    src = inspect.getsource(interview_api.start_interview)
    assert "InterviewRunner" in src or "runner" in src
    assert "agent.start" not in src


def test_send_message_source_uses_runner() -> None:
    src = inspect.getsource(interview_api.send_message)
    assert "stream_turn" in src or "InterviewRunner" in src
    assert "agent.respond" not in src
    # The method must be called; do not use list(bound_method)
    assert "phases_remaining()" in src


def test_phases_remaining_is_callable_list() -> None:
    """Prevent phases_remaining from being treated as a property again and causing TypeError."""
    from unittest.mock import MagicMock

    from realmock.domains.interview.services.interview.session_state import InterviewSessionState

    session = MagicMock()
    session.role = "Backend"
    session.level = "intermediate"
    session.company = "x"
    session.workflow_type = "technical"
    session.personality = "professional"
    session.strictness = "medium"
    session.interview_style = "standard"
    session.resume_id = None
    session.messages = "[]"
    session.agent_state = "{}"
    session.current_phase = "identity_check"
    session.questions_in_phase = 0
    session.asked_questions = "[]"
    llm = MagicMock()
    agent = InterviewSessionState(session, llm)
    names = agent.phases_remaining()
    assert isinstance(names, list)
    assert all(isinstance(n, str) for n in names)
    # list() is available after the correct call
    assert list(agent.phases_remaining()) == names
