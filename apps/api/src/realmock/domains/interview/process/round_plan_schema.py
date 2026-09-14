"""HR round-program value objects with tolerant parsing and clamping.

Mirrors :mod:`planning.plan_schema`: the HR planner agent authors a
multi-round program (round count / kinds / interviewer persona /
pass criteria); field-level drift degrades only that field, structural
garbage yields None so callers fall back to the static
:func:`round_chain.round_chain`.

Kind ids are pinned to the :mod:`round_chain` vocabulary (frontend i18n
keys off them; never accept free-form kinds).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from realmock.domains.interview.constants import MAX_INTERVIEW_ROUNDS
from realmock.domains.interview.process.round_chain import (
    KIND_CROSS,
    KIND_HR_1,
    KIND_HR_2,
    KIND_MGMT,
    KIND_TECH_1,
    KIND_TECH_2,
    KIND_TECH_DEEP,
    RoundStep,
)

logger = logging.getLogger(__name__)

SCHEMA = "realmock.round_plan.v1"

#: Kind ids the frontend can label (see web i18n process.kind.*).
KNOWN_KINDS = (
    KIND_TECH_1,
    KIND_TECH_2,
    KIND_TECH_DEEP,
    KIND_HR_1,
    KIND_HR_2,
    KIND_MGMT,
    KIND_CROSS,
)

#: Closed vocabularies (mirror the process/session request Literals).
KNOWN_WORKFLOWS = ("technical", "hr", "management")
KNOWN_PERSONALITIES = ("gentle", "professional", "pressure", "hr", "expert")
KNOWN_STYLES = ("guided", "deep_dive", "continuous", "challenging")

FOCUS_MAX_CHARS = 400
LABEL_MAX_CHARS = 60
PASS_CRITERIA_MAX_CHARS = 300


@dataclass
class PlannedRound:
    """One HR-planned round: who interviews and what passes."""

    round_no: int
    kind: str
    workflow_type: str
    personality: str
    interview_style: str
    strictness: int
    focus: str
    label: str
    #: One-to-two-line pass bar for this round (candidate-visible; also fed
    #: to the round interviewer's flow planner). The pass/fail call itself
    #: stays with the round interviewer's verdict.
    pass_criteria: str = ""

    def to_dict(self) -> dict:
        return {
            "round_no": self.round_no,
            "kind": self.kind,
            "workflow_type": self.workflow_type,
            "personality": self.personality,
            "interview_style": self.interview_style,
            "strictness": self.strictness,
            "focus": self.focus,
            "label": self.label,
            "pass_criteria": self.pass_criteria,
        }

    def to_step(self) -> RoundStep:
        """Project onto the static-chain shape driving session creation."""
        return RoundStep(
            round_no=self.round_no,
            kind=self.kind,
            workflow_type=self.workflow_type,
            personality=self.personality,
            interview_style=self.interview_style,
            strictness=self.strictness,
            focus=self.focus,
            label=self.label,
        )


@dataclass
class RoundPlan:
    """HR-authored multi-round program for one process."""

    rounds: list[PlannedRound] = field(default_factory=list)
    note: str = ""  # one-line rationale, e.g. "3 rounds: junior role, single tech + HR"
    source: str = "agent"  # "agent" (LLM-authored)

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "note": self.note,
            "source": self.source,
            "rounds": [r.to_dict() for r in self.rounds],
        }


def _clean_round(raw: object, round_no: int) -> PlannedRound | None:
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip()
    if kind not in KNOWN_KINDS:
        return None
    workflow = str(raw.get("workflow_type") or "").strip()
    if workflow not in KNOWN_WORKFLOWS:
        # Derive from kind: hr_* -> hr, mgmt/cross -> management, else technical.
        if kind.startswith("hr"):
            workflow = "hr"
        elif kind in (KIND_MGMT, KIND_CROSS):
            workflow = "management"
        else:
            workflow = "technical"
    personality = str(raw.get("personality") or "").strip()
    if personality not in KNOWN_PERSONALITIES:
        personality = "hr" if workflow == "hr" else "professional"
    style = str(raw.get("interview_style") or "").strip()
    if style not in KNOWN_STYLES:
        style = "guided" if workflow == "hr" else "deep_dive"
    try:
        strictness = max(1, min(10, int(raw.get("strictness") or 3)))
    except (TypeError, ValueError):
        strictness = 3
    focus = str(raw.get("focus") or "").strip()[:FOCUS_MAX_CHARS]
    label = str(raw.get("label") or "").strip()[:LABEL_MAX_CHARS]
    if not focus:
        return None
    return PlannedRound(
        round_no=round_no,
        kind=kind,
        workflow_type=workflow,
        personality=personality,
        interview_style=style,
        strictness=strictness,
        focus=focus,
        label=label or focus[:30],
        pass_criteria=str(raw.get("pass_criteria") or "").strip()[:PASS_CRITERIA_MAX_CHARS],
    )


def parse_round_plan(data: object) -> RoundPlan | None:
    """Parse a stored/generated round program; None when unusable.

    Rounds are renumbered sequentially (the LLM's numbering is not trusted);
    total rounds clamp to ``MAX_INTERVIEW_ROUNDS``.
    """
    if isinstance(data, str):
        try:
            data = json.loads(data or "{}")
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    raw_rounds = data.get("rounds")
    if not isinstance(raw_rounds, list):
        return None
    rounds: list[PlannedRound] = []
    for raw in raw_rounds[:MAX_INTERVIEW_ROUNDS]:
        step = _clean_round(raw, len(rounds) + 1)
        if step is not None:
            rounds.append(step)
    if not rounds:
        return None
    return RoundPlan(
        rounds=rounds,
        note=str(data.get("note") or "")[:200],
        source="agent",
    )


def load_round_plan(process: object) -> RoundPlan | None:
    """Load the LLM-authored program off a process row (ready-only)."""
    if getattr(process, "round_plan_status", "") != "ready":
        return None
    try:
        return parse_round_plan(getattr(process, "round_plan", None))
    except Exception:
        logger.warning("round plan parse failed pid=%s", getattr(process, "id", None))
        return None


__all__ = [
    "PlannedRound",
    "RoundPlan",
    "SCHEMA",
    "load_round_plan",
    "parse_round_plan",
]
