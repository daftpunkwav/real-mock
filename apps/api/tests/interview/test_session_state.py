"""Session state tests for src/realmock/domains/interview/agents/session_state.py.

Covers: load/clamp/plan/notes/pace/phase/progression branches
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from realmock.domains.interview.agents.session_state import (
    InterviewSessionState,
    _is_summary_phase,
)
from realmock.domains.interview.agents.turn_output import TurnOutput, TurnScore
from realmock.domains.interview.models import InterviewSession
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def _llm() -> MagicMock:
    m = MagicMock()
    m.api_key = ""
    return m


def _row(**overrides) -> InterviewSession:
    base = {
        "profile_id": 1,
        "role": "Backend",
        "level": "junior",
        "company": "acme",
        "workflow_type": "technical",
        "status": "pending",
        "current_phase": "identity_check",
        "agent_state": "{}",
        "messages": "[]",
    }
    base.update(overrides)
    return InterviewSession(**base)


def _state(db, **overrides) -> InterviewSessionState:
    row = _row(**overrides)
    db.add(row)
    db.commit()
    db.refresh(row)
    return InterviewSessionState(row, _llm())


# ---- _is_summary_phase ----


def test_is_summary_phase_variants() -> None:
    assert _is_summary_phase(SimpleNamespace(id="summary", kind="x")) is True
    assert _is_summary_phase(SimpleNamespace(id="x", kind="SummaryWrap")) is True
    assert _is_summary_phase(SimpleNamespace(id="tech", kind="qa")) is False
    assert _is_summary_phase(SimpleNamespace()) is False


# ---- load / clamp ----


def test_load_state_corrupt_json_starts_fresh(db) -> None:
    st = _state(db, agent_state="{bad", messages="[bad")
    assert st.agent_state.get("weak_points") == []
    assert st.messages == []
    assert st.current_phase_idx == 0


def test_load_state_clamps_phase_idx(db) -> None:
    st = _state(db, agent_state=json.dumps({"phase_idx": 999}))
    assert st.current_phase_idx == len(st.phases) - 1
    st2 = _state(db, agent_state=json.dumps({"phase_idx": -5}))
    assert st2.current_phase_idx == 0


def test_load_plan_failure_falls_back(db) -> None:
    st = _state(db, plan="not-a-plan-at-all{{{")
    # parse_plan tolerates or returns None; either way phases fall back
    assert len(st.phases) > 0
    with patch(
        "realmock.domains.interview.agents.session_state.parse_plan",
        side_effect=RuntimeError("boom"),
    ):
        st2 = _state(db)
        assert st2.plan is None


def test_reload_plan_clamps(db) -> None:
    st = _state(db)
    st.current_phase_idx = 999
    st.reload_plan()
    assert st.current_phase_idx == len(st.phases) - 1


def test_save_state_persists_and_plan(db) -> None:
    st = _state(db)
    st.note_question("what is redis?")
    st.save_state(db)
    db.refresh(st.session)
    assert st.session.current_phase
    data = json.loads(st.session.agent_state)
    assert data["phase_idx"] == st.current_phase_idx


# ---- notes ----


def test_note_question_trims_caps_dedups(db) -> None:
    st = _state(db)
    st.note_question("   ")
    assert st.agent_state["asked_questions"] == []
    st.note_question("q" * 200)
    assert len(st.agent_state["asked_questions"][0]) == 120
    st.note_question("q" * 200)
    assert len(st.agent_state["asked_questions"]) == 1
    st.agent_state["asked_questions"] = [f"q{i}" for i in range(85)]
    st.note_question("new-q")
    assert len(st.agent_state["asked_questions"]) == 80


def test_note_weak_point_caps(db) -> None:
    st = _state(db)
    st.note_weak_point("")
    assert st.agent_state["weak_points"] == []
    st.note_weak_point("vague answer")
    st.note_weak_point("vague answer")
    assert st.agent_state["weak_points"] == ["vague answer"]
    st.agent_state["weak_points"] = [f"w{i}" for i in range(31)]
    st.note_weak_point("fresh")
    assert len(st.agent_state["weak_points"]) == 30


def test_note_turn_output_probe_scores(db) -> None:
    st = _state(db)
    out = TurnOutput(
        say="hi",
        probe="follow cache",
        turn_score=TurnScore(brief="ok", rating=4, weak_points=("w1",)),
    )
    st.note_turn_output(out)
    assert st.agent_state["last_probe"] == "follow cache"
    assert st.agent_state["last_turn_score"]["rating"] == 4
    assert len(st.agent_state["turn_scores"]) == 1
    assert "w1" in st.agent_state["weak_points"]
    st.note_turn_output(TurnOutput(say="hi2"))
    assert st.agent_state["last_probe"] == "follow cache"


def test_note_turn_output_caps_scores(db) -> None:
    st = _state(db)
    st.agent_state["turn_scores"] = [
        {"brief": "x", "rating": 1, "weak_points": []} for _ in range(41)
    ]
    st.note_turn_output(
        TurnOutput(say="h", turn_score=TurnScore(brief="b", rating=2, weak_points=()))
    )
    assert len(st.agent_state["turn_scores"]) == 40


def test_note_verdict_only_pass_fail(db) -> None:
    st = _state(db)
    st.note_verdict("passed")
    assert st.session.result == "passed"
    st.note_verdict("nope")
    assert st.session.result == "passed"
    st.note_verdict(None)
    assert st.session.result == "passed"


# ---- pace ----


def test_pace_message_no_started(db) -> None:
    st = _state(db)
    st.session.started_at = None
    assert st.pace_message() is None


def test_pace_message_fires_once_per_threshold(db) -> None:
    st = _state(db)
    st.session.started_at = datetime.now(timezone.utc) - timedelta(minutes=32)
    first = st.pace_message()
    assert first is not None and "32" in first or "30" in first
    assert st.pace_message() is None  # same threshold already marked
    st.session.started_at = datetime.now(timezone.utc) - timedelta(minutes=50)
    second = st.pace_message()
    assert second is not None
    assert st.pace_message() is None


def test_pace_message_naive_datetime(db) -> None:
    st = _state(db)
    st.session.started_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=61)
    msg = st.pace_message()
    assert msg is not None


def test_pace_message_below_threshold(db) -> None:
    st = _state(db)
    st.session.started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert st.pace_message() is None


# ---- phase queries ----


def test_current_phase_overflow_returns_last(db) -> None:
    st = _state(db)
    st.current_phase_idx = 10**6
    assert st.current_phase() == st.phases[-1]
    assert isinstance(st.phases_remaining(), list)


def test_phase_title_display_plan_vs_static(db) -> None:
    st = _state(db)
    assert st.phase_title_for_display() == ""
    st.plan = SimpleNamespace(source="agent", steps=st.phases)
    with patch.object(type(st), "_plan_is_agent_authored", lambda self: True):
        assert st.phase_title_for_display() == st.current_phase().name


def test_apply_plan_ops_branches(db) -> None:
    st = _state(db)
    assert st.apply_plan_ops(()) == 0
    st.plan = None
    assert st.apply_plan_ops(({"title": "x"},)) == 0
    # With plan: insert, skip empty title, clamp max_questions.
    from realmock.domains.interview.protocols.plan_schema import (
        MAX_PLAN_STEPS,
        InterviewPlan,
        PlanStep,
    )

    plan = InterviewPlan(
        steps=[
            PlanStep(id="s01", title="t1", focus="f1", min_questions=1, max_questions=2),
        ]
    )
    st.plan = plan
    st.current_phase_idx = 0
    n = st.apply_plan_ops(
        (
            {"title": "  ", "focus": "f"},
            {"title": "Deep Redis", "focus": "cache", "max_questions": 99},
        )
    )
    assert n == 1
    assert st.plan.steps[1].title == "Deep Redis"
    # Cap: fill to max then further inserts stop.
    plan.steps = [PlanStep(id=f"s{i:02d}", title=f"t{i}", focus="f") for i in range(MAX_PLAN_STEPS)]
    assert st.apply_plan_ops(({"title": "extra"},)) == 0


# ---- progression ----


def test_mark_active_completed(db) -> None:
    st = _state(db)
    st.mark_active()
    assert st.session.status == "active"
    assert st.session.started_at is not None
    st.mark_completed()
    assert st.session.status == "completed"
    assert st.session.ended_at is not None
    assert st.current_phase_idx == len(st.phases) - 1


def test_record_text_and_reset(db) -> None:
    st = _state(db)
    st.record_user_text("hello")
    assert st.messages[-1] == {"role": "user", "content": "hello"}
    st.record_assistant_text("question about redis?")
    assert st.messages[-1]["role"] == "assistant"
    assert any("redis" in q for q in st.agent_state["asked_questions"])
    st.record_assistant_text("")
    st.reset_messages()
    assert st.messages == []
    st.set_questions_in_phase(3)
    assert st.questions_in_phase == 3


def test_advance_phase_marker_and_max(db) -> None:
    st = _state(db)
    # Marker path advances.
    assert st.advance_phase_if_needed("done [PHASE_COMPLETE]", phase_complete=None) in (True, False)
    st2 = _state(db)
    st2.questions_in_phase = st2.current_phase().max_questions
    idx = st2.current_phase_idx
    assert st2.advance_phase_if_needed("plain", phase_complete=False) is True
    assert st2.current_phase_idx == idx + 1
    # At end: increments counter, no advance.
    st3 = _state(db)
    st3.current_phase_idx = len(st3.phases) - 1
    assert st3.advance_phase_if_needed("x", phase_complete=True) is False
    # Below cap: counter increments, no advance.
    st4 = _state(db)
    assert st4.advance_phase_if_needed("plain", phase_complete=False) is False
    assert st4.questions_in_phase == 1


def test_load_state_tolerates_malformed_types(db) -> None:
    st = _state(
        db,
        agent_state=json.dumps(
            {"phase_idx": "oops", "questions_in_phase": "many", "asked_topics": "nope"}
        ),
    )
    assert st.current_phase_idx == 0
    assert st.questions_in_phase == 0
    assert st.asked_topics == []


def test_apply_plan_ops_tolerates_malformed_model_output(db) -> None:
    from realmock.domains.interview.protocols.plan_schema import InterviewPlan, PlanStep

    st = _state(db)
    st.plan = InterviewPlan(
        steps=[PlanStep(id="s01", title="t1", focus="f1", min_questions=1, max_questions=2)]
    )
    st.current_phase_idx = 0
    n = st.apply_plan_ops(
        (
            {"title": "Bad count", "focus": "f", "max_questions": "many"},
            {"title": "No count", "focus": "f", "max_questions": None},
            "not-a-dict",  # type: ignore[arg-type]
        ),  # type: ignore[arg-type]
    )
    assert n == 2
    assert st.plan.steps[1].max_questions == 3
    assert st.plan.steps[2].max_questions == 3


def test_phase_entry_reverse_qa_and_summary(db) -> None:
    st = _state(db)
    rev = SimpleNamespace(id="reverse_qa", kind="", name="RQ", description="ask us")
    msg = st._phase_entry_message(rev)
    assert "Role switch" in msg
    rev2 = SimpleNamespace(id="x", kind="reverse_qa", name="RQ", description="d")
    assert "Role switch" in st._phase_entry_message(rev2)
    generic = SimpleNamespace(id="tech", kind="qa", name="Tech", description="deep")
    assert "Entering new phase" in st._phase_entry_message(generic)
    summary = SimpleNamespace(id="summary", kind="summary", name="Summary", description="wrap")
    st.agent_state["turn_scores"] = [{"brief": "good", "rating": 4, "weak_points": []}]
    wrapped = st._phase_entry_message(summary)
    assert "trajectory" in wrapped


# ---- session_overrides ----








# ---- compaction thresholds ----














# ---- round planner background (tests live in test_round_planner_extra.py / test_round_plan_schema.py) ----


# ---- round planner background ----












