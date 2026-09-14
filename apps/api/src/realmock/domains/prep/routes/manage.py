"""Prep session management: delete, archive, and cross-session linking.

Management operations (delete / archive / truncate / link / purge-empty) are
owner-level: they require same-origin CSRF protection but NOT the per-session
capability token. Rationale: the session list is unauthenticated single-user
data, HttpOnly capability cookies are host-bound and expirable, and requiring
the token here permanently locks orphans (listed but undeletable, A0401).

Content-reading operations (GET messages / POST message+stream / fork source)
still require the capability token.
"""

from __future__ import annotations

import json
import logging

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from realmock.domains.prep.agents.context import LINKED_BLOCK_MARKER, format_linked_session
from realmock.domains.prep.models import PrepSession
from realmock.domains.prep.models import utcnow
from realmock.domains.prep.schemas import PrepArchiveRequest, PrepLinkRequest
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
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    session = _require_existing_session(session_id, db)
    db.delete(session)
    db.commit()
    return {"deleted": session_id}


async def purge_empty_sessions(
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Delete sessions that never accumulated user/assistant content.

    No capability token: contentless rows carry no information, and orphans
    (lost tokens) would otherwise be undeletable clutter. Same-origin CSRF
    protection still applies, so random websites cannot trigger this.
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
    db.commit()
    return {"deleted": deleted}


async def purge_all_sessions(
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Delete ALL coaching sessions permanently, with or without content.

    Owner-level: same-origin CSRF protection, no capability token (consistent
    with delete/archive/truncate/link — orphans must stay manageable).
    The caller must confirm explicitly; this cannot be undone.
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    rows = db.query(PrepSession).all()
    deleted = len(rows)
    for row in rows:
        db.delete(row)
    db.commit()
    return {"deleted": deleted}


async def archive_prep_session(
    session_id: int,
    body: PrepArchiveRequest,
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Archive (or restore) a session; archived sessions stay fully usable.

    Owner-level: CSRF-protected, no capability token (orphans must stay manageable).
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    session = _require_existing_session(session_id, db)
    session.status = (
        SessionStatus.ARCHIVED.value if body.archived else SessionStatus.ACTIVE.value
    )
    session.updated_at = utcnow()
    db.commit()
    return {"id": session_id, "status": session.status}


async def reissue_prep_token(
    session_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_sessions_db),
):
    """Mint a fresh capability token for a listed session (owner-level recovery).

    Capability cookies are host-bound and expirable, and server-side copies
    (compaction backups, cross-device sessions) never receive one — without
    recovery those rows are listed but permanently locked (A0401). Rotation
    reseeds the HttpOnly cookie. CSRF-protected, no old token required: same
    trust basis as delete/archive in this single-user session list.
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    session = _require_existing_session(session_id, db)
    session.access_token = new_access_token()
    session.updated_at = utcnow()
    db.commit()
    set_session_cookie(
        response,
        scope="prep",
        session_id=session.id,
        token=session.access_token,
        secure=cookie_should_be_secure(request),
    )
    return {"id": session.id}


async def link_prep_session(    session_id: int,
    body: PrepLinkRequest,
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Link another session's summary + recent turns into this session's context.

    Only one direct level is injected (no chains); self-links are refused.
    Owner-level: CSRF-protected, no capability token (same-origin trusted).

    Superseded by per-turn ``#`` references (``context_session_ids``): the UI
    no longer calls this, but the endpoint stays for API compatibility.
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
    db.commit()
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
                m.get("role") == "system"
                and isinstance(m.get("content"), str)
                and m["content"].startswith(LINKED_BLOCK_MARKER)
            )
        ]
        block = format_linked_session(db, session.linked_session_id)
        if block:
            # Anchor after the leading system run (multi-message seeding):
            # the block reads as one more pinned context section.
            anchor = 0
            while anchor < len(kept) and kept[anchor].get("role") == "system":
                anchor += 1
            kept.insert(anchor, {"role": "system", "content": f"{LINKED_BLOCK_MARKER}\n{block}"})
        session.messages = json.dumps(kept, ensure_ascii=False)
        session.updated_at = utcnow()
        db.commit()
    except Exception as exc:
        logger.warning("Linked-block refresh failed sid=%s: %s", session.id, exc)


__all__ = ["archive_prep_session", "delete_prep_session", "link_prep_session", "purge_all_sessions", "purge_empty_sessions", "reissue_prep_token"]
