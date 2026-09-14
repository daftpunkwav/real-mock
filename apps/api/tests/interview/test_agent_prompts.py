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


def test_spoken_voice_section_present() -> None:
    """The interviewer gets spoken-voice constraints outranking written style."""
    prompt = build_system_prompt(**_prompt_kwargs())
    assert "How you talk" in prompt
    # Ban list is spelled out (written scaffolding + hollow meta-questions).
    assert "综上所述" in prompt
    assert "首先" in prompt
    assert "能详细说说吗" in prompt


def test_turn_openings_rotate_not_template() -> None:
    """Openers must rotate (straight-in default); standalone 嗯/对/好 banned."""
    prompt = build_system_prompt(**_prompt_kwargs())
    assert "STRAIGHT" in prompt
    assert "很好的问题" in prompt  # named as forbidden
    assert "Three gears" in prompt


def test_personality_carries_spoken_flavor() -> None:
    """Persona prompts include a spoken delivery clause."""
    gentle = build_system_prompt(**_prompt_kwargs(config=_config(personality="gentle")))
    assert "别急" in gentle
    pressure = build_system_prompt(**_prompt_kwargs(config=_config(personality="pressure")))
    assert "Clipped" in pressure


def test_probe_system_prompt_differs_by_attempt() -> None:
    """Silence probes: check-in first, concrete sub-question second."""
    from realmock.domains.interview.realtime.control.silence_probe import probe_system_prompt

    first = probe_system_prompt(attempt=1)
    second = probe_system_prompt(attempt=2)
    assert first != second
    assert "综上所述" in first  # written scaffolding banned
    assert "能详细说说吗" in second  # hollow prompts banned on the 2nd attempt


def test_reverse_qa_uses_compact_candidate_block() -> None:
    """Non-questioning phases skip the resume dump (context savings)."""
    workflow = get_workflow("technical")
    phase = next(p for p in workflow.phases if p.id == "reverse_qa")
    prompt = build_system_prompt(
        **_prompt_kwargs(current_phase=phase, candidate=_candidate()),
    )
    assert "compact" in prompt
    assert "Parsed resume" not in prompt
    assert "Zhang San" in prompt  # identity kept


def test_questioning_phase_keeps_full_candidate_block() -> None:
    """Questioning phases keep full resume grounding."""
    prompt = build_system_prompt(
        **_prompt_kwargs(candidate=_candidate()),
    )
    assert "Parsed resume" in prompt
    assert "MockInterviewApp" in prompt


def test_refresh_system_head_swaps_candidate_and_phase() -> None:
    """Phase advance rebuilds the frozen head: compact card + fresh phase lines."""
    from types import SimpleNamespace

    from realmock.domains.interview.agents.session_prompt import SessionPromptMixin

    opening_prompt = build_system_prompt(
        **_prompt_kwargs(candidate=_candidate()),
    )
    mixin = SessionPromptMixin()
    mixin.session = SimpleNamespace(profile_id=1, resume_id=None, company="ByteDance")
    mixin.agent_state = {"asked_questions": ["Old question"]}
    mixin.messages = [{
        "role": "system",
        "content": (
            opening_prompt
            + "\n\n## Session structured memory (do not repeat asked questions)\n"
            "Covered: Old question"
        ),
    }]
    reverse_qa = next(p for p in get_workflow("technical").phases if p.id == "reverse_qa")
    profile_stub = SimpleNamespace(
        name="Zhang San", target_role="Backend", school="TSU", github_username="",
    )

    mixin.refresh_system_head(reverse_qa, profile=profile_stub, candidate=_candidate())

    head = mixin.messages[0]["content"]
    assert "Candidate (compact" in head  # resume dump swapped for the card
    assert "Parsed resume" not in head
    assert "Work experience" not in head  # dump detail gone (project names stay)
    assert "Phase: Your questions (reverse_qa)" in head  # stale phase refreshed
    assert "## Full flow" in head
    assert "Covered: Old question" in head  # memory section survives


def test_refresh_system_head_keeps_full_block_for_questioning_phase() -> None:
    """Questioning-phase advances only refresh the phase lines, no DB lookup."""
    from types import SimpleNamespace

    from realmock.domains.interview.agents.session_prompt import SessionPromptMixin

    opening_prompt = build_system_prompt(
        **_prompt_kwargs(candidate=_candidate()),
    )
    mixin = SessionPromptMixin()
    mixin.session = SimpleNamespace(profile_id=1, resume_id=None, company="")
    mixin.agent_state = {}
    mixin.messages = [{"role": "system", "content": opening_prompt}]
    next_phase = get_workflow("technical").phases[2]  # basic_knowledge

    mixin.refresh_system_head(next_phase, profile=object(), candidate=object())

    head = mixin.messages[0]["content"]
    assert "Parsed resume" in head
    assert f"Phase: {next_phase.name}" in head


def test_probe_system_prompt_follows_flow_language() -> None:
    """English-flow probes must not embed Chinese filler words."""
    from realmock.domains.interview.realtime.control.silence_probe import probe_system_prompt

    en_first = probe_system_prompt(attempt=1, lang="en")
    en_second = probe_system_prompt(attempt=2, lang="en")
    for prompt in (en_first, en_second):
        assert "诶" not in prompt and "还在吗" not in prompt
    assert "hey, still there?" in en_first
    assert "elaborate" in en_second
    # Chinese flow keeps its idiomatic wording.
    zh_first = probe_system_prompt(attempt=1, lang="zh")
    assert "还在吗" in zh_first


def test_system_prompt_resists_candidate_manipulation() -> None:
    """Behavior rules cover fishing for answers / a favorable verdict."""
    prompt = build_system_prompt(**_prompt_kwargs())
    assert "fish for answers" in prompt
    assert "judge only by demonstrated performance" in prompt


def test_spoken_voice_covers_followup_chain_and_pressure_release() -> None:
    """Human-feel rules: chained probes go bare; stuck answers get a pressure-release line."""
    prompt = build_system_prompt(**_prompt_kwargs())
    assert "zero preamble" in prompt
    assert "releases the pressure" in prompt
    assert "never announce a verdict mid-interview" in prompt
