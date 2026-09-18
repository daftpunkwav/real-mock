"""Interview-domain adapters for session catalog (read) and score projection (write).

Registered together from the composition root so records can project debrief
scores without importing interview ORM.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.interview.ledger.store import is_frozen, load_ledger
from realmock.domains.interview.models import InterviewSession
from realmock.platform.contracts.session_catalog import (
    SessionCatalogItem,
    SessionSnapshot,
    register_session_catalog,
)
from realmock.platform.contracts.session_score import register_session_score_projection

logger = logging.getLogger(__name__)


class InterviewSessionCatalog:
    """Read-only catalog backed by interview_sessions."""

    def list_sessions(self, db: Session) -> list[SessionCatalogItem]:
        """Newest-first session metadata (no transcript payloads)."""
        rows = db.query(InterviewSession).order_by(InterviewSession.created_at.desc()).all()
        return [self._to_item(s) for s in rows]

    def get_session(self, db: Session, session_id: int) -> SessionSnapshot | None:
        """One session snapshot; None when the id is unknown."""
        session = (
            db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
        )
        if session is None:
            return None
        return self._to_snapshot(session)

    def get_session_snapshot(self, db: Session, session_id: int) -> dict[str, Any] | None:
        """JSON-serializable snapshot dict; None when the id is unknown."""
        snap = self.get_session(db, session_id)
        if snap is None:
            return None
        return snap.model_dump(mode="json")

    def get_ledger(self, db: Session, session_id: int) -> dict[str, Any] | None:
        """Raw ledger document for a session; None when the id is unknown."""
        session = (
            db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
        )
        if session is None:
            return None
        return dict(load_ledger(session))

    def get_process_context(self, db: Session, process_id: int) -> str:
        """Render a process's prior-round memory for cross-domain consumers."""
        from realmock.domains.interview.models import InterviewProcess
        from realmock.domains.interview.protocols.process_memory import (
            load_memory,
            render_for_prompt,
        )

        process = (
            db.query(InterviewProcess).filter(InterviewProcess.id == process_id).first()
        )
        if process is None:
            return ""
        return render_for_prompt(load_memory(process.memory))

    @staticmethod
    def _messages_and_duration(session: InterviewSession) -> tuple[int, float | None]:
        try:
            messages = json.loads(session.messages or "[]")
            if not isinstance(messages, list):
                messages = []
        except (json.JSONDecodeError, TypeError):
            logger.warning("corrupt messages JSON sid=%s; count=0", session.id)
            messages = []

        duration_seconds: float | None = None
        started = session.started_at
        ended = session.ended_at
        if started is not None and ended is not None:
            try:
                duration_seconds = (ended - started).total_seconds()
            except TypeError:
                logger.debug("non-datetime bounds sid=%s; duration unknown", session.id)
                duration_seconds = None
        return len(messages), duration_seconds

    @classmethod
    def _to_item(cls, session: InterviewSession) -> SessionCatalogItem:
        return SessionCatalogItem(
            id=session.id,
            role=session.role,
            level=session.level,
            company=session.company,
            workflow_type=session.workflow_type,
            personality=session.personality,
            strictness=session.strictness,
            interview_style=session.interview_style,
            avatar_id=getattr(session, "avatar_id", None) or "professional_male",
            scene_id=getattr(session, "scene_id", None) or "meeting_room",
            status=session.status,
            current_phase=session.current_phase,
            overall_score=session.overall_score,
            process_id=getattr(session, "process_id", None),
            round_no=getattr(session, "round_no", None),
            result=getattr(session, "result", None),
            started_at=session.started_at,
            ended_at=session.ended_at,
            created_at=session.created_at,
            ledger_frozen=is_frozen(session),
        )

    @classmethod
    def _to_snapshot(cls, session: InterviewSession) -> SessionSnapshot:
        messages_count, duration_seconds = cls._messages_and_duration(session)
        ledger = dict(load_ledger(session))
        return SessionSnapshot(
            id=session.id,
            profile_id=int(getattr(session, "profile_id", 1) or 1),
            resume_id=getattr(session, "resume_id", None),
            role=session.role or "",
            level=session.level or "",
            company=session.company or "",
            workflow_type=session.workflow_type or "technical",
            personality=session.personality or "professional",
            strictness=int(session.strictness or 3),
            interview_style=session.interview_style or "deep_dive",
            status=session.status or "",
            current_phase=session.current_phase or "",
            overall_score=session.overall_score,
            access_token=getattr(session, "access_token", None) or "",
            process_id=getattr(session, "process_id", None),
            round_no=getattr(session, "round_no", None),
            result=getattr(session, "result", None),
            messages=getattr(session, "messages", None) or "[]",
            report=getattr(session, "report", None) or "{}",
            ledger=ledger,
            started_at=session.started_at,
            ended_at=session.ended_at,
            created_at=session.created_at,
            ledger_frozen=bool(ledger.get("frozen")),
            messages_count=messages_count,
            duration_seconds=duration_seconds,
        )


class InterviewSessionScoreProjection:
    """Write overall_score onto interview_sessions after records debrief."""

    def apply_overall_score(self, db: Session, session_id: int, score: int) -> None:
        session = (
            db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
        )
        if session is None:
            logger.warning("apply_overall_score: session missing sid=%s", session_id)
            return
        try:
            session.overall_score = int(score)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("apply_overall_score failed sid=%s", session_id)
            raise


def register_interview_session_catalog() -> InterviewSessionCatalog:
    """Register read catalog + score projection adapters on platform ports."""
    catalog = InterviewSessionCatalog()
    register_session_catalog(catalog)
    register_session_score_projection(InterviewSessionScoreProjection())
    return catalog


__all__ = [
    "InterviewSessionCatalog",
    "InterviewSessionScoreProjection",
    "register_interview_session_catalog",
]
