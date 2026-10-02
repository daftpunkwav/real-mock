"""Interview session ORM (in-progress room state + ledger freeze flag)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from realmock.platform.database import SessionsBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InterviewSession(SessionsBase):
    """Persisted interview session row."""

    __tablename__ = "interview_sessions"

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
    # UI locale at creation ("zh-CN" / "en-US" ...); the flow planner uses it
    # as one signal when deciding the interview working language.
    ui_locale: Mapped[str] = mapped_column(String(10), default="")
    # Reference-answer depth ("outline" fast bullets / "full" agent-loop answer).
    reference_detail: Mapped[str] = mapped_column(String(10), default="outline")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    current_phase: Mapped[str] = mapped_column(String(50), default="identity_check")
    agent_state: Mapped[str] = mapped_column(Text, default="{}")
    messages: Mapped[str] = mapped_column(Text, default="[]")
    # Frozen flag as a first-class column: list/read paths must not parse a
    # JSON blob just to learn one boolean. The legacy monolithic ledger
    # column was migrated into interview_turns and dropped (see
    # realmock.domains.interview.ledger.migration); it is intentionally NOT
    # mapped here, and any pre-migration database is backfilled via raw SQL
    # before the column is dropped on boot.
    ledger_frozen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    report: Mapped[str] = mapped_column(Text, default="{}")
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    access_token: Mapped[str] = mapped_column(String(64), default="")
    ai_overrides: Mapped[str] = mapped_column(Text, default="{}")
    # Multi-round lineage: NULL = standalone interview.
    process_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    round_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Agent-announced verdict ("passed" / "failed"); NULL = not judged yet.
    result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Agent-planned interview flow (InterviewPlan JSON) + generation status.
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_status: Mapped[str | None] = mapped_column(String(20), default="")
    # Target-company web-research digest (planning stage; empty when none).
    company_research: Mapped[str] = mapped_column(Text, default="")
    # Pre-interview GitHub evidence digest (seeded in the background right
    # after creation; the interviewer reads it instead of crawling repos live
    # while the candidate waits).
    github_evidence: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
