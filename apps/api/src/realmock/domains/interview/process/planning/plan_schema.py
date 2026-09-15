"""InterviewPlan / PlanStep value objects with tolerant parsing and clamping.

A plan step duck-types ``workflows.PhaseDef`` (id/name/description/min/max
questions) so :class:`InterviewSessionState` can advance either a static
workflow or an agent plan through the same code path.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from realmock.domains.interview.agents.workflows import Workflow

logger = logging.getLogger(__name__)

MIN_PLAN_STEPS = 8
MAX_PLAN_STEPS = 30
MIN_QUESTIONS = 1
STEP_QUESTIONS_MAX = 8
STEP_TITLE_MAX_CHARS = 60
STEP_FOCUS_MAX_CHARS = 400

#: Marker kind for the "candidate asks questions" step (special prompt rules).
REVERSE_QA_KIND = "reverse_qa"

#: Allowed opening styles (planner rule 3). Unknown values degrade to identity.
OPENING_STYLE_IDENTITY = "identity_confirm"
OPENING_STYLE_RESUME_ACK = "resume_ack"
OPENING_STYLE_WARMUP = "casual_warmup"
OPENING_STYLES = frozenset({OPENING_STYLE_IDENTITY, OPENING_STYLE_RESUME_ACK, OPENING_STYLE_WARMUP})

#: Fallback interview language for legacy plans without a language field.
DEFAULT_FLOW_LANGUAGE = "zh"


@dataclass
class PlanOpening:
    """How this session starts (planner rule 3; randomized per session)."""

    style: str = OPENING_STYLE_IDENTITY
    note: str = ""  # one-line personalization: name + one resume fact

    def to_dict(self) -> dict:
        """JSON-ready opening projection."""
        return {"style": self.style, "note": self.note}


def _clean_opening(raw: object) -> PlanOpening:
    """Validate the plan-level opening block; unknown styles degrade to identity."""
    if not isinstance(raw, dict):
        return PlanOpening()
    style = str(raw.get("style") or "").strip()[:30]
    if style not in OPENING_STYLES:
        style = OPENING_STYLE_IDENTITY
    return PlanOpening(style=style, note=str(raw.get("note") or "").strip()[:200])


def _clean_language(raw: object) -> str:
    """Normalize the plan-level flow language to "en" or "zh"."""
    text = str(raw or "").strip().lower()
    return "en" if text.startswith("en") else DEFAULT_FLOW_LANGUAGE


@dataclass
class PlanStep:
    """One step of the agent-planned flow (PhaseDef-compatible)."""

    id: str
    title: str
    focus: str
    min_questions: int = 1
    max_questions: int = 3
    kind: str = ""  # e.g. "reverse_qa"; free-form otherwise

    # PhaseDef compatibility: the state machine reads .name / .description.
    @property
    def name(self) -> str:
        """PhaseDef-compatible display name."""
        return self.title

    @property
    def description(self) -> str:
        """PhaseDef-compatible assessment focus."""
        return self.focus

    def to_dict(self) -> dict:
        """JSON-ready step projection (stable key order for storage)."""
        return {
            "id": self.id,
            "title": self.title,
            "focus": self.focus,
            "min_questions": self.min_questions,
            "max_questions": self.max_questions,
            "kind": self.kind,
        }


@dataclass
class InterviewPlan:
    """Agent-authored interview flow for one session."""

    steps: list[PlanStep] = field(default_factory=list)
    round_note: str = ""  # positioning of this round, e.g. "Round 1: fundamentals and project overview"
    source: str = "agent"  # "agent" | "fallback"
    language: str = DEFAULT_FLOW_LANGUAGE  # "zh" | "en": interview working language
    opening: PlanOpening = field(default_factory=PlanOpening)

    def to_dict(self) -> dict:
        """JSON-ready plan document (steps + round note + source)."""
        return {
            "round_note": self.round_note,
            "source": self.source,
            "language": self.language,
            "opening": self.opening.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
        }


def _clamp_questions(value, default_min: int = MIN_QUESTIONS) -> tuple[int, int]:
    """Clamp a raw min/max question pair into legal bounds."""
    if isinstance(value, bool) or not isinstance(value, int) or value < MIN_QUESTIONS:
        return default_min, min(default_min + 2, STEP_QUESTIONS_MAX)
    value = min(value, STEP_QUESTIONS_MAX)
    return MIN_QUESTIONS, value


def _clean_step(raw: object, index: int, used_ids: set[str] | None = None) -> PlanStep | None:
    """Validate one raw step dict; returns None for unusable entries.

    An existing non-duplicate ``id`` is preserved (fallback plans keep static
    phase ids); otherwise a synthetic ``sNN`` id is assigned.
    """
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()[:STEP_TITLE_MAX_CHARS]
    focus = str(raw.get("focus") or raw.get("description") or "").strip()[:STEP_FOCUS_MAX_CHARS]
    if not title:
        return None
    min_q, max_q = _clamp_questions(raw.get("max_questions"))
    kind = str(raw.get("kind") or "").strip()[:30]
    step_id = str(raw.get("id") or "").strip()[:30]
    if not step_id or (used_ids is not None and step_id in used_ids):
        step_id = f"s{index + 1:02d}"
    if used_ids is not None:
        used_ids.add(step_id)
    return PlanStep(
        id=step_id,
        title=title,
        focus=focus or title,
        min_questions=min_q,
        max_questions=max_q,
        kind=kind,
    )


def parse_plan(data: object) -> InterviewPlan | None:
    """Parse a stored/generated plan dict; returns None when unusable.

    Field-level drift degrades only that field; structural garbage (no usable
    steps) yields None so the caller can fall back to the static workflow.
    """
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            logger.debug("plan JSON unparsable; caller falls back")
            return None
    if not isinstance(data, dict):
        return None
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list):
        return None
    steps: list[PlanStep] = []
    used_ids: set[str] = set()
    for raw in raw_steps[:MAX_PLAN_STEPS]:
        step = _clean_step(raw, len(steps), used_ids)
        if step is not None:
            steps.append(step)
    if len(steps) < MIN_PLAN_STEPS:
        logger.info("plan rejected: only %d usable steps (need %d)", len(steps), MIN_PLAN_STEPS)
        return None
    plan = InterviewPlan(
        steps=steps,
        round_note=str(data.get("round_note") or "").strip()[:200],
        source=str(data.get("source") or "agent").strip()[:20] or "agent",
        language=_clean_language(data.get("language")),
        opening=_clean_opening(data.get("opening")),
    )
    if plan.steps and plan.steps[-1].kind != REVERSE_QA_KIND:
        # The closing step is always the summary/verdict phase (planner
        # contract rule 3) — whatever kind the model filled in. Tagging it lets
        # the state machine inject the per-question score trajectory there.
        plan.steps[-1].kind = "summary"
    return plan


def plan_from_workflow(workflow: Workflow) -> InterviewPlan:
    """Convert a static workflow into a fallback plan (degraded mode).

    Original phase ids are preserved so clients keep resolving static phases
    via i18n; only agent-generated steps carry synthetic ``sNN`` ids.
    """
    return InterviewPlan(
        steps=[
            PlanStep(
                id=p.id,
                title=p.name,
                focus=p.description,
                min_questions=p.min_questions,
                max_questions=p.max_questions,
                kind=REVERSE_QA_KIND if p.id == "reverse_qa" else "",
            )
            for p in workflow.phases
        ],
        round_note="",
        source="fallback",
    )


def plan_step_views(plan: InterviewPlan | None) -> list[dict]:
    """Light step list for API responses (id/title/status-agnostic)."""
    if plan is None:
        return []
    return [{"id": s.id, "title": s.title} for s in plan.steps]


__all__ = [
    "MAX_PLAN_STEPS",
    "MIN_PLAN_STEPS",
    "MIN_QUESTIONS",
    "REVERSE_QA_KIND",
    "STEP_FOCUS_MAX_CHARS",
    "STEP_QUESTIONS_MAX",
    "STEP_TITLE_MAX_CHARS",
    "DEFAULT_FLOW_LANGUAGE",
    "OPENING_STYLES",
    "OPENING_STYLE_IDENTITY",
    "OPENING_STYLE_RESUME_ACK",
    "OPENING_STYLE_WARMUP",
    "InterviewPlan",
    "PlanOpening",
    "PlanStep",
    "parse_plan",
    "plan_from_workflow",
    "plan_step_views",
]
