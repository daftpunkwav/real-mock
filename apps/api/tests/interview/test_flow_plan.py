"""Agent-planned interview flow: plan schema, plan_ops, past-record tools, planner."""

from __future__ import annotations

import json

from realmock.domains.interview.models import InterviewProcess, InterviewSession
from realmock.domains.interview.services.interview.past_records import (
    prior_round_sessions,
    read_past_round,
    search_past_interviews,
)
from realmock.domains.interview.services.interview.session_state import InterviewSessionState
from realmock.domains.interview.services.interview.turn_output import parse_turn_output
from realmock.domains.interview.services.planning.plan_schema import (
    MAX_PLAN_STEPS,
    MIN_PLAN_STEPS,
    parse_plan,
    plan_from_workflow,
)
from realmock.domains.interview.services.planning.planner import (
    PLAN_STATUS_READY,
    ensure_plan,
    fallback_plan_for,
)
from realmock.domains.interview.services.interview.workflows import get_workflow
from tests.fakes import FakeLLMClient


# ---- plan schema ---------------------------------------------------------------


def _agent_plan_dict(steps: int = 10) -> dict:
    return {
        "round_note": "一面:基础与项目初探",
        "source": "agent",
        "steps": [
            {"title": f"步骤{i}", "focus": f"考察点{i}", "max_questions": 3}
            for i in range(1, steps + 1)
        ],
    }


def test_parse_plan_clamps_and_ids():
    plan = parse_plan(_agent_plan_dict(12))
    assert plan is not None
    assert len(plan.steps) == 12
    assert plan.steps[0].id == "s01"
    assert plan.source == "agent"
    # question bounds clamp into 1..8
    raw = _agent_plan_dict(9)
    raw["steps"][0]["max_questions"] = 99
    plan = parse_plan(raw)
    assert plan is not None
    assert plan.steps[0].max_questions == 8


def test_parse_plan_rejects_too_few_steps():
    assert parse_plan(_agent_plan_dict(MIN_PLAN_STEPS - 1)) is None
    assert parse_plan("garbage") is None
    assert parse_plan(None) is None
    assert parse_plan({"steps": "nope"}) is None


def test_parse_plan_caps_total_steps():
    plan = parse_plan(_agent_plan_dict(50))
    assert plan is not None
    assert len(plan.steps) == MAX_PLAN_STEPS


def test_plan_from_workflow_preserves_static_ids():
    plan = plan_from_workflow(get_workflow("technical"))
    assert plan.source == "fallback"
    assert plan.steps[0].id == "identity_check"
    # round-trip through parse_plan keeps static ids
    restored = parse_plan(plan.to_dict())
    assert restored is not None
    assert restored.steps[0].id == "identity_check"


# ---- plan_ops (turn protocol + state machine) ----------------------------------


def test_plan_ops_parsed_and_sanitized():
    output = parse_turn_output(
        {
            "plan_ops": {
                "insert_after_current": [
                    {"title": "库存项目深挖", "focus": "压测数据真实性", "max_questions": 4},
                    {"title": "", "focus": "ignored"},  # dropped: no title
                    "garbage",
                ]
            }
        },
        say_text="好",
    )
    assert len(output.plan_ops) == 1
    assert output.plan_ops[0]["title"] == "库存项目深挖"
    assert output.plan_ops[0]["max_questions"] == 4

    assert parse_turn_output({"plan_ops": None}, say_text="x").plan_ops == ()
    assert parse_turn_output({"plan_ops": {"insert_after_current": []}}, say_text="x").plan_ops == ()


def test_apply_plan_ops_inserts_after_current():
    session = InterviewSession(
        role="r", level="l", company="c",
        plan=json.dumps(_agent_plan_dict(10), ensure_ascii=False),
        plan_status="ready",
    )
    agent = InterviewSessionState.__new__(InterviewSessionState)
    agent.session = session
    agent.plan = parse_plan(session.plan)
    agent.phases = agent.plan.steps
    agent.current_phase_idx = 2
    agent.questions_in_phase = 0

    inserted = agent.apply_plan_ops(
        ({"title": "新项目追问", "focus": "f", "max_questions": 2},)
    )
    assert inserted == 1
    assert agent.plan.steps[3].title == "新项目追问"
    # current step unchanged; next step is the insertion
    assert agent.current_phase_idx == 2
    assert agent.phases[3] is agent.plan.steps[3]

    # no-op without a plan
    agent.plan = None
    assert agent.apply_plan_ops(({"title": "x", "focus": "y"},)) == 0


