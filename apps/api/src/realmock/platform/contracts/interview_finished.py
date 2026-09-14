"""Outbound DTO: interview domain signals a finished (frozen) session.

Records (and other consumers) subscribe via lifecycle hooks; they must not
import interview implementation packages.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InterviewFinishedPayload(BaseModel):
    """Payload emitted when an interview session finishes and ledger freezes."""

    session_id: int
    profile_id: int = 1
    resume_id: int | None = None
    role: str = ""
    level: str = ""
    company: str = ""
    workflow_type: str = "technical"
    personality: str = "professional"
    strictness: int = 3
    interview_style: str = "deep_dive"
    started_at: datetime | str | None = None
    ended_at: datetime | str | None = None
    ledger: dict[str, Any] = Field(default_factory=dict)
    overall_score: int | None = None
    messages_count: int | None = None
    # Multi-round lineage (None = standalone session)
    process_id: int | None = None
    round_no: int | None = None
    result: str | None = None


__all__ = ["InterviewFinishedPayload"]
