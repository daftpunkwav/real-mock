"""Interview workflow definitions (single source of truth for phase metadata).

Phase id / English name / description / question bounds live only here.
``InterviewPhaseId`` is the id enum; UI copy uses frontend i18n
(``interview.phase.*``), with ``phases.ts`` PHASE_LABELS as the English SSOT
lock against this module (see ``test_phase_ssot.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from realmock.domains.interview.constants import InterviewPhaseId, WorkflowType


@dataclass(frozen=True)
class PhaseDef:
    """Runtime definition for a single interview phase."""

    id: str
    name: str
    description: str
    min_questions: int = 1
    max_questions: int = 3


@dataclass
class Workflow:
    id: str
    name: str
    phases: list[PhaseDef] = field(default_factory=list)


def _p(
    phase_id: InterviewPhaseId,
    name: str,
    description: str,
    min_q: int = 1,
    max_q: int = 3,
) -> PhaseDef:
    return PhaseDef(phase_id.value, name, description, min_q, max_q)


TECHNICAL_WORKFLOW = Workflow(
    id=WorkflowType.TECHNICAL.value,
    name="Technical Interview",
    phases=[
        _p(InterviewPhaseId.IDENTITY_CHECK, "Identity check", "Confirm candidate identity with a brief greeting", 1, 1),
        _p(InterviewPhaseId.SELF_INTRO, "Self introduction", "Ask the candidate for a self introduction", 1, 1),
        _p(InterviewPhaseId.BASIC_KNOWLEDGE, "Fundamentals", "Assess role-related fundamentals", 2, 4),
        _p(InterviewPhaseId.PROJECT_DEEP_DIVE, "Project deep dive", "Deep-dive into resume projects", 3, 6),
        _p(InterviewPhaseId.TECHNICAL_DEEP, "Technical deep dive", "Deep technical assessment of the stack", 2, 4),
        _p(InterviewPhaseId.SYSTEM_DESIGN, "System design", "Design or architecture discussion", 1, 2),
        _p(InterviewPhaseId.SCENARIO, "Scenario questions", "Realistic on-the-job scenario questions", 1, 2),
        _p(InterviewPhaseId.REVERSE_QA, "Your questions", "Candidate asks the interviewer questions", 1, 3),
        _p(InterviewPhaseId.SUMMARY, "Summary", "Brief interviewer wrap-up", 1, 1),
    ],
)

HR_WORKFLOW = Workflow(
    id=WorkflowType.HR.value,
    name="HR Interview",
    phases=[
        _p(InterviewPhaseId.IDENTITY_CHECK, "Identity check", "Confirm identity", 1, 1),
        _p(InterviewPhaseId.SELF_INTRO, "Self introduction", "Self introduction", 1, 1),
        _p(InterviewPhaseId.CAREER_PLAN, "Career plans", "Explore career direction", 2, 3),
        _p(InterviewPhaseId.TEAMWORK, "Teamwork", "Team collaboration experience", 2, 3),
        _p(InterviewPhaseId.PRESSURE, "Pressure questions", "Pressure and conflict handling", 1, 2),
        _p(InterviewPhaseId.SALARY, "Compensation", "Compensation expectations (simulated)", 1, 1),
        _p(InterviewPhaseId.REVERSE_QA, "Your questions", "Candidate questions", 1, 3),
        _p(InterviewPhaseId.SUMMARY, "Summary", "Wrap-up", 1, 1),
    ],
)

MANAGEMENT_WORKFLOW = Workflow(
    id=WorkflowType.MANAGEMENT.value,
    name="Management Interview",
    phases=[
        _p(InterviewPhaseId.IDENTITY_CHECK, "Identity check", "Confirm identity", 1, 1),
        _p(InterviewPhaseId.SELF_INTRO, "Self introduction", "Self introduction", 1, 1),
        _p(InterviewPhaseId.LEADERSHIP, "Leadership", "Team leadership experience", 2, 4),
        _p(InterviewPhaseId.DECISION_MAKING, "Decision making", "Key decision cases", 2, 3),
        _p(InterviewPhaseId.CONFLICT, "Conflict handling", "Team conflict resolution", 1, 2),
        _p(InterviewPhaseId.BUSINESS, "Business sense", "Business and strategy understanding", 2, 3),
        _p(InterviewPhaseId.REVERSE_QA, "Your questions", "Candidate questions", 1, 3),
        _p(InterviewPhaseId.SUMMARY, "Summary", "Wrap-up", 1, 1),
    ],
)

WORKFLOWS: dict[str, Workflow] = {
    WorkflowType.TECHNICAL.value: TECHNICAL_WORKFLOW,
    WorkflowType.HR.value: HR_WORKFLOW,
    WorkflowType.MANAGEMENT.value: MANAGEMENT_WORKFLOW,
}


def phase_label_map() -> dict[str, str]:
    """Phase id → English display name across all workflows (technical first)."""
    labels: dict[str, str] = {}
    for wf in (TECHNICAL_WORKFLOW, HR_WORKFLOW, MANAGEMENT_WORKFLOW):
        for p in wf.phases:
            labels.setdefault(p.id, p.name)
    return labels


def technical_phase_order() -> tuple[str, ...]:
    """Technical workflow phase id order (authoritative)."""
    return tuple(p.id for p in TECHNICAL_WORKFLOW.phases)


PERSONALITY_PROMPTS = {
    "gentle": "You are a warm, friendly interviewer; encourage and guide the candidate when helpful. Let it show in speech: 嗯 / 别急 / 慢慢说 sparingly, plus warm one-line acknowledgments.",
    "professional": "You are a professional, rigorous interviewer; ask precise questions and probe for logic and depth. Spoken but crisp: short sentences, direct transitions (那 / 好，下一个点).",
    "pressure": "You are a high-pressure interviewer; ask sharp follow-ups without giving the candidate much breathing room. Clipped and fast: very short sentences, cut off vagueness immediately, no softening.",
    "hr": "You are an HR interviewer; focus on soft skills, culture fit, and career plans. Conversational and curious: small acknowledgments, natural topic bridges.",
    "expert": "You are a technical-expert interviewer; go deep on details and first-principles understanding. Think aloud with the candidate: short probing bursts, always demand the mechanism (然后呢 / 底层到底发生了什么).",
}

STYLE_PROMPTS = {
    "guided": "Use a guided style: give light hints when the candidate's answer is incomplete. Hint in half a sentence, then hand the question straight back.",
    "deep_dive": "Use a deep-dive style: follow each answer 3–5 layers until you reach the technical essence. Drill with short single questions, one layer at a time.",
    "continuous": "Use continuous probing: stay on one technical point and dig deeper without switching topics. Chain short follow-ups; never drift.",
    "challenging": "Use a challenging style: question the candidate's approach and require justification. Doubt in one short sentence, then demand the reason.",
}

STRICTNESS_DESCRIPTIONS = {
    1: "Very friendly, like a casual conversation",
    2: "Fairly relaxed; occasional follow-ups",
    3: "Standard corporate interview intensity",
    4: "Somewhat strict; frequent detail probes",
    5: "Strict; do not accept vague answers",
    6: "High pressure; rapid follow-ups with little think time",
    7: "Very high pressure; challenge every claim",
    8: "Extreme pressure; simulate a big-tech final round",
    9: "Stress-test level",
    10: "Maximum stress test; push the candidate's limits",
}


def get_workflow(workflow_id: str) -> Workflow:
    """Look up a static interview workflow; unknown ids fall back to technical.

    Args:
        workflow_id: Workflow key (``technical`` | ``hr`` | ``management``).

    Returns:
        The matching workflow, or the technical workflow for legacy/unknown ids.
    """
    return WORKFLOWS.get(workflow_id, TECHNICAL_WORKFLOW)


# Alias: interview-domain ``InterviewPhase`` points at this PhaseDef dataclass
InterviewPhase = PhaseDef
