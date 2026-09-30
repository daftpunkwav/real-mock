"""Growth HTTP response schemas (history / system insights / aggregated / LLM insight).

Field-by-field mirror of the dicts returned by ``domains.growth.routes.router``;
the handwritten frontend mirror lives in ``apps/web/src/lib/api/growthHttp.ts``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

GrowthStage = Literal["rising", "stalling", "plateau", "insufficient"]


# ── GET /growth/history ────────────────────────────────────────────────────

class GrowthHistoryItem(BaseModel):
    """One per-session growth snapshot (writers persist validated ``list[str]``)."""

    id: int
    session_id: int
    weak_skills: list[str]
    training_plan: list[str]
    created_at: datetime


# ── GET /growth/system-insights ────────────────────────────────────────────

class GrowthProbeItem(BaseModel):
    """One recent weak-point probe (entries come from a local JSON file)."""

    company: str | None = None
    role: str | None = None
    point: str | None = None
    session_id: int | None = None
    source: str | None = None


class SystemGrowthInsights(BaseModel):
    """Cross-interview system aggregates plus environment flags for the growth page.

    ``extra="allow"``: the read path is fail-open and serves whatever snapshot
    survived normalization, so unknown keys pass through instead of failing.
    """

    model_config = ConfigDict(extra="allow")

    company_session_counts: dict[str, int] = {}
    role_session_counts: dict[str, int] = {}
    avg_scores_by_company: dict[str, float | None] = {}
    followup_category_hits: dict[str, int] = {}
    tool_call_counts: dict[str, int] = {}
    recent_probes: list[GrowthProbeItem] = []
    updated_at: str | None = None
    github_token_configured: bool = False
    interview_tools_enabled: bool = False


# ── GET /growth/aggregated ─────────────────────────────────────────────────

class GrowthAggregatedStats(BaseModel):
    """Rule-based growth-page stats from ``GrowthAgent.analyze``."""

    top_weaknesses: list[tuple[str, int]]
    total_interviews: int
    total_plans: int
    total_weak_skills: int
    growth_pct: int
    growth_level: str


# ── GET /growth/insight ────────────────────────────────────────────────────

class GrowthWeaknessPattern(BaseModel):

    skill: str
    count: int
    trend: str
    advice: str


class GrowthTrainingFocus(BaseModel):

    area: str
    based_on: str
    actions: list[str]


class GrowthInsightPayload(BaseModel):
    """LLM insight body (``normalize_growth_insight`` + row metadata)."""

    headline: str
    trajectory: str
    trajectory_stage: GrowthStage
    recurring_weaknesses: list[GrowthWeaknessPattern]
    improving_areas: list[str]
    resume_gap_insights: list[str]
    training_plan: list[GrowthTrainingFocus]
    generated_at: str | None = None
    session_count: int = 0
    locale: str = "zh-CN"


class GrowthInsightEnvelope(BaseModel):

    insight: GrowthInsightPayload | None
    status: Literal["ready", "generating", "empty"]


# ── POST /growth/insight/refresh ───────────────────────────────────────────

class GrowthInsightRefreshResponse(BaseModel):

    scheduled: bool
    status: Literal["generating", "ready"]


__all__ = [
    "GrowthAggregatedStats",
    "GrowthHistoryItem",
    "GrowthInsightEnvelope",
    "GrowthInsightPayload",
    "GrowthInsightRefreshResponse",
    "GrowthProbeItem",
    "GrowthStage",
    "GrowthTrainingFocus",
    "GrowthWeaknessPattern",
    "SystemGrowthInsights",
]
