"""Current-limiting bucket shared between processes (sessions.db, multi-worker deployment)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from realmock.platform.database import SessionsBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RateLimitBucket(SessionsBase):
    """Sliding-window timestamp JSON: ``{key}:{client_id}`` -> ``[epoch_s, ...]``.

    Timestamps are wall-clock epoch seconds (``time.time()``): the DB backend must read them
    across processes and full machine restarts, while a monotonic clock has no cross-restart baseline.
    """

    __tablename__ = "rate_limit_buckets"

    bucket_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    timestamps_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
