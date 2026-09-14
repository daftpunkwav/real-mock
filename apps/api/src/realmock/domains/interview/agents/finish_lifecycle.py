"""Finish-path lifecycle: freeze ledger and notify platform subscribers.

Report / debrief generation is owned by the records domain after
``notify_interview_finished``; this module only freezes and notifies.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.interview.ledger.store import freeze_ledger, is_frozen, load_ledger
from realmock.platform.contracts.interview_finished import InterviewFinishedPayload
from realmock.platform.contracts.lifecycle_hooks import notify_interview_finished

logger = logging.getLogger(__name__)


def run_finish_lifecycle(
    db: Session,
    session: Any,
    *,
    mark_completed: bool = True,
) -> dict[str, Any]:
    """Freeze ledger, optionally mark session completed, notify subscribers.

    Returns the frozen ledger snapshot. Notification failures never raise.
    """
    if mark_completed and getattr(session, "status", None) != "completed":
        from datetime import datetime, timezone

        session.status = "completed"
        if getattr(session, "ended_at", None) is None:
            session.ended_at = datetime.now(timezone.utc)
        db.commit()

    if is_frozen(session):
        ledger = dict(load_ledger(session))
        logger.info("ledger already frozen sid=%s; notify only", getattr(session, "id", None))
    else:
        ledger = freeze_ledger(db, session)

    # Fold the finished round into its process memory (no-op for standalone sessions).
    from realmock.domains.interview.services.process_service import record_round_finished

    record_round_finished(db, session)

    messages_count: int | None = None
    try:
        messages = json.loads(getattr(session, "messages", None) or "[]")
        if isinstance(messages, list):
            messages_count = len(messages)
    except (json.JSONDecodeError, TypeError):
        messages_count = None

    payload = InterviewFinishedPayload(
        session_id=int(session.id),
        profile_id=int(getattr(session, "profile_id", 0) or 0),
        resume_id=getattr(session, "resume_id", None),
        role=str(getattr(session, "role", "") or ""),
        level=str(getattr(session, "level", "") or ""),
        company=str(getattr(session, "company", "") or ""),
        workflow_type=str(getattr(session, "workflow_type", "") or ""),
        personality=str(getattr(session, "personality", "") or "professional"),
        strictness=int(getattr(session, "strictness", 3) or 3),
        interview_style=str(getattr(session, "interview_style", "") or "deep_dive"),
        started_at=getattr(session, "started_at", None),
        ended_at=getattr(session, "ended_at", None),
        ledger=ledger,
        overall_score=getattr(session, "overall_score", None),
        messages_count=messages_count,
        process_id=getattr(session, "process_id", None),
        round_no=getattr(session, "round_no", None),
        result=getattr(session, "result", None),
    )
    notify_interview_finished(payload)
    return ledger


__all__ = ["run_finish_lifecycle"]
