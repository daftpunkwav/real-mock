"""Interview report ORM row (records domain ownership)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from realmock.platform.database import SessionsBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InterviewReportRow(SessionsBase):
    """Persisted debrief report for one interview session."""

    __tablename__ = "interview_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    payload: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_meta: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )
