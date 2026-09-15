"""Round plan schema tests for src/realmock/domains/interview/process/round_plan_schema.py.

Covers: PlannedRound projections, parse_round_plan coerce/derive, load exception
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from realmock.domains.interview.agents.session_state import (
    InterviewSessionState,
)
from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.process.round_plan_schema import (
    PlannedRound,
    RoundPlan,
    load_round_plan,
    parse_round_plan,
)
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




# ---- load / clamp ----












# ---- notes ----












# ---- pace ----










# ---- phase queries ----








# ---- progression ----










# ---- session_overrides ----








# ---- compaction thresholds ----














# ---- round plan schema extras ----


def test_planned_round_projections() -> None:
    r = PlannedRound(
        round_no=1,
        kind="tech_1",
        workflow_type="technical",
        personality="expert",
        interview_style="deep_dive",
        strictness=5,
        focus="f",
        label="l",
        pass_criteria="p",
    )
    d = r.to_dict()
    assert d["round_no"] == 1 and d["pass_criteria"] == "p"
    step = r.to_step()
    assert step.kind == "tech_1"
    plan = RoundPlan(rounds=[r], note="n")
    assert plan.to_dict()["schema"].startswith("realmock.round_plan")


def test_parse_round_plan_string_and_workflow_derive() -> None:
    raw = json.dumps(
        {
            "note": "n",
            "rounds": [
                {
                    "kind": "tech_1",
                    "workflow_type": "nope",
                    "personality": "nope",
                    "interview_style": "nope",
                    "strictness": "bad",
                    "focus": "focus here",
                    "label": "",
                },
                {"kind": "mgmt", "focus": "lead"},
                {"kind": "hr_1", "focus": "motivation"},
                "garbage",
                {"kind": "tech_1", "focus": ""},
            ],
        }
    )
    plan = parse_round_plan(raw)
    assert plan is not None
    assert plan.rounds[0].workflow_type == "technical"
    assert plan.rounds[0].label  # fallback to focus slice
    kinds = [x.kind for x in plan.rounds]
    assert "mgmt" in kinds and "hr_1" in kinds


def test_load_round_plan_exception_returns_none() -> None:
    proc = SimpleNamespace(round_plan_status="ready", round_plan="{}", id=1)
    with patch(
        "realmock.domains.interview.process.round_plan_schema.parse_round_plan",
        side_effect=RuntimeError("boom"),
    ):
        assert load_round_plan(proc) is None


# ---- round planner background ----












