"""Unit tests for the followup signal analyzer."""

from __future__ import annotations

from realmock.domains.interview.agents.followup import analyze


def test_empty_answer_triggers_missing_data() -> None:
    sig = analyze("")
    assert sig.needs_followup
    assert sig.category == "missing_data"


def test_vague_terms_short_answer_triggers_vague() -> None:
    # Chinese vague fillers remain first-class for zh answers
    sig = analyze("差不多就是这样吧", question="请描述一次性能优化")
    assert sig.needs_followup
    assert sig.category == "vague"


def test_vague_terms_english_short_answer_triggers_vague() -> None:
    sig = analyze("That's about it", question="Describe a performance optimization")
    assert sig.needs_followup
    assert sig.category == "vague"


def test_long_answer_without_data_triggers_missing_data() -> None:
    sig = analyze(
        "我们对这个接口进行了完整的性能优化工作，从架构设计到代码实现"
        "都做了深入的改进，整体效果非常好，用户反馈也很满意。",
        question="请说说这次性能优化的具体效果",
    )
    assert sig.needs_followup
    assert sig.category == "missing_data"


def test_answer_with_quantitative_data_passes() -> None:
    sig = analyze(
        "Endpoint RT dropped from 200 ms to 35 ms, QPS increased from 1.2k to 8k, and the error rate fell by 90%.",
        question="Describe the specific results of this performance optimization",
    )
    assert not sig.needs_followup


def test_off_topic_low_overlap_triggers_off_topic() -> None:
    # Must stay under the short-answer threshold (<30 chars) for the off_topic rule
    sig = analyze(
        "I like basketball.",
        question="Describe the project you are most proud of and explain your role in it.",
    )
    assert sig.needs_followup
    assert sig.category == "off_topic"


def test_tech_hole_triggers_when_no_domain_match() -> None:
    # Include a quantity so missing_data does not win; still no declared tech domains.
    sig = analyze(
        "I wrote the PRD with the PM after user interviews (n=12).",
        question="Introduce your technical project",
        tech_domains=["Python", "FastAPI", "PostgreSQL"],
    )
    assert sig.needs_followup
    assert sig.category == "tech_hole"


def test_answer_with_tech_keywords_passes() -> None:
    sig = analyze(
        "We refactored the API with FastAPI and optimized the PostgreSQL indexes,"
        "QPS increased to 12,000.",
        question="Introduce your technical project",
        tech_domains=["Python", "FastAPI", "PostgreSQL"],
    )
    assert not sig.needs_followup


def test_suggested_probe_is_non_empty_when_followup() -> None:
    sig = analyze("可能差不多吧", question="自我介绍")
    assert sig.suggested_probe
    assert len(sig.suggested_probe) > 5


def test_missing_data_skipped_in_reverse_qa_phase() -> None:
    """The candidate-question phase should not trigger missing_data."""
    sig = analyze(
        "I would like to learn about your company's technology stack, team collaboration practices, and onboarding program.",
        question="You can ask me questions now",
        phase_id="reverse_qa",
    )
    assert not sig.needs_followup


def test_tech_hole_skipped_in_summary_phase() -> None:
    """The summary stage should not trigger tech_hole."""
    sig = analyze(
        "The interviewer gave a summary assessment and thanked the candidate for their time.",
        question="Please summarize",
        tech_domains=["Python", "FastAPI"],
        phase_id="summary",
    )
    assert not sig.needs_followup


def test_missing_data_still_triggers_in_technical_phase() -> None:
    """Evaluation phases (project_deep_dive) should still trigger missing_data."""
    sig = analyze(
        "我们对这个接口进行了完整的性能优化工作，从架构设计到代码实现"
        "都做了深入的改进，整体效果非常好。",
        question="请说说性能优化的效果",
        phase_id="project_deep_dive",
    )
    assert sig.needs_followup
    assert sig.category == "missing_data"


def test_vague_still_triggers_in_reverse_qa_phase() -> None:
    """Vague terms should trigger at every stage (including candidate questions)."""
    sig = analyze(
        "大概可能就是想了解一下公司情况吧",
        question="你想了解什么",
        phase_id="reverse_qa",
    )
    assert sig.needs_followup
    assert sig.category == "vague"
