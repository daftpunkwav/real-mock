"""HR round-program planning: schema, service wiring, background generation.

Covers: tolerant parsing (unknown kinds dropped, vocabularies repaired),
LLM program preferred while ready, static-chain degradation otherwise,
pass_criteria carried to the response, and ready/failed marking.
"""

from __future__ import annotations

import asyncio
import json

from realmock.domains.interview.constants import MAX_INTERVIEW_ROUNDS, ProcessStatus
from realmock.domains.interview.models import InterviewProcess
from realmock.domains.interview.process.process_service import (
    _planned_step,
    _session_from_process,
    _to_response,
    create_process_with_first_round,
)
from realmock.domains.interview.protocols.round_plan_schema import (
    load_round_plan,
    parse_round_plan,
)
from realmock.domains.interview.schemas.process import ProcessCreateRequest
from tests.fakes import FakeLLMClient


def _round(kind="tech_1", **overrides):
    base = {
        "kind": kind,
        "workflow_type": "technical",
        "personality": "expert",
        "interview_style": "deep_dive",
        "strictness": 5,
        "label": "Tech 1",
        "focus": "baseline",
        "pass_criteria": "answer basics correctly",
    }
    base.update(overrides)
    return base


def _plan_dict(*rounds):
    return {"note": "n", "rounds": list(rounds)}


# ---- schema -----------------------------------------------------------------


def test_parse_round_plan_ok():
    plan = parse_round_plan(
        _plan_dict(_round(), _round("hr_1", workflow_type="hr", personality="hr"))
    )
    assert plan is not None
    assert [r.round_no for r in plan.rounds] == [1, 2]
    assert plan.rounds[1].pass_criteria == "answer basics correctly"


def test_parse_round_plan_repairs_vocabularies():
    plan = parse_round_plan(
        _plan_dict(
            _round("bogus-kind", focus="x"),
            _round("hr_1", workflow_type="nope", personality="nope",
                   interview_style="nope", strictness=99),
        )
    )
    assert plan is not None
    assert len(plan.rounds) == 1  # unknown kind dropped
    only = plan.rounds[0]
    assert only.kind == "hr_1"
    assert only.workflow_type == "hr"
    assert only.personality == "hr"
    assert only.strictness == 10  # clamped, not rejected


def test_parse_round_plan_rejects_garbage():
    assert parse_round_plan(None) is None
    assert parse_round_plan("garbage") is None
    assert parse_round_plan({"rounds": "nope"}) is None
    assert parse_round_plan(_plan_dict()) is None
    assert parse_round_plan(_plan_dict({"kind": "bogus"})) is None


def test_parse_round_plan_caps_and_renumbers():
    plan = parse_round_plan(
        _plan_dict(*[_round(focus=f"f{i}") for i in range(MAX_INTERVIEW_ROUNDS + 3)])
    )
    assert plan is not None
    assert len(plan.rounds) == MAX_INTERVIEW_ROUNDS
    assert [r.round_no for r in plan.rounds] == list(range(1, MAX_INTERVIEW_ROUNDS + 1))


def test_load_round_plan_ready_only():
    process = InterviewProcess(
        role="r", level="l", company="c",
        round_plan=json.dumps(_plan_dict(_round()), ensure_ascii=False),
        round_plan_status="ready",
    )
    assert load_round_plan(process) is not None
    process.round_plan_status = "pending"
    assert load_round_plan(process) is None
    process.round_plan_status = "failed"
    assert load_round_plan(process) is None


# ---- service wiring ----------------------------------------------------------


def _ready_process(db, **overrides):
    process = InterviewProcess(
        role="r",
        level="junior",
        company="c",
        workflow_type="technical",
        max_rounds=4,
        current_round=1,
        status=ProcessStatus.IN_PROGRESS.value,
        round_plan=json.dumps(
            _plan_dict(
                _round("tech_1", personality="expert", strictness=3),
                _round("hr_1", workflow_type="hr", personality="hr",
                       pass_criteria="show motivation"),
            ),
            ensure_ascii=False,
        ),
        round_plan_status="ready",
    )
    for key, value in overrides.items():
        setattr(process, key, value)
    db.add(process)
    db.commit()
    db.refresh(process)
    return process


def test_planned_step_preferred_while_ready(db):
    process = _ready_process(db)
    step = _planned_step(process, 2)
    assert step is not None
    assert step.kind == "hr_1"
    assert step.personality == "hr"


def test_planned_step_none_when_not_ready(db):
    process = _ready_process(db, round_plan_status="pending")
    assert _planned_step(process, 1) is None
    session = _session_from_process(process, 1)
    assert session.workflow_type == "technical"  # static chain fallback
    assert session.personality == "expert"


def test_session_from_process_uses_llm_persona(db):
    process = _ready_process(db)
    second = _session_from_process(process, 2)
    assert second.workflow_type == "hr"
    assert second.personality == "hr"
    # Beyond the LLM program length: static chain covers the budget.
    fourth = _session_from_process(process, 4)
    assert fourth.workflow_type == "hr"


def test_to_response_carries_pass_criteria(db):
    req = ProcessCreateRequest(role="Backend", level="junior", company="acme", max_rounds=4)
    process, session = create_process_with_first_round(db, req)
    process.round_plan = json.dumps(
        _plan_dict(
            _round("tech_1", personality="expert", strictness=3),
            _round("hr_1", workflow_type="hr", personality="hr",
                   pass_criteria="show motivation"),
        ),
        ensure_ascii=False,
    )
    process.round_plan_status = "ready"
    response = _to_response(process, [session])
    assert response.round_plan[1].pass_criteria == "show motivation"


