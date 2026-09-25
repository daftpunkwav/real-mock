"""Persistence for the latest growth insight (single row per profile)."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from realmock.domains.growth.models.insight import GrowthInsight

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_ID = 1


def get_latest_insight(db: Session, *, profile_id: int = DEFAULT_PROFILE_ID) -> GrowthInsight | None:
    """Latest insight row for the profile, or None."""
    try:
        return (
            db.query(GrowthInsight)
            .filter(GrowthInsight.profile_id == profile_id)
            .order_by(GrowthInsight.updated_at.desc(), GrowthInsight.id.desc())
            .first()
        )
    except OperationalError:
        db.rollback()
        return None


def upsert_insight(
    db: Session,
    payload: dict[str, Any],
    *,
    locale: str,
    session_count: int,
    profile_id: int = DEFAULT_PROFILE_ID,
) -> GrowthInsight:
    """Insert or replace the profile's single insight row."""
    row = get_latest_insight(db, profile_id=profile_id)
    if row is None:
        row = GrowthInsight(profile_id=profile_id)
        db.add(row)
    row.payload = json.dumps(payload, ensure_ascii=False)
    row.locale = locale
    row.session_count = int(session_count)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning("growth insight upsert raced; retrying as update", exc_info=True)
        row = get_latest_insight(db, profile_id=profile_id)
        if row is None:
            raise
        row.payload = json.dumps(payload, ensure_ascii=False)
        row.locale = locale
        row.session_count = int(session_count)
        db.commit()
    db.refresh(row)
    return row


def insight_response(row: GrowthInsight | None) -> dict[str, Any]:
    """HTTP-shaped insight payload (None row -> {"insight": None})."""
    if row is None:
        return {"insight": None}
    try:
        payload = json.loads(row.payload or "{}")
    except (json.JSONDecodeError, TypeError):
        logger.warning("growth insight payload corrupted id=%s", row.id)
        payload = {}
    return {
        "insight": {
            **payload,
            "generated_at": row.updated_at.isoformat() if row.updated_at else None,
            "session_count": int(row.session_count or 0),
            "locale": row.locale or "zh-CN",
        }
    }


__all__ = ["get_latest_insight", "insight_response", "upsert_insight"]
