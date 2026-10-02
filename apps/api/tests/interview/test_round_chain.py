"""Realistic multi-round interview chains: round kinds, per-round session
overrides, and the round-identity prompt section."""

from __future__ import annotations

from realmock.domains.interview.models import InterviewProcess, InterviewSession
from realmock.domains.interview.process.process_service import (
    _session_from_process,
    create_process_with_first_round,
)
from realmock.domains.interview.protocols.round_chain import round_chain, step_for


def _process(db, **overrides) -> InterviewProcess:
    defaults = dict(
        profile_id=1,
        resume_id=2,
        role="后端工程师",
        level="中级工程师",
        company="bytedance",
        workflow_type="technical",
        personality="professional",
        strictness=3,
        interview_style="deep_dive",
        avatar_id="professional_male",
        scene_id="meeting_room",
        ai_overrides="{}",
        max_rounds=4,
        current_round=1,
        status="in_progress",
        memory="{}",
    )
    defaults.update(overrides)
    p = InterviewProcess(**defaults)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_technical_chain_walks_real_company_loop() -> None:
    """A 4-round technical process plans: tech 1 → tech 2 → HR 1 → HR 2,
    with HR rounds running the hr workflow and softer strictness."""
    steps = round_chain("technical", 4)
    assert [s.kind for s in steps] == ["tech_1", "tech_2", "hr_1", "hr_2"]
    assert [s.workflow_type for s in steps] == ["technical", "technical", "hr", "hr"]
    assert steps[1].strictness > steps[0].strictness, "round 2 raises the bar"
    assert all(s.focus for s in steps)


def test_chain_unknown_workflow_falls_back_and_budget_caps() -> None:
    steps = round_chain("legacy-kind", 2)
    assert len(steps) == 2
    assert steps[0].kind == "tech_1"
    assert step_for("technical", 9, 4) is None


def test_sessions_from_process_follow_the_chain(db) -> None:
    """Each round's session carries its chain step's workflow/personality/
    strictness/style instead of cloning the process defaults."""
    process = _process(db)
    r1 = _session_from_process(process, 1)
    r3 = _session_from_process(process, 3)
    assert r1.workflow_type == "technical" and r1.personality == "expert"
    assert r3.workflow_type == "hr" and r3.personality == "hr"
    assert isinstance(r1, InterviewSession)


def test_create_process_response_exposes_round_plan(db) -> None:
    """The process response carries the full planned chain for the frontend."""
    from realmock.domains.interview.process.process_service import _to_response
    from realmock.domains.interview.schemas.process import (
        ProcessCreateRequest,
        ProcessRoundPlanItem,
    )

    req = ProcessCreateRequest(role="r", level="l", company="bytedance", max_rounds=4)
    process, session = create_process_with_first_round(db, req)
    assert session.round_no == 1
    assert session.workflow_type == "technical"

    response = _to_response(process, [session])
    assert [p.kind for p in response.round_plan] == ["tech_1", "tech_2", "hr_1", "hr_2"]
    assert response.round_plan[2].workflow_type == "hr"
    assert all(isinstance(p, ProcessRoundPlanItem) and p.focus for p in response.round_plan)


def test_final_judgement_only_on_last_round():
    """Mid-chain rounds never claim the final judgement; the budget's last one always does."""
    for base in ("technical", "hr", "management"):
        for budget in (2, 4, 5, 8):
            steps = round_chain(base, budget)
            for step in steps[:-1]:
                assert "final" not in step.focus.lower(), (base, budget, step.round_no)
            assert "final" in steps[-1].focus.lower(), (base, budget)


def test_chain_assigns_per_round_interviewer_avatars() -> None:
    """Each round persona carries its own look: HR rounds are female
    interviewers (whose avatar→voice mapping keeps their voice female),
    pressure rounds the strict expert, expert rounds the senior male."""
    steps = round_chain("technical", 4)
    assert steps[0].avatar_id == "senior_male"  # expert
    assert steps[1].avatar_id == "senior_male"  # expert
    assert steps[2].avatar_id == "hr_female"  # hr
    assert steps[3].avatar_id == "professional_male"  # professional
    # The pressure persona shows up inside the round budget on the
    # management chain (its round 2).
    stress = step_for("management", 2, 5)
    assert stress is not None and stress.avatar_id == "strict_expert"


def test_sessions_from_process_carry_round_avatars(db) -> None:
    """Round sessions take the round persona's avatar — an HR round must not
    inherit the process-level male default (that mismatch is what gave female
    interviewer personas male voices)."""
    process = _process(db)
    r1 = _session_from_process(process, 1)
    r3 = _session_from_process(process, 3)
    assert r1.avatar_id == "senior_male"
    assert r3.avatar_id == "hr_female"


def test_avatar_for_personality_falls_back_to_generic() -> None:
    """Personas outside the map (LLM plans may author "gentle") stay on the
    generic professional look — consistent with the persona prompts, which
    declare no gender for them."""
    from realmock.domains.interview.protocols.round_chain import avatar_for_personality

    assert avatar_for_personality("gentle") == "professional_male"
    assert avatar_for_personality("made_up") == "professional_male"
    assert avatar_for_personality("") == "professional_male"
