# -*- coding: utf-8 -*-
"""WS turn-state persistence regression (N2).

runner/agent is constructed from the main-loop db session object; only after the turn path creates its own db and rebinds
can save_state actually write to the database. This file locks in that behavior through the real ORM path:
- Turn state is persisted after rebind;
- The interruption count uses the agent's in-memory state as the single source of truth, and turn save_state does not revert it.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from realmock.platform.core.constants import SessionStatus
from realmock.platform.database import ApiBase, SessionsBase
import realmock.domains.prep.models  # noqa: F401
import realmock.domains.interview.models  # noqa: F401
import realmock.platform.models  # noqa: F401

from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.services.interview.runner import InterviewRunner
from realmock.domains.interview.services.interview.session_state import InterviewSessionState


@pytest.fixture
def ws_db():
    engine = create_engine("sqlite:///:memory:")
    ApiBase.metadata.create_all(engine)
    SessionsBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db, factory
    db.close()
    engine.dispose()


def _mk_session(db) -> InterviewSession:
    s = InterviewSession(
        profile_id=1, role="Backend", level="intermediate", company="bytedance",
        workflow_type="technical", personality="professional", strictness=3,
        interview_style="deep_dive", status=SessionStatus.ACTIVE.value,
        current_phase="basic_knowledge", messages="[]", agent_state="{}",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


class _FakeLLM:
    api_key = "sk-t"


def _mk_runner(session, llm):
    agent = InterviewSessionState(session, llm)
    runner = InterviewRunner(session, llm, agent, rag=None)
    return runner, agent


def test_round_save_state_persists_after_rebind(ws_db) -> None:
    """After rebind, the turn's save_state actually writes to the database (N2 regression: detached objects are not persisted)."""
    main_db, factory = ws_db
    s = _mk_session(main_db)

    # Simulate bind_pipeline: runner/agent holds objects from the main-loop db.
    runner, agent = _mk_runner(s, _FakeLLM())

    # Turn path: use a self-created db2 to reload the session with the same primary key and rebind it
    round_db = factory()
    session2 = round_db.query(InterviewSession).filter(InterviewSession.id == s.id).first()
    assert session2 is not s
    runner.session = session2
    runner.agent.session = session2
    runner.prompter.session = session2
    runner.tools.session = session2

    agent.record_user_text("My answer content ABC")
    agent.record_assistant_text("Interviewer follow-up XYZ")
    agent.save_state(round_db)

    # The third connection reads the database: the state must already be persisted
    check_db = factory()
    row = check_db.query(InterviewSession).filter(InterviewSession.id == s.id).first()
    msgs = json.loads(row.messages or "[]")
    assert [m["content"] for m in msgs] == ["My answer content ABC", "Interviewer follow-up XYZ"]
    assert row.current_phase == agent.session.current_phase


def test_interrupt_stats_survive_round_save_state(ws_db) -> None:
    """The interruption count uses the agent's in-memory state as the single source of truth; after rebind, the turn's save_state does not revert to the old value."""
    main_db, factory = ws_db
    s = _mk_session(main_db)
    runner, agent = _mk_runner(s, _FakeLLM())

    # Interruption path: incorporate the count into the agent's in-memory state (the source after making interrupt the single source of truth).
    agent.agent_state["candidate_interrupts"] = 2
    agent.agent_state["ai_interrupts"] = 1

    # Turn path: persist after rebinding a self-created db
    round_db = factory()
    session2 = round_db.query(InterviewSession).filter(InterviewSession.id == s.id).first()
    runner.session = session2
    runner.agent.session = session2
    runner.prompter.session = session2
    runner.tools.session = session2

    agent.record_user_text("Continue answering")
    agent.save_state(round_db)

    check_db = factory()
    row = check_db.query(InterviewSession).filter(InterviewSession.id == s.id).first()
    state = json.loads(row.agent_state or "{}")
    assert state["candidate_interrupts"] == 2
    assert state["ai_interrupts"] == 1
    assert "phase_idx" in state, "Turn state should be persisted together"
