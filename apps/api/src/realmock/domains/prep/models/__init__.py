"""Prep persistent models: coaching sessions and long-term memories.

Tables live in sessions.db (single-user app: no owner column). Time helpers
are public on purpose: routes, services, and agents share one clock.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from realmock.platform.database import SessionsBase


def utcnow() -> datetime:
    """Current UTC time shared by all prep persistence paths."""
    return datetime.now(timezone.utc)


# Backward-compatible alias: older imports use the private name.
_utcnow = utcnow


class PrepSession(SessionsBase):
    """Interview preparation coaching sessions."""

    __tablename__ = "prep_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_role: Mapped[str] = mapped_column(String(100), default="")
    target_company: Mapped[str] = mapped_column(String(100), default="")
    messages: Mapped[str] = mapped_column(Text, default="[]")
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    # Accumulation of real tokens returned by the supplier (when missing, migration will be filled in); cached is the hit input cache part
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # Matches prep_sessions.status in prep/column_migrations.py SESSIONS_MIGRATIONS; the startup migration adds the column if it is missing
    status: Mapped[str] = mapped_column(String(20), default="active")
    # Capability token: issued when created, message/history must be verified
    access_token: Mapped[str] = mapped_column(String(64), default="")
    # Linked session: its summary + recent turns are injected into this session's
    # context so the coach knows the linked conversation (single level, no chains).
    linked_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # The time when the latest message was dropped into the database (the conversation list is sorted by active); if it is missing, it will be filled in when migration is started.
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PrepMemory(SessionsBase):
    """Long-term prep memories: user-rated turns, emphasized facts, and agent notes.

    Index/detail split (claudecode-style): list views carry only id/summary/tags;
    full user_input/agent_output load on demand via the detail path. Summaries and
    tags are maintained by the LLM (one line, topic-organized, no duplicates).
    """

    __tablename__ = "prep_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Origin session, if recorded from a chat turn (nullable: agent notes may be session-free).
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # One-line index maintained by the LLM (≤200 chars).
    summary: Mapped[str] = mapped_column(String(200), default="")
    user_input: Mapped[str] = mapped_column(Text, default="")
    agent_output: Mapped[str] = mapped_column(Text, default="")
    # 1–10 user rating, if the memory came from an explicit rating.
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Free-form user comment and selected reason chips (JSON list).
    comment: Mapped[str] = mapped_column(Text, default="")
    reasons: Mapped[str] = mapped_column(Text, default="[]")
    # Topic tags maintained by the LLM (JSON list).
    tags: Mapped[str] = mapped_column(Text, default="[]")
    # How the memory was recorded: user_rating | user_emphasis | agent_note.
    origin: Mapped[str] = mapped_column(String(30), default="agent_note")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


__all__ = ["PrepMemory", "PrepSession", "utcnow"]
