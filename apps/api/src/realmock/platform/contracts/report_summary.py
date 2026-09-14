"""Outbound DTO: records domain publishes a distilled report summary.

Growth consumes this only — never ledger transcripts or raw tool results.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReportSummaryPayload(BaseModel):
    """Distilled report fields safe for growth / cross-session learning."""

    session_id: int
    profile_id: int | None = None
    overall_score: int | None = None
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    weaknesses: list[str] = Field(default_factory=list)
    training_plan: list[str] = Field(default_factory=list)
    turn_note_digest: list[str] = Field(default_factory=list)
    company: str | None = None
    role: str | None = None
    ended_at: datetime | str | None = None


__all__ = ["ReportSummaryPayload"]
