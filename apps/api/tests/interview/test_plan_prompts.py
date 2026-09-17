"""Plan prompts tests for src/realmock/domains/interview/process/planning/plan_prompts.py.

Covers: build_plan_user_message branches, planner_system_prompt
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


# ---- plan_prompts (61, 68, 78-89, 96) ----


def test_plan_user_message_all_branches() -> None:
    from realmock.domains.interview.agents.planning import plan_prompts as mod
    from realmock.domains.interview.schemas import InterviewConfig

    cfg = InterviewConfig(role="BE", level="S", company="Acme")
    profile = SimpleNamespace(
        preferred_languages="English",
        name="Ada",
        target_role="BE",
        experience_years=3,
        tech_domains_list=["Python"],
        career_highlights="built cache",
    )
    payload = {
        "projects": [
            {"name": "p1", "stack": "py", "summary": "s1", "extra": 1},
            "not-a-dict",
        ],
        "skills": ["Python", "Redis"],
    }
    out = mod.build_plan_user_message(
        cfg,
        resume_payload=payload,
        profile=profile,
        process_section="prior rounds memory",
        company_context="Acme cloud",
        ui_locale="zh-CN",
    )
    assert "candidate preferred languages" in out
    assert "Candidate profile" in out
    assert "Resume" in out
    assert "Prior rounds" in out
    assert mod.planner_system_prompt().startswith("You are a senior")


# ---- process_service (165, 278-279, 308-310) ----




    # No crash, warning path (278-279).




# ---- turns (115, 118, 122, 155, 166-168) ----


def _turn_session(**kw):
    base = {
        "id": 1,
        "status": "pending",
        "current_phase": "tech",
        "access_token": "tok",
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _turn_db(session_row=None):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = session_row
    return db






