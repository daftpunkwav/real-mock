"""Idempotent ingest of InterviewFinished payloads into records debrief."""

from __future__ import annotations

import logging
from datetime import datetime

from realmock.domains.records.services.debrief_runner import run_debrief_for_session
from realmock.domains.records.services.report_store import (
    STATUS_GENERATING,
    STATUS_READY,
    upsert_pending,
)
from realmock.platform.contracts.interview_finished import InterviewFinishedPayload
from realmock.platform.contracts.lifecycle_hooks import set_on_interview_finished
from realmock.platform.database import sessions_db_session

logger = logging.getLogger(__name__)


def _coerce_ended_at(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def handle_interview_finished(payload: InterviewFinishedPayload) -> None:
    """Queue/run debrief for a finished interview.

    Idempotent: skips when report is already ready or generating.
    Uses owned short DB sessions inside the runner so LLM does not pin SQLite.
    Failures are logged; this handler must not crash the finish path.
    """
    sid = int(payload.session_id)
    try:
        with sessions_db_session() as db:
            row = upsert_pending(db, sid)
            if row.status in (STATUS_READY, STATUS_GENERATING):
                logger.info("records ingest skip sid=%s status=%s", sid, row.status)
                return

        await run_debrief_for_session(
            None,
            None,
            sid,
            ledger=payload.ledger or {},
            role=payload.role,
            level=payload.level,
            company=payload.company,
            workflow_type=payload.workflow_type,
            strictness=payload.strictness,
            interview_style=payload.interview_style,
            ended_at=_coerce_ended_at(payload.ended_at),
        )
    except Exception:
        logger.exception("records ingest failed sid=%s (finish path unaffected)", sid)


def register_records_lifecycle_handlers() -> None:
    """Wire records ingest into the platform interview-finished hook."""
    set_on_interview_finished(handle_interview_finished)
