"""Interview session CRUD: resume picker, create/list/get, message list, and response views.

These handlers are mounted on the main ``interview`` router (see assembly in ``interview.py``); this module
has no router prefix and defines only undecorated handlers for the main file to include.
"""

from __future__ import annotations

import json

from fastapi import BackgroundTasks, Depends, Request, Response
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from realmock.platform.core.constants import SessionStatus
from realmock.platform.core.errors import raise_error
from realmock.platform.core.session_auth import (
    assert_session_token,
    cookie_should_be_secure,
    extract_token,
    new_access_token,
    set_session_cookie,
)
from realmock.platform.database import get_api_db, get_sessions_db
from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.schemas import (
    ChatMessage,
    InterviewConfig,
    InterviewSessionResponse,
)
from realmock.domains.interview.process.planning.planner import generate_plan_for_session
from realmock.domains.interview.process.planning.plan_schema import (
    parse_plan,
    plan_step_views,
)
from realmock.platform.services.resume_picker import list_resume_picker_items


# Strongly typed ChatMessage list verification (defense storage layer historical dirty data)
_CHAT_MSG_ADAPTER: TypeAdapter[list[ChatMessage]] = TypeAdapter(list[ChatMessage])


def list_resume_picker(db: Session = Depends(get_api_db)):
    """Configure the resume summary for drop-down on the page; do not return the analysis text and in-depth evaluation."""
    return list_resume_picker_items(db)


def create_session(
    config: InterviewConfig,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_sessions_db),
):
    """Create a PENDING session, issue its capability token, and plan the flow.

    The flow planner runs in the background; the opening turn waits for it
    (bounded) and degrades to the static workflow on failure. The token is
    issued via HttpOnly cookie only, never in the response body.
    """
    token = new_access_token()
    session = InterviewSession(
        role=config.role,
        level=config.level,
        company=config.company,
        workflow_type=config.workflow_type,
        personality=config.personality,
        strictness=config.strictness,
        interview_style=config.interview_style,
        resume_id=config.resume_id,
        avatar_id=config.avatar_id,
        scene_id=config.scene_id,
        ui_locale=(config.ui_locale or "")[:10],
        reference_detail=config.reference_detail or "outline",
        status=SessionStatus.PENDING.value,
        current_phase="identity_check",
        access_token=token,
        ai_overrides=(
            json.dumps(config.ai_overrides.model_dump(exclude_none=True), ensure_ascii=False)
            if config.ai_overrides
            else "{}"
        ),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    # Plan the interview flow in the background; the opening turn waits (bounded).
    background_tasks.add_task(generate_plan_for_session, session.id)
    set_session_cookie(
        response,
        scope="iv",
        session_id=session.id,
        token=token,
        secure=cookie_should_be_secure(request),
    )
    # The token is only issued via HttpOnly Cookie, and the response body is no longer returned.
    return to_session_response(session, include_token=False)


def list_sessions(db: Session = Depends(get_sessions_db)):
    """History list: Only metadata is returned, excluding access_token (anti-enumeration theft capability token)."""
    sessions = db.query(InterviewSession).order_by(InterviewSession.created_at.desc()).all()
    return [to_session_response(s, include_token=False) for s in sessions]


def get_session(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_token),
):
    """Fetch one session view; 404 when missing, 403 on token mismatch."""
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)
    return to_session_response(session)


def get_messages(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_token),
):
    """Return the session transcript as validated chat messages.

    Dirty historical rows validate to an empty list rather than leaking
    internal errors to the client.
    """
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise_error("A2001")
    assert_session_token(session, access)
    raw = json.loads(session.messages or "[]")
    # Strong validation: only retain legal items that conform to the ChatMessage structure; bad data is reduced to an empty list
    try:
        validated = _CHAT_MSG_ADAPTER.validate_python(raw)
        return [m.model_dump(mode="json") for m in validated]
    except Exception:
        # Historical dirty data: Return empty to avoid exposing internal exceptions to the outside world
        return []


def to_session_response(
    session: InterviewSession, *, include_token: bool = False
) -> InterviewSessionResponse:
    """Project a session row onto the API response (plan steps included)."""
    plan = parse_plan(getattr(session, "plan", None))
    return InterviewSessionResponse(
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
        plan_status=getattr(session, "plan_status", None),
        plan=plan_step_views(plan),
        started_at=session.started_at,
        ended_at=session.ended_at,
        created_at=session.created_at,
        access_token=(session.access_token if include_token else None),
    )
