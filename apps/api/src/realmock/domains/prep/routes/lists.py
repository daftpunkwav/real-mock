"""Prep read-only lists: resume dropdown summaries and coaching session lists.

List endpoints do not include message bodies or capability tokens.
"""

from __future__ import annotations

import json
from typing import Any

import logging

from fastapi import Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from realmock.domains.prep.models import PrepSession
from realmock.domains.prep.schemas import PrepSessionSummary
from realmock.platform.database import get_api_db, get_sessions_db
from realmock.platform.services.resume_picker import list_resume_picker_items

logger = logging.getLogger(__name__)


# Newest-first cap: the list parses message JSON per row, so bound rows to
# avoid loading unbounded Text bodies into memory (single-user scale).
SESSION_LIST_LIMIT = 500


def list_resume_picker(db: Session = Depends(get_api_db)):
    """Return dropdown summaries only; exclude analysis text.

    Args:
        db: API database session (injected).

    Returns:
        Resume picker items (id/filename pairs, no analysis payloads).
    """
    return list_resume_picker_items(db)


def _is_user_text(m: Any) -> bool:
    return isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str)


def _is_countable(m: Any) -> bool:
    return (
        isinstance(m, dict)
        and m.get("role") in ("user", "assistant")
        and isinstance(m.get("content"), str)
    )


def list_prep_sessions(
    db: Session = Depends(get_sessions_db),
    api_db: Session = Depends(get_api_db),
) -> list[PrepSessionSummary]:
    """List coaching sessions (shown in the frontend's “Conversation History,” grouped by resume).

    Returns summaries only (first question + message count + associated resume),
    without message bodies or capability tokens—opening a specific session still uses the original token validation.
    Newest-first, capped at SESSION_LIST_LIMIT rows.

    Args:
        db: Sessions database session (injected).
        api_db: API database session for resume filenames (injected).

    Returns:
        Newest-first session summaries (corrupt histories surface as empty summaries, never errors).
    """
    rows = (
        db.query(PrepSession)
        .order_by(func.coalesce(PrepSession.updated_at, PrepSession.created_at).desc())
        .limit(SESSION_LIST_LIMIT)
        .all()
    )
    names = {p.id: p.filename for p in list_resume_picker_items(api_db)}
    items: list[PrepSessionSummary] = []
    for s in rows:
        try:
            loaded = json.loads(s.messages or "[]")
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            logger.warning("Prep list skipping unreadable history sid=%s", s.id)
            loaded = []
        if not isinstance(loaded, list):
            logger.warning("Prep list skipping non-list history sid=%s", s.id)
            loaded = []
        msgs = loaded

        summary = next(
            (str(m.get("content") or "").strip() for m in msgs if _is_user_text(m)),
            "",
        )
        items.append(
            PrepSessionSummary(
                id=s.id,
                resume_id=s.resume_id,
                resume_filename=names.get(s.resume_id) if s.resume_id else None,
                summary=summary[:48],
                message_count=sum(1 for m in msgs if _is_countable(m)),
                status=getattr(s, "status", "") or "active",
                linked_session_id=getattr(s, "linked_session_id", None),
                token_usage=s.token_usage or 0,
                prompt_tokens=s.prompt_tokens or 0,
                completion_tokens=s.completion_tokens or 0,
                cached_tokens=s.cached_tokens or 0,
                created_at=s.created_at,
                updated_at=getattr(s, "updated_at", None) or s.created_at,
            )
        )
    return items

__all__ = [
    "SESSION_LIST_LIMIT",
    "list_prep_sessions",
    "list_resume_picker",
]
