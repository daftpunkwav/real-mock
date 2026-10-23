"""Prep session admission rules shared by the prep routes.

Every prep route answers the same three questions before it touches a
session: does the session exist (A3001), does the caller own it (the
session capability token, A0401 on mismatch), and may it still take work
(a completed session refuses new turns with A3002). The rules live here so
the routes apply them in one order instead of repeating the guard.

Order matters and differs per caller:

- ``require_open_prep_session`` — a token-carrying turn route: unknown
  session, then wrong token, then completed session.
- ``require_owned_prep_session`` — a token-carrying route that may still
  fork a finished session.
- ``require_writable_prep_session`` — an owner-level route (history
  surgery): unknown session, then completed session, no token so an
  orphaned session stays manageable.
- ``load_prep_session`` — existence only.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from realmock.domains.prep.models import PrepSession
from realmock.platform.core.constants import SessionStatus
from realmock.platform.core.errors import raise_error
from realmock.platform.core.session_auth import assert_session_token

#: Detail text for a capability-token mismatch on a prep session.
#: Private to this module: the wording belongs to the guard, no caller reads it.
_PREP_FORBIDDEN_DETAIL = "Don't have access to this coaching session"


def load_prep_session(db: Session, session_id: int) -> PrepSession:
    """Load a prep session; A3001 when it does not exist."""
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    return session


def _refuse_completed(session: PrepSession) -> None:
    """A3002 when the session already finished and cannot take new work."""
    if getattr(session, "status", None) == SessionStatus.COMPLETED.value:
        raise_error("A3002")


def require_owned_prep_session(
    db: Session,
    session_id: int,
    access: str | None,
) -> PrepSession:
    """Load a prep session and prove the caller owns it.

    An unknown session is A3001 and a wrong capability token is A0401; a
    completed session is still accepted (forking a finished session is
    allowed).
    """
    session = load_prep_session(db, session_id)
    assert_session_token(session, access, detail=_PREP_FORBIDDEN_DETAIL)
    return session


def require_open_prep_session(
    db: Session,
    session_id: int,
    access: str | None,
) -> PrepSession:
    """Load a prep session that may still take a turn.

    Order is fixed: unknown session (A3001), wrong capability token
    (A0401), completed session (A3002).
    """
    session = require_owned_prep_session(db, session_id, access)
    _refuse_completed(session)
    return session


def require_writable_prep_session(db: Session, session_id: int) -> PrepSession:
    """Load a prep session that may still take work (owner level, no token).

    Used by the history-surgery routes: an orphaned session must stay
    manageable, so the capability token is not required.
    """
    session = load_prep_session(db, session_id)
    _refuse_completed(session)
    return session


__all__ = [
    "load_prep_session",
    "require_open_prep_session",
    "require_owned_prep_session",
    "require_writable_prep_session",
]
