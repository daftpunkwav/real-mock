"""Persist GrowthRecord from ReportSummaryPayload (idempotent by session_id)."""

from __future__ import annotations

import json
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from realmock.domains.growth.models.growth import GrowthRecord
from realmock.platform.contracts.report_summary import ReportSummaryPayload

logger = logging.getLogger(__name__)


def persist_growth_from_summary(
    db: Session,
    payload: ReportSummaryPayload,
) -> tuple[GrowthRecord | None, bool]:
    """Insert GrowthRecord for ``payload.session_id`` if missing.

    Returns ``(row, created)``. Concurrent inserts hit the unique index and are
    treated as ``created=False``. Failures other than uniqueness are re-raised.
    """
    sid = int(payload.session_id)
    existing = (
        db.query(GrowthRecord)
        .filter(GrowthRecord.session_id == sid)
        .order_by(GrowthRecord.id.desc())
        .first()
    )
    if existing is not None:
        logger.info("growth persist skip sid=%s (already exists id=%s)", sid, existing.id)
        return existing, False

    weaknesses = list(payload.weaknesses or [])
    training = list(payload.training_plan or [])
    if payload.profile_id is None:
        logger.warning(
            "growth persist sid=%s missing profile_id; defaulting to 1", sid
        )
        profile_id = 1
    else:
        profile_id = int(payload.profile_id)

    growth = GrowthRecord(
        profile_id=profile_id,
        session_id=sid,
        weak_skills=json.dumps(weaknesses, ensure_ascii=False),
        common_mistakes=json.dumps(weaknesses[:3], ensure_ascii=False),
        training_plan=json.dumps(training, ensure_ascii=False),
    )
    try:
        db.add(growth)
        db.commit()
        db.refresh(growth)
    except IntegrityError:
        db.rollback()
        logger.info("growth persist race sid=%s; treating as already created", sid)
        existing = (
            db.query(GrowthRecord)
            .filter(GrowthRecord.session_id == sid)
            .order_by(GrowthRecord.id.desc())
            .first()
        )
        return existing, False
    except Exception:
        db.rollback()
        logger.exception("GrowthRecord persist failed sid=%s", sid)
        raise
    return growth, True


__all__ = ["persist_growth_from_summary"]
