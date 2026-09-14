"""CRUD helpers for interview_reports status and JSON payload.

Handles pending/generating/ready/failed transitions with stale-generating reclaim
so a crashed debrief cannot pin a session forever.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.records.models.report import InterviewReportRow
from realmock.domains.records.schemas.report import DebriefReport

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_GENERATING = "generating"
STATUS_READY = "ready"
STATUS_FAILED = "failed"

# Skip ingest while generating unless the claim is older than this.
STALE_GENERATING_AFTER = timedelta(minutes=10)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_report_row(db: Session, session_id: int) -> InterviewReportRow | None:
    """Fetch report row by session_id."""
    return (
        db.query(InterviewReportRow)
        .filter(InterviewReportRow.session_id == session_id)
        .first()
    )


def is_stale_generating(row: InterviewReportRow) -> bool:
    """True when status=generating and updated_at is older than the reclaim window."""
    if row.status != STATUS_GENERATING:
        return False
    updated = _as_aware(row.updated_at)
    if updated is None:
        return True
    return (_utcnow() - updated) > STALE_GENERATING_AFTER


def reclaim_stale_generating(db: Session, row: InterviewReportRow) -> InterviewReportRow:
    """Reset a stale generating row to pending so debrief can be claimed again."""
    logger.warning(
        "reclaiming stale generating report sid=%s updated_at=%s",
        row.session_id,
        row.updated_at,
    )
    row.status = STATUS_PENDING
    row.error_message = "reclaimed: previous generation timed out"
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return row


def upsert_pending(db: Session, session_id: int) -> InterviewReportRow:
    """Ensure a report row exists; set pending unless ready or fresh generating.

    Stale ``generating`` rows are reclaimed to ``pending``.
    """
    row = get_report_row(db, session_id)
    if row is None:
        row = InterviewReportRow(
            session_id=session_id,
            status=STATUS_PENDING,
            payload="{}",
            model_meta="{}",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    if row.status == STATUS_READY:
        return row
    if row.status == STATUS_GENERATING:
        if is_stale_generating(row):
            return reclaim_stale_generating(db, row)
        return row
    row.status = STATUS_PENDING
    row.error_message = None
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return row


def mark_failed(db: Session, session_id: int, error_message: str) -> None:
    """Set status=failed with a truncated error message."""
    row = get_report_row(db, session_id)
    if row is None:
        return
    row.status = STATUS_FAILED
    row.error_message = (error_message or "")[:2000] or None
    row.updated_at = _utcnow()
    db.commit()


def persist_ready(
    db: Session,
    session_id: int,
    report: DebriefReport,
    *,
    model_meta: dict[str, Any] | None = None,
) -> InterviewReportRow | None:
    """Write ready payload + model_meta for a session report row."""
    row = get_report_row(db, session_id)
    if row is None:
        row = InterviewReportRow(session_id=session_id)
        db.add(row)
    row.status = STATUS_READY
    row.payload = report.model_dump_json()
    row.error_message = None
    row.model_meta = json.dumps(model_meta or {}, ensure_ascii=False)
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return row


def parse_payload(row: InterviewReportRow) -> DebriefReport | None:
    """Parse ready payload; return None on empty/invalid JSON."""
    raw = (row.payload or "").strip()
    if not raw or raw == "{}":
        return None
    try:
        return DebriefReport.model_validate_json(raw)
    except Exception:
        logger.debug(
            "report payload parse failed sid=%s", row.session_id, exc_info=True
        )
        return None


def reset_for_retry(db: Session, session_id: int) -> InterviewReportRow:
    """Re-queue failed/pending/stale-generating reports. Ready rows are unchanged."""
    row = get_report_row(db, session_id)
    if row is None:
        return upsert_pending(db, session_id)
    if row.status == STATUS_READY:
        return row
    if row.status == STATUS_GENERATING and not is_stale_generating(row):
        return row
    row.status = STATUS_PENDING
    row.error_message = None
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return row


__all__ = [
    "STATUS_FAILED",
    "STATUS_GENERATING",
    "STATUS_PENDING",
    "STATUS_READY",
    "STALE_GENERATING_AFTER",
    "get_report_row",
    "is_stale_generating",
    "mark_failed",
    "parse_payload",
    "persist_ready",
    "reclaim_stale_generating",
    "reset_for_retry",
    "upsert_pending",
]
