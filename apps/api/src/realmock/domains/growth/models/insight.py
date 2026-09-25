"""Growth insight ORM (LLM-generated cross-session growth analysis)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from realmock.platform.database import SessionsBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GrowthInsight(SessionsBase):
    """Latest LLM growth analysis (single row per profile, upserted)."""

    __tablename__ = "growth_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    locale: Mapped[str] = mapped_column(Text, default="zh-CN")
    session_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
