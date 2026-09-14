"""Deterministic multi-round interview chains: one process simulates a real
company loop (technical round 1 → technical round 2 → HR round 1 → HR round 2).

The chain is derived from the process's base workflow and its round budget —
no schema involved. Each round maps to a :class:`RoundStep` that overrides the
round session's workflow / personality / strictness / style and carries a
focus line for the interviewer persona, so a "technical" process actually
walks the candidate through distinct interviewer types instead of N clones of
the same interview. ``render_for_prompt`` consumers keep working unchanged;
the chain only decides what each round IS.
"""

from __future__ import annotations

from dataclasses import dataclass

from realmock.domains.interview.constants import MAX_INTERVIEW_ROUNDS

# Stable round-kind ids (frontend i18n keys key off these; never rename).
KIND_TECH_1 = "tech_1"
KIND_TECH_2 = "tech_2"
KIND_TECH_DEEP = "tech_deep"
KIND_HR_1 = "hr_1"
KIND_HR_2 = "hr_2"
KIND_MGMT = "mgmt"
KIND_CROSS = "cross"


@dataclass(frozen=True)
class RoundStep:
    """One planned round: which workflow drives it and who the interviewer is."""

    round_no: int
    kind: str
    workflow_type: str
    personality: str
    interview_style: str
    strictness: int
    #: One line steering this round's questioning focus (English; prompt-side).
    focus: str
    #: Backend-side display name (English); localized names live in the frontend i18n.
    label: str


def _step(round_no: int, kind: str, workflow: str, personality: str, style: str, strictness: int, focus: str, label: str) -> RoundStep:
    return RoundStep(
        round_no=round_no,
        kind=kind,
        workflow_type=workflow,
        personality=personality,
        interview_style=style,
        strictness=max(1, min(10, strictness)),
        focus=focus,
        label=label,
    )


def _technical_chain() -> list[RoundStep]:
    return [
        _step(1, KIND_TECH_1, "technical", "expert", "deep_dive", 3,
              "fundamentals and one resume project; establish a baseline",
              "Technical Round 1"),
        _step(2, KIND_TECH_2, "technical", "expert", "challenging", 5,
              "deep-dive the strongest project and system-design trade-offs; challenge every claim",
              "Technical Round 2"),
        _step(3, KIND_HR_1, "hr", "hr", "guided", 2,
              "motivation, career plan, and teamwork; keep it warm",
              "HR Round 1"),
        _step(4, KIND_HR_2, "hr", "professional", "continuous", 4,
              "pressure handling, compensation expectations, and overall fit; final judgement",
              "HR Round 2"),
        _step(5, KIND_TECH_DEEP, "technical", "expert", "challenging", 6,
              "cross-check round: verify earlier weak points from new angles",
              "Technical Cross-check"),
        _step(6, KIND_CROSS, "management", "pressure", "challenging", 7,
              "senior loop: business sense and architecture leadership",
              "Final Loop"),
        _step(7, KIND_TECH_DEEP, "technical", "pressure", "continuous", 8,
              "stress round: rapid deep probes with little think time",
              "Stress Round"),
        _step(8, KIND_CROSS, "management", "pressure", "challenging", 9,
              "executive round: strategy, ownership, and growth",
              "Executive Round"),
    ]


def _hr_chain() -> list[RoundStep]:
    return [
        _step(1, KIND_HR_1, "hr", "hr", "guided", 2,
              "motivation, career plan, and culture fit; keep it warm",
              "HR Round 1"),
        _step(2, KIND_HR_2, "hr", "professional", "continuous", 4,
              "pressure handling, compensation expectations, and overall fit",
              "HR Round 2"),
        _step(3, KIND_TECH_1, "technical", "expert", "deep_dive", 3,
              "technical baseline: fundamentals and one resume project",
              "Technical Round 1"),
        _step(4, KIND_TECH_2, "technical", "expert", "challenging", 5,
              "technical depth: system-design trade-offs and challenge probes",
              "Technical Round 2"),
        _step(5, KIND_MGMT, "management", "professional", "deep_dive", 4,
              "leadership and decision-making cases",
              "Management Round"),
        _step(6, KIND_HR_2, "hr", "professional", "challenging", 5,
              "final HR judgement: fit, stability, and offer expectations",
              "HR Final"),
        _step(7, KIND_CROSS, "management", "pressure", "challenging", 7,
              "senior loop: business sense and architecture leadership",
              "Final Loop"),
        _step(8, KIND_TECH_DEEP, "technical", "pressure", "continuous", 8,
              "stress round: rapid deep probes with little think time",
              "Stress Round"),
    ]


def _management_chain() -> list[RoundStep]:
    return [
        _step(1, KIND_MGMT, "management", "professional", "deep_dive", 3,
              "leadership experience and decision-making cases",
              "Management Round 1"),
        _step(2, KIND_MGMT, "management", "pressure", "challenging", 5,
              "business sense and conflict handling under challenge",
              "Management Round 2"),
        _step(3, KIND_HR_1, "hr", "hr", "guided", 2,
              "motivation, career plan, and team-fit",
              "HR Round 1"),
        _step(4, KIND_HR_2, "hr", "professional", "continuous", 4,
              "pressure handling, compensation expectations, and overall fit",
              "HR Round 2"),
        _step(5, KIND_TECH_1, "technical", "expert", "deep_dive", 3,
              "technical literacy check for a management role",
              "Technical Round"),
        _step(6, KIND_CROSS, "management", "pressure", "challenging", 7,
              "executive round: strategy, ownership, and growth",
              "Executive Round"),
        _step(7, KIND_HR_2, "hr", "professional", "challenging", 5,
              "final HR judgement: fit, stability, and offer expectations",
              "HR Final"),
        _step(8, KIND_TECH_DEEP, "technical", "pressure", "continuous", 8,
              "stress round: rapid deep probes with little think time",
              "Stress Round"),
    ]


_CHAINS: dict[str, list[RoundStep]] = {
    "technical": _technical_chain(),
    "hr": _hr_chain(),
    "management": _management_chain(),
}


def round_chain(base_workflow: str, max_rounds: int) -> list[RoundStep]:
    """The planned round list for a process, capped by the round budget.

    Unknown base workflows fall back to the technical chain (mirrors
    ``get_workflow``). ``max_rounds`` is clamped to the global round cap; the
    canonical chain always fills the budget (beyond the canonical length the
    last step repeats unchanged).
    """
    budget = max(1, min(int(max_rounds or MAX_INTERVIEW_ROUNDS), MAX_INTERVIEW_ROUNDS))
    canonical = _CHAINS.get(str(base_workflow or ""), _technical_chain())
    steps: list[RoundStep] = []
    for no in range(1, budget + 1):
        base = canonical[min(no, len(canonical)) - 1]
        steps.append(
            RoundStep(
                round_no=no,
                kind=base.kind,
                workflow_type=base.workflow_type,
                personality=base.personality,
                interview_style=base.interview_style,
                strictness=base.strictness,
                focus=base.focus,
                label=base.label,
            )
        )
    return steps


def step_for(base_workflow: str, round_no: int, max_rounds: int) -> RoundStep | None:
    """One step of the chain (None when the round number is out of range)."""
    steps = round_chain(base_workflow, max_rounds)
    for step in steps:
        if step.round_no == round_no:
            return step
    return None


__all__ = [
    "KIND_CROSS",
    "KIND_HR_1",
    "KIND_HR_2",
    "KIND_MGMT",
    "KIND_TECH_1",
    "KIND_TECH_2",
    "KIND_TECH_DEEP",
    "RoundStep",
    "round_chain",
    "step_for",
]
