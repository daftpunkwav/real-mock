"""``realmock.domains.interview.agents.agent_prompts.build_system_prompt`` unit tests.

Coverage:
- Assemble normally without candidate (no resume bound);
- Serialize normally with candidate (including projects / work_experience) without raising NameError
  (regression: runtime crash from F821 because `json` was not imported);
- followup_probe injects the follow-up guidance section;
- profile section.
"""

from __future__ import annotations

from realmock.platform.schemas import CandidateProfile
from realmock.domains.interview.schemas import InterviewConfig
from realmock.domains.interview.agents.agent_prompts import build_system_prompt
from realmock.domains.interview.agents.workflows import get_workflow


def _config(**overrides) -> InterviewConfig:
    base = {
        "role": "Backend engineer",
        "level": "Senior",
        "company": "ByteDance",
    }
    base.update(overrides)
    return InterviewConfig(**base)


def _candidate(**overrides) -> CandidateProfile:
    base = {
        "name": "Zhang San",
        "skills": ["Python", "FastAPI"],
        "projects": [{"name": "MockInterviewApp", "desc": "AI mock interview"}],
        "work_experience": [{"company": "A certain company", "role": "Backend"}],
    }
    base.update(overrides)
    return CandidateProfile(**base)


def test_without_candidate_and_profile() -> None:
    """Assemble normally without a candidate or profile, including the basic sections."""
    prompt = build_system_prompt(
        config=_config(),
        candidate=None,
        company_context="Company overview: builds AI interview products",
        workflow=get_workflow("technical"),
        current_phase=get_workflow("technical").phases[0],
    )
    assert "Company overview" in prompt
    assert "interviewer" in prompt.lower() or "Interviewer" in prompt or "You are" in prompt


def test_with_candidate_serializes_projects() -> None:
    """When candidate is present, projects/work_experience should be serialized with json.dumps (F821 regression)."""
    prompt = build_system_prompt(
        config=_config(),
        candidate=_candidate(),
        company_context="",
        workflow=get_workflow("technical"),
        current_phase=get_workflow("technical").phases[0],
    )
    assert "Zhang San" in prompt
    assert "MockInterviewApp" in prompt  # projects content appears
    assert "A certain company" in prompt  # work_experience content appears


def test_with_followup_probe_injects_section() -> None:
    """followup_probe should inject a follow-up guidance section."""
    prompt = build_system_prompt(
        config=_config(),
        candidate=None,
        company_context="",
        workflow=get_workflow("technical"),
        current_phase=get_workflow("technical").phases[0],
        followup_probe="Candidate seems weak on system design; probe cache consistency deeper.",
    )
    assert "Follow-up guidance" in prompt
    assert "cache consistency" in prompt


def test_with_profile_includes_personal_info() -> None:
    """Include the candidate profile section when profile is provided."""
    from realmock.platform.models import UserProfile

    profile = UserProfile(
        name="Li Si",
        school="A certain university",
        self_intro="5 years of backend experience",
        job_direction="Backend",
        target_role="Senior backend engineer",
        tech_domains='["Python", "Go"]',
    )
    prompt = build_system_prompt(
        config=_config(),
        candidate=None,
        company_context="",
        workflow=get_workflow("technical"),
        current_phase=get_workflow("technical").phases[0],
        profile=profile,
    )
    assert "Candidate profile" in prompt
    assert "Li Si" in prompt


def _prompt_kwargs(**overrides):
    kw = {
        "config": _config(),
        "candidate": None,
        "company_context": "",
        "workflow": get_workflow("technical"),
        "current_phase": get_workflow("technical").phases[0],
    }
    kw.update(overrides)
    return kw


def test_default_flow_language_is_chinese() -> None:
    """Without flow_language the interviewer defaults to Chinese."""
    prompt = build_system_prompt(**_prompt_kwargs())
    assert "Communicate in Chinese" in prompt


def test_english_flow_language_directs_english() -> None:
    """flow_language=en switches the whole interview to English."""
    prompt = build_system_prompt(**_prompt_kwargs(flow_language="en"))
    assert "entire interview in English" in prompt
    assert "Communicate in Chinese" not in prompt


def test_plan_ops_rule_mentions_revision_triggers() -> None:
    """The plan_ops rule tells the model when to revise the flow."""
    prompt = build_system_prompt(**_prompt_kwargs(allow_plan_ops=True))
    assert "plan_ops" in prompt
    assert "unlisted project" in prompt
