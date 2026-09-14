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

import json
import logging

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from realmock.domains.prep.models import PrepSession
from realmock.domains.prep.models import commit_session, utcnow
from realmock.domains.prep.services import LINKED_BLOCK_MARKER, format_linked_session
from realmock.domains.prep.schemas import PrepArchiveRequest, PrepLinkRequest, PrepPurgeAllRequest
from realmock.platform.core.constants import SessionStatus
from realmock.platform.core.errors import raise_error
from realmock.platform.core.security import redact_api_key
from realmock.platform.core.session_auth import (
    cookie_should_be_secure,
    new_access_token,
    set_session_cookie,
)
from realmock.platform.core.session_auth.csrf import assert_csrf_if_cookie_only
from realmock.platform.database import get_sessions_db

logger = logging.getLogger(__name__)


def _require_existing_session(session_id: int, db: Session) -> PrepSession:
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    return session


async def delete_prep_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Delete a session and its history permanently.

    Owner-level: CSRF-protected, no capability token (orphans must stay deletable).

    Args:
        session_id: Target session id.
        request: Active request (used for CSRF validation).
        db: Sessions database session (injected).

    Returns:
        Mapping with the deleted session id.

    Raises:
        ApiBusinessError: A3001 (missing session).
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    session = _require_existing_session(session_id, db)
    db.delete(session)
    commit_session(db)
    return {"deleted": session_id}


async def purge_empty_sessions(
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Delete sessions that never accumulated user/assistant content.

    No capability token: contentless rows carry no information, and orphans
    (lost tokens) would otherwise be undeletable clutter. Same-origin CSRF
    protection still applies, so random websites cannot trigger this.

    Args:
        request: Active request (used for CSRF validation).
        db: Sessions database session (injected).

    Returns:
        Mapping with the deleted row count.
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    rows = db.query(PrepSession).all()
    deleted = 0
    for row in rows:
        try:
            messages = json.loads(row.messages or "[]")
        except json.JSONDecodeError:
            continue
        if isinstance(messages, list) and not any(
            m.get("role") in ("user", "assistant") and str(m.get("content") or "").strip()
            for m in messages
            if isinstance(m, dict)
        ):
            db.delete(row)
            deleted += 1
    commit_session(db)
    return {"deleted": deleted}


async def purge_all_sessions(
    request: Request,
    db: Session = Depends(get_sessions_db),
    body: PrepPurgeAllRequest | None = None,
):
    """Delete ALL coaching sessions permanently, with or without content.

    Owner-level: same-origin CSRF protection, no capability token (consistent
    with delete/archive/link — orphans must stay manageable).
    The caller must confirm explicitly via ``{"confirm": true}``; anything
    else is rejected (A0001). This cannot be undone.

    Args:
        request: Active request (used for CSRF validation).
        db: Sessions database session (injected).
        body: Confirmation payload (``confirm`` must be True).

    Returns:
        Mapping with the deleted row count.

    Raises:
        ApiBusinessError: A0001 (missing confirmation).
    """
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
    """Archive (or restore) a session; archived sessions stay fully usable.

    Owner-level: CSRF-protected, no capability token (orphans must stay manageable).

    Args:
        session_id: Target session id.
        body: Archive flag (True archives, False restores).
        request: Active request (used for CSRF validation).
        db: Sessions database session (injected).

    Returns:
        Mapping with the session id and resulting status.

    Raises:
        ApiBusinessError: A3001 (missing session).
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    session = _require_existing_session(session_id, db)
    session.status = (
        SessionStatus.ARCHIVED.value if body.archived else SessionStatus.ACTIVE.value
    )
    session.updated_at = utcnow()
    commit_session(db)
    return {"id": session_id, "status": session.status}


async def reissue_prep_token(
    session_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_sessions_db),
):
    """Mint a fresh capability token for a listed session (owner-level recovery).

    Capability cookies are host-bound and expirable; rows created without a
    browser round-trip (compaction backups carry a token in the row but never
    seed a cookie, cross-device sessions likewise) are listed but unreadable
    (A0401) until recovery. Rotation reseeds the HttpOnly cookie.
    CSRF-protected, no old token required: same trust basis as
    delete/archive in this single-user session list.

    Args:
        session_id: Target session id.
        request: Active request (used for CSRF validation).
        response: Response used to reseed the HttpOnly capability cookie.
        db: Sessions database session (injected).

    Returns:
        Mapping with the recovered session id.

    Raises:
        ApiBusinessError: A3001 (missing session).
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    session = _require_existing_session(session_id, db)
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
    """Link another session's summary + recent turns into this session's context.

    Only one direct level is injected (no chains); self-links are refused.
    Owner-level: CSRF-protected, no capability token (same-origin trusted).

    Prefer per-turn ``#`` references (``context_session_ids``) for transient
    links; this endpoint persists the default linked session for compatibility.

    Args:
        session_id: Target session id.
        body: Link parameters (``linked_session_id`` or null to unlink).
        request: Active request (used for CSRF validation).
        db: Sessions database session (injected).

    Returns:
        Mapping with the session id and effective link target.

    Raises:
        ApiBusinessError: A0001 (self-link), A3001 (missing session/link target).
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    session = _require_existing_session(session_id, db)
    target = body.linked_session_id
    if target is not None:
        if target == session_id:
            raise_error("A0001")
        linked = db.query(PrepSession).filter(PrepSession.id == target).first()
        if linked is None:
            raise_error("A3001")
    session.linked_session_id = target
    session.updated_at = utcnow()
    commit_session(db)
    _refresh_linked_block(session, db)
    return {"id": session_id, "linked_session_id": target}


def _refresh_linked_block(session: PrepSession, db: Session) -> None:
    """Rewrite the linked-session system block so linking takes effect this turn.

    The seeded system messages (prompt + context blocks) are never touched;
    only the dedicated linked block after the leading system run is replaced.
    Best-effort: a broken history must not fail the link itself.
    """
    try:
        try:
            messages = json.loads(session.messages or "[]")
        except json.JSONDecodeError:
            return
        if not isinstance(messages, list):
            return
        kept = [
            m for m in messages
            if not (
                isinstance(m, dict)
                and m.get("role") == "system"
                and isinstance(m.get("content"), str)
                and m["content"].startswith(LINKED_BLOCK_MARKER)
            )
        ]
        block = format_linked_session(db, session.linked_session_id)
        if block:
            # Anchor after the leading system run (multi-message seeding):
            # the block reads as one more pinned context section.
            anchor = 0
            while (
                anchor < len(kept)
                and isinstance(kept[anchor], dict)
                and kept[anchor].get("role") == "system"
            ):
                anchor += 1
            kept.insert(anchor, {"role": "system", "content": f"{LINKED_BLOCK_MARKER}\n{block}"})
        session.messages = json.dumps(kept, ensure_ascii=False)
        session.updated_at = utcnow()
        commit_session(db)
    except Exception as exc:
        db.rollback()
        logger.warning(
            "Linked-block refresh failed sid=%s: %s",
            session.id, redact_api_key(str(exc)),
        )


__all__ = [
    "archive_prep_session",
    "delete_prep_session",
    "link_prep_session",
    "purge_all_sessions",
    "purge_empty_sessions",
    "reissue_prep_token",
]