def test_to_response_static_without_pass_criteria(db):
    req = ProcessCreateRequest(role="Backend", level="junior", company="acme", max_rounds=4)
    process, session = create_process_with_first_round(db, req)
    response = _to_response(process, [session])
    assert [p.kind for p in response.round_plan] == ["tech_1", "tech_2", "hr_1", "hr_2"]
    assert all(p.pass_criteria == "" for p in response.round_plan)


def test_create_process_starts_round_plan_pending(db):
    req = ProcessCreateRequest(role="Backend", level="junior", company="acme", max_rounds=3)
    process, _ = create_process_with_first_round(db, req)
    assert process.round_plan_status in ("", "pending")


# ---- background generation ----------------------------------------------------


def _payload(*rounds):
    return {"note": "test", "rounds": list(rounds)}


def test_generate_round_plan_success_marks_ready(db, monkeypatch):
    req = ProcessCreateRequest(role="Backend", level="junior", company="acme", max_rounds=3)
    process, _ = create_process_with_first_round(db, req)

    payload = _payload(
        _round("tech_1"), _round("tech_2"), _round("hr_1", workflow_type="hr"),
    )

    class FakeHRPlanner(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3, max_tokens=None):
            return payload

    from realmock.domains.interview.agents.planning import round_planner as round_planner_mod

    monkeypatch.setattr(round_planner_mod, "session_llm", lambda db, session: FakeHRPlanner())
    asyncio.run(round_planner_mod.generate_round_plan_for_process(process.id))

    db.expire_all()
    refreshed = db.get(InterviewProcess, process.id)
    assert refreshed.round_plan_status == "ready"
    plan = parse_round_plan(refreshed.round_plan)
    assert plan is not None
    assert [r.kind for r in plan.rounds] == ["tech_1", "tech_2", "hr_1"]


def test_generate_round_plan_failure_marks_failed(db, monkeypatch):
    req = ProcessCreateRequest(role="Backend", level="junior", company="acme", max_rounds=3)
    process, _ = create_process_with_first_round(db, req)

    class ExplodingLLM(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3, max_tokens=None):
            raise RuntimeError("hr planner down")

    from realmock.domains.interview.agents.planning import round_planner as round_planner_mod

    monkeypatch.setattr(round_planner_mod, "session_llm", lambda db, session: ExplodingLLM())
    asyncio.run(round_planner_mod.generate_round_plan_for_process(process.id))

    db.expire_all()
    refreshed = db.get(InterviewProcess, process.id)
    assert refreshed.round_plan_status == "failed"
    # Degraded path: static chain still drives round creation.
    assert _planned_step(refreshed, 1) is None


# ---- company research integration --------------------------------------------


def test_generate_round_plan_custom_company_researches(db, monkeypatch):
    req = ProcessCreateRequest(role="Backend", level="junior", company="Acme Robotics", max_rounds=3)
    process, _ = create_process_with_first_round(db, req)

    seen: dict = {}

    async def fake_research(llm, **kwargs):
        seen.update(kwargs)
        return "DIGEST-1"

    class FakeHRPlanner(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3, max_tokens=None):
            return _payload(_round("tech_1"), _round("hr_1", workflow_type="hr"))

    from realmock.domains.interview.agents.planning import round_planner as round_planner_mod

    monkeypatch.setattr(round_planner_mod, "session_llm", lambda db, session: FakeHRPlanner())
    monkeypatch.setattr(round_planner_mod, "research_company_context", fake_research)
    asyncio.run(round_planner_mod.generate_round_plan_for_process(process.id))

    db.expire_all()
    refreshed = db.get(InterviewProcess, process.id)
    assert seen["company"] == "Acme Robotics"
    assert seen["role"] == "Backend"
    assert refreshed.company_research == "DIGEST-1"
    assert refreshed.round_plan_status == "ready"


def test_generate_round_plan_catalog_company_skips_research(db, monkeypatch):
    req = ProcessCreateRequest(role="Backend", level="junior", company="bytedance", max_rounds=3)
    process, _ = create_process_with_first_round(db, req)

    async def fail_research(llm, **kwargs):
        raise AssertionError("research must not run for catalog companies")

    class FakeHRPlanner(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3, max_tokens=None):
            return _payload(_round("tech_1"))

    from realmock.domains.interview.agents.planning import round_planner as round_planner_mod

    monkeypatch.setattr(round_planner_mod, "session_llm", lambda db, session: FakeHRPlanner())
    monkeypatch.setattr(round_planner_mod, "research_company_context", fail_research)
    asyncio.run(round_planner_mod.generate_round_plan_for_process(process.id))

    db.expire_all()
    refreshed = db.get(InterviewProcess, process.id)
    assert refreshed.company_research == ""
    assert refreshed.round_plan_status == "ready"


def test_generate_round_plan_research_failure_still_plans(db, monkeypatch):
    req = ProcessCreateRequest(role="Backend", level="junior", company="Acme Robotics", max_rounds=3)
    process, _ = create_process_with_first_round(db, req)

    async def failed_research(llm, **kwargs):
        return None

    class FakeHRPlanner(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3, max_tokens=None):
            return _payload(_round("tech_1"))

    from realmock.domains.interview.agents.planning import round_planner as round_planner_mod

    monkeypatch.setattr(round_planner_mod, "session_llm", lambda db, session: FakeHRPlanner())
    monkeypatch.setattr(round_planner_mod, "research_company_context", failed_research)
    asyncio.run(round_planner_mod.generate_round_plan_for_process(process.id))

    db.expire_all()
    refreshed = db.get(InterviewProcess, process.id)
    assert refreshed.company_research == ""
    assert refreshed.round_plan_status == "ready"