def test_apply_plan_ops_respects_total_cap():
    session = InterviewSession(
        role="r", level="l", company="c",
        plan=json.dumps(_agent_plan_dict(MAX_PLAN_STEPS), ensure_ascii=False),
        plan_status="ready",
    )
    agent = InterviewSessionState.__new__(InterviewSessionState)
    agent.session = session
    agent.plan = parse_plan(session.plan)
    agent.phases = agent.plan.steps
    agent.current_phase_idx = 0
    assert agent.apply_plan_ops(({"title": "再插一步", "focus": "f"},)) == 0


# ---- past-record tools ---------------------------------------------------------


def _make_process_with_rounds(db):
    process = InterviewProcess(role="r", level="l", company="c", max_rounds=3, current_round=2)
    db.add(process)
    db.flush()
    ledger = json.dumps({
        "schema": "realmock.ledger.v1",
        "frozen": True,
        "turns": [
            {"turn_id": "t1", "phase": "project_deep_dive",
             "assistant": {"text": "讲讲库存系统的 QPS"}, "user": {"text": "大概 5000"}},
            {"turn_id": "t2", "phase": "summary",
             "assistant": {"text": "总结一下"}, "user": {"text": "好的"}},
        ],
    }, ensure_ascii=False)
    first = InterviewSession(
        role="r", level="l", company="c", status="completed",
        process_id=process.id, round_no=1, result="passed", ledger=ledger,
    )
    db.add(first)
    db.commit()
    return process, first


def test_prior_rounds_scoped_to_process_and_completed(db):
    process, first = _make_process_with_rounds(db)
    current = InterviewSession(
        role="r", level="l", company="c", status="active",
        process_id=process.id, round_no=2,
    )
    standalone = InterviewSession(role="r", level="l", company="c", status="completed")
    db.add_all([current, standalone])
    db.commit()

    assert prior_round_sessions(db, current) == [first]
    assert prior_round_sessions(db, standalone) == []
    assert prior_round_sessions(db, first) == []


def test_search_and_read_past_rounds(db):
    process, first = _make_process_with_rounds(db)
    current = InterviewSession(
        role="r", level="l", company="c", status="active",
        process_id=process.id, round_no=2,
    )
    db.add(current)
    db.commit()

    hits = json.loads(search_past_interviews(db, current, "库存 QPS"))
    assert hits["matches"][0]["turn_id"] == "t1"
    assert "5000" in hits["matches"][0]["answer"]

    empty = json.loads(search_past_interviews(db, current, ""))
    assert empty == {"error": "empty_query"}

    page = json.loads(read_past_round(db, current, 1, 0))
    assert page["total_turns"] == 2
    assert page["next_offset"] is None
    assert page["turns"][0]["question"] == "讲讲库存系统的 QPS"

    missing = json.loads(read_past_round(db, current, 9))
    assert missing["error"] == "round_not_found"


# ---- planner orchestration -----------------------------------------------------


def test_ensure_plan_stores_fallback_when_failed(db):
    session = InterviewSession(
        role="r", level="l", company="c", plan_status="failed"
    )
    db.add(session)
    db.commit()

    import asyncio

    plan = asyncio.run(ensure_plan(db, session))
    assert plan is not None
    assert plan.source == "fallback"
    assert session.plan_status == PLAN_STATUS_READY
    assert session.plan and json.loads(session.plan)["steps"][0]["id"] == "identity_check"


def test_generate_plan_success_marks_ready(db, monkeypatch):
    session = InterviewSession(role="r", level="l", company="c")
    db.add(session)
    db.commit()

    plan_payload = _agent_plan_dict(9)

    class FakePlannerLLM(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3, max_tokens=None):
            return plan_payload

    from realmock.domains.interview.services.planning import planner as planner_mod

    monkeypatch.setattr(planner_mod, "session_llm", lambda db, session: FakePlannerLLM())
    import asyncio

    asyncio.run(planner_mod.generate_plan_for_session(session.id))

    db.expire_all()
    refreshed = db.get(InterviewSession, session.id)
    assert refreshed.plan_status == "ready"
    assert len(parse_plan(refreshed.plan).steps) == 9


def test_generate_plan_failure_marks_failed(db, monkeypatch):
    session = InterviewSession(role="r", level="l", company="c")
    db.add(session)
    db.commit()

    class ExplodingLLM(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3, max_tokens=None):
            raise RuntimeError("planner down")

    from realmock.domains.interview.services.planning import planner as planner_mod

    monkeypatch.setattr(planner_mod, "session_llm", lambda db, session: ExplodingLLM())
    import asyncio

    asyncio.run(planner_mod.generate_plan_for_session(session.id))

    db.expire_all()
    refreshed = db.get(InterviewSession, session.id)
    assert refreshed.plan_status == "failed"
    # degraded path still yields a usable (static) plan
    assert fallback_plan_for(refreshed) is not None
