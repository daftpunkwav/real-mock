"""Company question-style brief cache (one row per company/role/level/type+language)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from realmock.platform.database import SessionsBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompanyBrief(SessionsBase):
    """Cached interview-style brief for one company / role / level / interview type.

    Generated once by a bounded web-research agent and reused by the setup
    preview; clearing the cache (settings page) forces regeneration on the
    next request. ``company_key`` folds in role, level, interview type and the
    UI language, so each setup combination keeps its own brief.
    """

    __tablename__ = "company_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_key: Mapped[str] = mapped_column(String(140), unique=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String(120), default="")
    lang: Mapped[str] = mapped_column(String(10), default="")
    style: Mapped[str] = mapped_column(Text, default="")
    focus_areas: Mapped[str] = mapped_column(Text, default="[]")  # JSON string list
    process: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
