"""Legacy fallback: read old interview_sessions.report via session catalog."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.records.schemas.report import DebriefReport, ReportResponse
from realmock.platform.contracts.session_catalog import (
    get_session_catalog,
    snapshot_from_catalog_dict,
)

logger = logging.getLogger(__name__)


def try_legacy_report(db: Session, session_id: int) -> ReportResponse | None:
    """If catalog snapshot has a legacy session.report JSON, adapt to ReportResponse.

    Does not create an interview_reports row. Returns None when absent/invalid.
    """
    catalog = get_session_catalog()
    raw = catalog.get_session_snapshot(db, session_id)
    if raw is None:
        return None
    snap = snapshot_from_catalog_dict(raw)
    report_raw = (snap.report or "").strip()
    if not report_raw or report_raw in ("{}", '{"_generating":true}'):
        return None
    try:
        data: dict[str, Any] = json.loads(report_raw)
        report = DebriefReport.model_validate(data)
    except Exception:
        logger.debug("legacy report parse failed sid=%s", session_id, exc_info=True)
        return None
    ledger = snap.ledger
    if ledger is None:
        ledger = catalog.get_ledger(db, session_id)
    messages_count = snap.messages_count
    if not messages_count:
        try:
            messages = json.loads(snap.messages or "[]")
            messages_count = sum(
                1
                for m in messages
                if isinstance(m, dict) and m.get("role") in ("user", "assistant")
            )
        except Exception:
            messages_count = 0
    duration = None
    if snap.duration_seconds is not None:
        duration = round(float(snap.duration_seconds) / 60, 1)
    elif snap.started_at and snap.ended_at:
        duration = round((snap.ended_at - snap.started_at).total_seconds() / 60, 1)
    return ReportResponse(
        session_id=session_id,
        report=report,
        messages_count=messages_count,
        duration_minutes=duration,
        status="ready",
        ledger=ledger,
    )
