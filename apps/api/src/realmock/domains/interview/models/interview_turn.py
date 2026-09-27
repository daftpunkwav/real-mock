"""Per-turn interview ledger rows (replaces the monolithic ``ledger`` TEXT blob).

Interview is the sole writer. Each turn is one row so appends are O(1)
INSERTs instead of a full-blob read-modify-write, and turn ids come from an
explicit per-session sequence rather than being derived from the row count
(which silently produced duplicates whenever turns were reset).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from realmock.platform.database import SessionsBase


class InterviewTurn(SessionsBase):
    """One interview ledger turn (single source of truth for the transcript)."""

    __tablename__ = "interview_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # Human-facing turn id (``t-0001``, …); allocated from ``seq``.
    turn_id: Mapped[str] = mapped_column(String(16), nullable=False)
    # Explicit per-session append sequence — replaces len(turns)+1 derivation.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # Single-turn ledger document JSON (the former ``turns[i]`` dict).
    turn: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("session_id", "turn_id", name="uq_interview_turns_session_turn"),
        Index("ix_interview_turns_session_seq", "session_id", "seq"),
    )


__all__ = ["InterviewTurn"]
