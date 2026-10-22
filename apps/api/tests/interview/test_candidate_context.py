"""Shared candidate-grounding block tests for the interview planners.

Both planners ground their prompt in the same candidate profile block
(``agents/planning/candidate_context.py``), rendered once from the declared
profile read model. The block is the same text for both planners; only the
round planner caps the career highlights, because the round program is a
short document while the flow plan grounds in the whole career history.

Conventions: pure text construction; no LLM, no DB.
"""

from __future__ import annotations

from realmock.domains.interview.agents.planning.candidate_context import (
    HR_HIGHLIGHTS_MAX_CHARS,
    candidate_profile_block,
)
from realmock.domains.interview.agents.planning.plan_prompts import build_plan_user_message
from realmock.domains.interview.agents.planning.round_plan_prompts import (
    build_round_plan_user_message,
)
from realmock.domains.interview.schemas import InterviewConfig
from realmock.platform.schemas import UserProfileSnapshot

#: Career highlights long enough to be clipped by the round planner.
_LONG_HIGHLIGHTS = "H" * 600


def _profile(**overrides) -> UserProfileSnapshot:
    base = {
        "name": "Ada",
        "target_role": "Backend",
        "experience_years": "3",
        "tech_domains_list": ["Python", "Redis"],
        "career_highlights": _LONG_HIGHLIGHTS,
    }
    base.update(overrides)
    return UserProfileSnapshot(**base)


def test_candidate_profile_block_is_empty_without_a_profile() -> None:
    """No profile means no block: the planner prompt carries no empty section."""
    assert candidate_profile_block(None) == ""


def test_candidate_profile_block_renders_the_read_model_fields() -> None:
    """The block carries the profile fields the planners ground on."""
    block = candidate_profile_block(_profile())
    assert "## Candidate profile" in block
    assert "Name: Ada" in block
    assert "Target role: Backend" in block
    assert "Experience: 3 years" in block
    assert "Tech domains: Python, Redis" in block
    assert "Highlights: " in block


def test_candidate_profile_block_marks_the_unset_fields() -> None:
    """An unset field renders as a dash, never as a blank line."""
    block = candidate_profile_block(UserProfileSnapshot())
    assert "Name: —" in block
    assert "Target role: —" in block
    assert "Experience: — years" in block
    assert "Tech domains: —" in block
    assert "Highlights: —" in block


def test_candidate_profile_block_clips_the_highlights_when_asked() -> None:
    """The caller decides how much of the highlights text the prompt carries."""
    block = candidate_profile_block(_profile(), max_highlights_chars=10)
    assert "Highlights: " + "H" * 10 in block
    assert "H" * 11 not in block


def test_flow_planner_keeps_the_whole_career_highlights() -> None:
    """The flow planner grounds the plan in the full career history."""
    message = build_plan_user_message(
        InterviewConfig(role="Backend", level="Senior", company="Acme"),
        candidate=None,
        profile=_profile(),
        process_section="",
        company_context="",
    )
    assert _LONG_HIGHLIGHTS in message


def test_round_planner_clips_the_career_highlights() -> None:
    """The round program is a short document: the highlights are a teaser.

    The cap belongs to the round planner only, so the flow planner keeps the
    whole text while the HR planner carries the first
    ``HR_HIGHLIGHTS_MAX_CHARS`` characters.
    """
    message = build_round_plan_user_message(
        role="Backend",
        level="junior",
        company="acme",
        round_budget=3,
        profile=_profile(),
        candidate=None,
        company_context="",
    )
    assert "H" * HR_HIGHLIGHTS_MAX_CHARS in message
    assert "H" * (HR_HIGHLIGHTS_MAX_CHARS + 1) not in message
