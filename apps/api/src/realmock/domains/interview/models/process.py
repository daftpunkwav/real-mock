"""Multi-round interview process ORM (round 1..5 lineage across sessions)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from realmock.platform.database import SessionsBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InterviewProcess(SessionsBase):
    """A candidate's multi-round interview pipeline; sessions hang off it via process_id."""

    __tablename__ = "interview_processes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, default=1)
    resume_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(50))
    company: Mapped[str] = mapped_column(String(100))
    workflow_type: Mapped[str] = mapped_column(String(50), default="technical")
    personality: Mapped[str] = mapped_column(String(50), default="professional")
    strictness: Mapped[int] = mapped_column(Integer, default=3)
    interview_style: Mapped[str] = mapped_column(String(50), default="deep_dive")
    avatar_id: Mapped[str] = mapped_column(String(50), default="professional_male")
    scene_id: Mapped[str] = mapped_column(String(50), default="meeting_room")
    # UI locale at process creation; round sessions inherit it for flow-language planning.
    ui_locale: Mapped[str] = mapped_column(String(10), default="")
    # Reference-answer depth for all rounds ("outline" / "full").
    reference_detail: Mapped[str] = mapped_column(String(10), default="outline")
    ai_overrides: Mapped[str] = mapped_column(Text, default="{}")
    max_rounds: Mapped[int] = mapped_column(Integer, default=5)
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="in_progress")
    # HR-planner round program (realmock.round_plan.v1 JSON document): the LLM
    # decides round count/kinds/pass criteria within the max_rounds budget.
    # Empty status = pending; "ready" | "failed" (failed degrades to the
    # static round_chain everywhere).
    round_plan: Mapped[str] = mapped_column(Text, default="{}")
    round_plan_status: Mapped[str] = mapped_column(String(20), default="")
    # Target-company web-research digest (planning stage; empty when none).
    company_research: Mapped[str] = mapped_column(Text, default="")
    # Long-term memory across rounds (realmock.process_memory.v1 JSON document).
    memory: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=_utcnow)
