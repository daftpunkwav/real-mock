"""History list response schemas for records routes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


# Session metadata for the history page (no access token).
class SessionHistoryItem(BaseModel):

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
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime | None = None
    ledger_frozen: bool = False
