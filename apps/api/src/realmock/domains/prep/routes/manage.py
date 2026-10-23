"""Prep session management: delete, archive, link, token recovery, and purges.

Management operations (delete / archive / link / reissue / purge-empty /
purge-all) are owner-level: they require same-origin CSRF protection but NOT
the per-session capability token. Rationale: the session list is
unauthenticated single-user data, HttpOnly capability cookies are host-bound
and expirable, and requiring the token here permanently locks orphans (listed
but undeletable, A0401). History surgery (truncate / compact / summary) lives
in ``history.py`` under the same rule.

Content-reading operations (GET messages / POST message+stream / fork source)
still require the capability token.
"""

from __future__ import annotations

import logging

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from realmock.domains.prep.models import PrepSession, commit_session, utcnow
from realmock.domains.prep.schemas import PrepArchiveRequest, PrepLinkRequest, PrepPurgeAllRequest
from realmock.domains.prep.services import apply_session_link
from realmock.domains.prep.services.maintenance import (
    purge_empty_sessions as purge_empty_session_rows,
)
from realmock.domains.prep.services.session_guard import load_prep_session
from realmock.domains.prep.services.turn_lock import session_turn_lock
from realmock.platform.core.constants import SessionStatus
from realmock.platform.core.errors import raise_error
from realmock.platform.core.session_auth import (
    cookie_should_be_secure,
    new_access_token,
    set_session_cookie,
)
from realmock.platform.core.session_auth.csrf import assert_csrf_if_cookie_only
from realmock.platform.database import get_sessions_db

logger = logging.getLogger(__name__)


async def delete_prep_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Delete a session and its history permanently."""
    assert_csrf_if_cookie_only(request, used_header=False)
    session = load_prep_session(db, session_id)
    db.delete(session)
    commit_session(db)
    return {"deleted": session_id}


async def purge_empty_sessions(
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Delete sessions that never accumulated user/assistant content."""
    assert_csrf_if_cookie_only(request, used_header=False)
    deleted = purge_empty_session_rows(db)
    return {"deleted": deleted}


async def purge_all_sessions(
    request: Request,
    db: Session = Depends(get_sessions_db),
    body: PrepPurgeAllRequest | None = None,
):
    """Delete ALL coaching sessions permanently, with or without content."""
    assert_csrf_if_cookie_only(request, used_header=False)
    if body is None or body.confirm is not True:
        raise_error("A0001")
    rows = db.query(PrepSession).all()
    deleted = len(rows)
    for row in rows:
        db.delete(row)
    commit_session(db)
    logger.warning("Prep purge-all deleted=%s", deleted)
    return {"deleted": deleted}


async def archive_prep_session(
    session_id: int,
    body: PrepArchiveRequest,
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Archive (or restore) a session; archived sessions stay fully usable."""
    assert_csrf_if_cookie_only(request, used_header=False)
    session = load_prep_session(db, session_id)
    session.status = SessionStatus.ARCHIVED.value if body.archived else SessionStatus.ACTIVE.value
    session.updated_at = utcnow()
    commit_session(db)
    return {"id": session_id, "status": session.status}


async def reissue_prep_token(
    session_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_sessions_db),
):
    """Mint a fresh capability token for a listed session (owner-level recovery)."""
    assert_csrf_if_cookie_only(request, used_header=False)
    session = load_prep_session(db, session_id)
    session.access_token = new_access_token()
    session.updated_at = utcnow()
    commit_session(db)
    set_session_cookie(
        response,
        scope="prep",
        session_id=session.id,
        token=session.access_token,
        secure=cookie_should_be_secure(request),
    )
    return {"id": session.id}


async def link_prep_session(
    session_id: int,
    body: PrepLinkRequest,
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Link another session's summary + recent turns into this session's context."""
    assert_csrf_if_cookie_only(request, used_header=False)
    # Linking rewrites stored history (the linked-context system block):
    # serialize with chat turns on the session lock, loading the session
    # inside it — a stale snapshot would clobber a concurrent turn.
    async with session_turn_lock(session_id):
        return await _run_link(session_id, db, body)


async def _run_link(
    session_id: int,
    db: Session,
    body: PrepLinkRequest,
):
    """Link body, executed under the session turn lock."""
    session = load_prep_session(db, session_id)
    target = apply_session_link(session, db, body.linked_session_id)
    return {"id": session_id, "linked_session_id": target}


__all__ = [
    "archive_prep_session",
    "delete_prep_session",
    "link_prep_session",
    "purge_all_sessions",
    "purge_empty_sessions",
    "reissue_prep_token",
]
