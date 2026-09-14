"""Multi-round interview process contracts (create / list / next-round)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from realmock.domains.interview.constants import MAX_INTERVIEW_ROUNDS
from realmock.domains.interview.schemas.session import AiOverrides


class ProcessCreateRequest(BaseModel):
    """Start a multi-round process; round-1 session is created together."""

    role: str = Field(..., max_length=100)
    level: str = Field(..., max_length=50)
    company: str = Field(..., max_length=100)
    workflow_type: Literal["technical", "hr", "management"] = "technical"
    personality: Literal["gentle", "professional", "pressure", "hr", "expert"] = "professional"
    strictness: int = Field(default=3, ge=1, le=10)
    interview_style: Literal["guided", "deep_dive", "continuous", "challenging"] = "deep_dive"
    resume_id: int | None = None
    avatar_id: str = Field(default="professional_male", max_length=50)
    scene_id: str = Field(default="meeting_room", max_length=50)
    max_rounds: int = Field(default=MAX_INTERVIEW_ROUNDS, ge=1, le=MAX_INTERVIEW_ROUNDS)
    ai_overrides: AiOverrides | None = None


class ProcessRoundItem(BaseModel):
    """One round inside a process (session projection)."""

    session_id: int
    round_no: int
    status: str
    result: str | None = None
    overall_score: int | None = None
    created_at: datetime | None = None


class ProcessRoundPlanItem(BaseModel):
    """One planned round of the realistic chain (kind drives i18n labels)."""

    round_no: int
    kind: str
    workflow_type: str
    label: str
    focus: str
    # HR-planned pass bar (candidate-visible); empty on the static chain.
    pass_criteria: str = ""


class InterviewProcessResponse(BaseModel):
    """Process view with round lineage and next-round eligibility."""

    id: int
    role: str
    level: str
    company: str
    workflow_type: str
    max_rounds: int
    current_round: int
    status: str
    next_round_eligible: bool = False
    next_round_no: int | None = None
    rounds: list[ProcessRoundItem] = Field(default_factory=list)
    round_plan: list[ProcessRoundPlanItem] = Field(default_factory=list)
    created_at: datetime | None = None


class ProcessCreatedResponse(BaseModel):
    """Process + first session created together."""

    process: InterviewProcessResponse
    session_id: int
