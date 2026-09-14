"""Agent-planned interview flow: schema, prompt building, and generation.

The interviewer agent owns its own flow: before the opening turn a planner
call turns resume/profile/process context into an ``InterviewPlan`` of 8-30
steps stored on the session row. Static ``Workflow``s remain only as the
degraded fallback. Plan steps duck-type ``PhaseDef`` (id/name/description/
min/max questions) so the existing phase-advancement machinery is reused.
"""

from __future__ import annotations

from .plan_schema import (
    MAX_PLAN_STEPS,
    MIN_PLAN_STEPS,
    InterviewPlan,
    PlanStep,
    parse_plan,
    plan_step_views,
)
from .planner import (
    PLAN_WAIT_TIMEOUT_SECONDS,
    ensure_plan,
    generate_plan_for_session,
    wait_for_plan_ready,
)

__all__ = [
    "MAX_PLAN_STEPS",
    "MIN_PLAN_STEPS",
    "PLAN_WAIT_TIMEOUT_SECONDS",
    "InterviewPlan",
    "PlanStep",
    "ensure_plan",
    "generate_plan_for_session",
    "parse_plan",
    "plan_step_views",
    "wait_for_plan_ready",
]
