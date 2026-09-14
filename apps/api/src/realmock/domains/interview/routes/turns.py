"""Interview turns: start / message / finish and Runner event-stream consumption.

Handlers mount on the ``interview`` router. ``start_interview`` /
``send_message`` source must retain ``InterviewRunner`` /
``phases_remaining()`` tokens (session-repair tests use ``inspect.getsource``).
Finish paths freeze ledger via finish_lifecycle; report generation is owned
by the records domain (async after notify).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.orm import Session

from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.schemas import (
    ChatMessage,
    FinishInterviewResponse,
    InterviewMessageRequest,
    InterviewMessageResponse,
)
from realmock.domains.interview.agents import (
    InterviewRunner,
    InterviewSessionState,
    run_finish_lifecycle,
    session_llm,
)
from realmock.domains.interview.agents.events import EventKind
from realmock.platform.core.constants import SessionStatus
from realmock.platform.core.errors import ApiBusinessError, raise_error
from realmock.platform.core.session_auth import assert_session_token, extract_token
from realmock.platform.database import get_sessions_db

logger = logging.getLogger(__name__)


async def _collect_turn_result(stream) -> tuple[str, bool]:
    """Consume Runner event stream; return (final text, is_complete).

    Runner carries business codes on StreamEvent.error_code (A2002 / C0001).
    REST uses the same codes as WS; details stay in logs only.
    """
    content = ""
    is_complete = False
    error_code: str = ""
    error_message: str = ""
    async for event in stream:
        if event.kind == EventKind.TOKEN:
            content += event.token
        elif event.kind == EventKind.TURN_COMPLETE:
            content = event.content
            is_complete = bool(event.is_complete)
        elif event.kind == EventKind.ERROR:
            error_code = event.error_code or "C0001"
            error_message = event.error or "Interview execution failed"
    if error_code:
        logger.warning("Runner returns error: code=%s msg=%s", error_code, error_message)
        from realmock.platform.core.errors import get_spec

        spec = get_spec(error_code)
        raise ApiBusinessError(
            spec,
            message=spec.message,
        ) from None
    return content, is_complete


async def start_interview(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_token),
):
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)
    if session.status not in (SessionStatus.PENDING.value, SessionStatus.ACTIVE.value):
        raise_error("A2002")

    llm = session_llm(db, session)
    if not llm.api_key:
        raise_error("A0006")

    agent = InterviewSessionState(session, llm)
    runner = InterviewRunner(session, llm, agent)
    opening, _ = await _collect_turn_result(runner.stream_opening(db))

    return {
        "session_id": session_id,
        "message": ChatMessage(role="assistant", content=opening, timestamp=datetime.now(timezone.utc)),
        "current_phase": session.current_phase,
    }


async def send_message(
    session_id: int,
    body: InterviewMessageRequest,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_token),
):
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)
    if session.status == SessionStatus.COMPLETED.value:
        raise_error("A2002")

    llm = session_llm(db, session)
    if not llm.api_key:
        raise_error("A0006")

    agent = InterviewSessionState(session, llm)
    runner = InterviewRunner(session, llm, agent)
    reply, is_complete = await _collect_turn_result(
        runner.stream_turn(
            body.content,
            db,
            face=body.face_analysis,
            image_b64=body.image_base64,
        )
    )

    # When is_complete, runner_turn already ran finish_lifecycle (freeze+notify).
    # Do not double-notify here — ingest CAS is a backstop, not a substitute.

    return InterviewMessageResponse(
        session_id=session_id,
        message=ChatMessage(role="assistant", content=reply, timestamp=datetime.now(timezone.utc)),
        current_phase=session.current_phase,
        is_complete=is_complete,
        phases_remaining=list(agent.phases_remaining()) if not is_complete else [],
    )


async def finish_interview(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_token),
) -> FinishInterviewResponse:
    """End interview early: freeze ledger and notify (report is async via records)."""
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)
    if session.status == SessionStatus.COMPLETED.value:
        return FinishInterviewResponse(
            session_id=session_id,
            status="already_completed",
            overall_score=session.overall_score,
        )

    try:
        run_finish_lifecycle(db, session, mark_completed=True)
    except Exception:
        logger.exception("finish_lifecycle failed sid=%s", session_id)
        raise
    return FinishInterviewResponse(
        session_id=session_id,
        status=SessionStatus.COMPLETED.value,
        overall_score=session.overall_score,
    )
