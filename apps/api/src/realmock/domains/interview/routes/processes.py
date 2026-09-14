"""Multi-round interview process routes: create, list, detail, next round.

Handlers are thin: business rules live in
``services/process_service.py``; this module owns HTTP concerns (auth cookie,
rate limits are declared on the aggregating router).
"""

from __future__ import annotations

from fastapi import BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

from realmock.domains.interview.schemas.process import (
    ProcessCreateRequest,
    ProcessCreatedResponse,
)
from realmock.domains.interview.process.planning.planner import generate_plan_for_session
from realmock.domains.interview.process.process_service import (
    ProcessRoundError,
    create_next_round,
    create_process_with_first_round,
    get_process_detail,
    list_processes,
)
from realmock.platform.core.errors import raise_error
from realmock.platform.core.session_auth import (
    cookie_should_be_secure,
    new_access_token,
    set_session_cookie,
)
from realmock.platform.database import get_sessions_db
from realmock.domains.interview.routes.sessions import to_session_response


def _issue_session_cookie(
    session, request: Request, response: Response
) -> None:
    """Attach a fresh access token + HttpOnly cookie to a newly created session."""
    token = new_access_token()
    session.access_token = token
    set_session_cookie(
        response,
        scope="iv",
        session_id=session.id,
        token=token,
        secure=cookie_should_be_secure(request),
    )


def create_process(
    config: ProcessCreateRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_sessions_db),
):
    """Start a multi-round process together with its round-1 session."""
    process, session = create_process_with_first_round(db, config)
    _issue_session_cookie(session, request, response)
    background_tasks.add_task(generate_plan_for_session, session.id)
    detail = get_process_detail(db, process.id)
    return ProcessCreatedResponse(process=detail, session_id=session.id)


def list_process_routes(db: Session = Depends(get_sessions_db)):
    """List multi-round processes (newest first) with next-round eligibility."""
    return list_processes(db)


def get_process(
    process_id: int,
    db: Session = Depends(get_sessions_db),
):
    """One process with its round lineage."""
    return get_process_detail(db, process_id)


def create_round(
    process_id: int,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_sessions_db),
):
    """Create the next round session after a passed round."""
    try:
        session = create_next_round(db, process_id)
    except ProcessRoundError as e:
        raise_error(e.code)
    _issue_session_cookie(session, request, response)
    background_tasks.add_task(generate_plan_for_session, session.id)
    return to_session_response(session)


__all__ = [
    "create_process",
    "create_round",
    "get_process",
    "list_process_routes",
]
