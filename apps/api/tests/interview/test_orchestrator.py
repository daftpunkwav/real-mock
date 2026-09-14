"""InterviewOrchestrator unit tests, focusing on the silent-follow-up indexing algorithm."""

from __future__ import annotations

from realmock.domains.interview.agents.orchestrator import InterviewOrchestrator


def test_silence_nudge_strict_branch_uses_strict_templates() -> None:
    """The high-pressure persona should use the strict branch template."""
    orch = InterviewOrchestrator()
    for _ in range(12):
        nudge = orch.build_silence_nudge("pressure", strictness=3)
        assert any(
            k in nudge
            for k in ("Conclusion", "Main point", "Time is limited", "One or two sentences", "More specific", "Respond directly")
        ), nudge


def test_silence_nudge_gentle_branch_uses_gentle_templates() -> None:
    """A gentle persona with low strictness should use the gentle branch template."""
    orch = InterviewOrchestrator()
    for _ in range(12):
        nudge = orch.build_silence_nudge("gentle", strictness=1)
        assert any(
            k in nudge
            for k in ("No problem", "Idea", "Start speaking", "Familiar", "Most memorable", "Try another angle", "Sub-question", "Context")
        ), nudge


def test_silence_nudge_low_strictness_uses_first_tier() -> None:
    """Strictness 1-4 should select the tier 0 gentle template."""
    orch = InterviewOrchestrator()
    for s in (1, 2, 3, 4):
        for _ in range(8):
            nudge = orch.build_silence_nudge("professional", strictness=s)
            assert any(
                k in nudge for k in ("No problem", "Idea", "Start speaking", "Familiar")
            ), f"strictness={s}: {nudge}"


def test_silence_nudge_mid_strictness_uses_second_tier() -> None:
    """Strictness 5-8: 5 uses the medium gentle tier, while >=6 uses the medium strict tier."""
    orch = InterviewOrchestrator()
    for s in (5, 6, 7, 8):
        for _ in range(8):
            nudge = orch.build_silence_nudge("professional", strictness=s)
            if s >= 6:
                assert any(
                    k in nudge for k in ("Time is limited", "One or two sentences", "Summarize")
                ), f"strictness={s}: {nudge}"
            else:
                assert any(
                    k in nudge for k in ("Most memorable", "Context", "Process", "Result", "Entry point")
                ), f"strictness={s}: {nudge}"


def test_silence_nudge_max_strictness_uses_last_tier() -> None:
    """Strictness 9-10 should select the most direct tier."""
    orch = InterviewOrchestrator()
    for s in (9, 10):
        for _ in range(8):
            nudge = orch.build_silence_nudge("professional", strictness=s)
            assert any(
                k in nudge for k in ("More specific", "Respond directly", "Key point")
            ), f"strictness={s}: {nudge}"


def test_silence_nudge_identity_phase_is_contextual() -> None:
    """The identity verification stage should use stage-specific copy."""
    orch = InterviewOrchestrator()
    for _ in range(10):
        nudge = orch.build_silence_nudge(
            "professional", strictness=1, phase="identity_check"
        )
        assert any(
            k in nudge for k in ("Confirm", "Identity", "Confirmed", "Formal interview")
        ), nudge


def test_silence_nudge_normal_strictness_not_skips_first_template() -> None:
    """Regression: normal strictness (1) should select the gentlest tier."""
    orch = InterviewOrchestrator()
    nudge = orch.build_silence_nudge("professional", strictness=1)
    assert any(k in nudge for k in ("No problem", "Idea", "Start speaking", "Familiar")), nudge
