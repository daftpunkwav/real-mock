"""Prep session creation: issue capability tokens and deliver cookies."""

from __future__ import annotations

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from realmock.domains.prep.models import PrepSession
from realmock.domains.prep.schemas import PrepCreateRequest, PrepSessionCreateResponse
from realmock.platform.core.constants import SessionStatus
from realmock.platform.core.session_auth import (
    cookie_should_be_secure,
    new_access_token,
    set_session_cookie,
)
from realmock.platform.database import get_sessions_db


async def create_prep_session(
    body: PrepCreateRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_sessions_db),
):
    token = new_access_token()
    # The status column is guaranteed by model + migrate; active is explicitly written during construction
    kwargs: dict = {
        "resume_id": body.resume_id,
        "target_role": body.target_role,
        "target_company": body.target_company,
        "access_token": token,
    }
    # status always present; guard kept for downgrade rollback
    if hasattr(PrepSession, "status"):
        kwargs["status"] = SessionStatus.ACTIVE.value
    session = PrepSession(**kwargs)
    db.add(session)
    db.commit()
    db.refresh(session)
    set_session_cookie(
        response,
        scope="prep",
        session_id=session.id,
        token=token,
        secure=cookie_should_be_secure(request),
    )
    return PrepSessionCreateResponse(id=session.id)
