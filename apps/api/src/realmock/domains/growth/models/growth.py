"""Growth record ORM (candidate weak skills + training plan)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from realmock.platform.database import SessionsBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GrowthRecord(SessionsBase):
    """Per-session candidate growth snapshot."""

    __tablename__ = "growth_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, default=1)
    session_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    weak_skills: Mapped[str] = mapped_column(Text, default="[]")
    common_mistakes: Mapped[str] = mapped_column(Text, default="[]")
    training_plan: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
