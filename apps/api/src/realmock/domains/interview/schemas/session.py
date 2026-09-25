"""Mock interview sessions with round messaging contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from realmock.domains.interview.constants import DEFAULT_INTERVIEW_STYLE, DEFAULT_PERSONALITY
from realmock.platform.core.constants import MAX_CONFIG_STR_CHARS, MAX_USER_TEXT_CHARS


# Processor selection for mock interviews: thinking / voice input / voice output + thinking intensity.
class AiOverrides(BaseModel):

    chat_profile_id: int | None = None
    stt_profile_id: int | None = None
    tts_profile_id: int | None = None
    # Custom model-declared levels ride through verbatim; the default scale is
    # low/medium/high/max and anything else must be a declared model variant.
    reasoning_effort: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_\-]{0,32}$")


class InterviewConfig(BaseModel):
    role: str = Field(..., max_length=MAX_CONFIG_STR_CHARS)
    level: str = Field(..., max_length=MAX_CONFIG_STR_CHARS)
    company: str = Field(..., max_length=MAX_CONFIG_STR_CHARS)
    workflow_type: Literal["technical", "hr", "management"] = "technical"
    personality: Literal["gentle", "professional", "pressure", "hr", "expert"] = DEFAULT_PERSONALITY.value
    strictness: int = Field(default=3, ge=1, le=10)
    interview_style: Literal["guided", "deep_dive", "continuous", "challenging"] = DEFAULT_INTERVIEW_STYLE.value
    resume_id: int | None = None
    avatar_id: str = Field(default="professional_male", max_length=MAX_CONFIG_STR_CHARS)
    scene_id: str = Field(default="meeting_room", max_length=MAX_CONFIG_STR_CHARS)
    ai_overrides: "AiOverrides | None" = None
    # UI locale ("zh-CN" / "en-US" ...): one signal for the flow-language decision.
    ui_locale: str | None = Field(default=None, max_length=10)
    # Reference-answer depth: "outline" (fast single-shot bullets, default) or
    # "full" (multi-round agent loop with profile/resume/GitHub grounding).
    reference_detail: Literal["outline", "full"] = "outline"


# Light plan-step projection for room UI (flow spine).
class PlanStepView(BaseModel):

    id: str
    title: str


class InterviewSessionResponse(BaseModel):
    id: int
    role: str
    level: str
    company: str
    workflow_type: str
    personality: str
    strictness: int
    interview_style: str
    avatar_id: str = "professional_male"
    scene_id: str = "meeting_room"
    status: str
    current_phase: str
    overall_score: int | None = None
    process_id: int | None = None
    round_no: int | None = None
    result: str | None = None
    plan_status: str | None = None
    plan: list[PlanStepView] = []
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    access_token: str | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime | None = None


class InterviewMessageRequest(BaseModel):
    content: str = Field(..., max_length=MAX_USER_TEXT_CHARS)
    face_analysis: dict[str, Any] | None = None
    image_base64: str | None = Field(default=None, max_length=300_000)


class InterviewMessageResponse(BaseModel):
    session_id: int
    message: ChatMessage
    current_phase: str
    is_complete: bool = False
    phases_remaining: list[str] = Field(default_factory=list)


class FinishInterviewResponse(BaseModel):
    session_id: int
    status: str
    overall_score: int | None = None
