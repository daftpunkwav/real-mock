"""Prep read-only lists: resume dropdown summaries and coaching session lists.

List endpoints do not include message bodies or capability tokens.
"""

from __future__ import annotations

import json
import logging

from fastapi import Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, defer

from realmock.domains.prep.models import PrepSession
from realmock.domains.prep.schemas import PrepSessionSummary
from realmock.domains.prep.services.session_stats import (
    SESSION_SUMMARY_SNIPPET_MAX_CHARS,
    compute_session_summary_and_count,
)
from realmock.platform.database import get_api_db, get_sessions_db
from realmock.platform.services.resume_picker import list_resume_picker_items

logger = logging.getLogger(__name__)


# Newest-first cap: legacy rows without cached columns still parse message JSON
# per row, so bound rows to avoid loading unbounded Text bodies into memory
# (single-user scale). Cached rows skip parsing entirely.
SESSION_LIST_LIMIT = 500


def list_resume_picker(db: Session = Depends(get_api_db)):
    """Return dropdown summaries only; exclude analysis text."""
    return list_resume_picker_items(db)


def _cached_summary_and_count(session: PrepSession) -> tuple[str, int] | None:
    """Return cached list metrics, or None when the row predates the cache.

    Corrupt cache shapes (non-string summary, non-numeric count) fall back to
    None so the caller re-derives from messages instead of failing the list.
    """
    raw_summary = getattr(session, "summary", None)
    raw_count = getattr(session, "message_count", None)
    if not raw_summary and not raw_count:
        return None
    try:
        summary = str(raw_summary or "")[:SESSION_SUMMARY_SNIPPET_MAX_CHARS]
        count = int(raw_count or 0)
    except (TypeError, ValueError):
        logger.warning("Prep list ignoring corrupt cache sid=%s", getattr(session, "id", ""))
        return None
    if count < 0:
        return None
    return summary, count


def _legacy_messages(db: Session, session_ids: list[int]) -> dict[int, str]:
    """Stored conversation bodies of the rows that predate the cached columns.

    One bounded query serves every legacy row, so the rows that already carry
    a cached summary never pay for a conversation body they do not read.
    """
    if not session_ids:
        return {}
    rows = (
        db.query(PrepSession.id, PrepSession.messages).filter(PrepSession.id.in_(session_ids)).all()
    )
    return {int(sid): raw for sid, raw in rows}


def _parse_history(raw: str | None, session_id: int) -> list:
    """Parse a stored conversation body; an unreadable row degrades to empty."""
    try:
        loaded = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        logger.warning("Prep list skipping unreadable history sid=%s", session_id)
        return []
    if not isinstance(loaded, list):
        logger.warning("Prep list skipping non-list history sid=%s", session_id)
        return []
    return loaded


def list_prep_sessions(
    db: Session = Depends(get_sessions_db),
    api_db: Session = Depends(get_api_db),
) -> list[PrepSessionSummary]:
    """List coaching sessions (shown in the frontend's “Conversation History,” grouped by resume)."""
    # The conversation body stays deferred: the cached summary/count columns
    # answer the list, and only the legacy rows without them need the body.
    # Fetching it for every row would load the whole chat history of every
    # session on every list request.
    rows = (
        db.query(PrepSession)
        .options(defer(PrepSession.messages))
        .order_by(func.coalesce(PrepSession.updated_at, PrepSession.created_at).desc())
        .limit(SESSION_LIST_LIMIT)
        .all()
    )
    names = {p.id: p.filename for p in list_resume_picker_items(api_db)}
    cached_values: list[tuple[str, int] | None] = []
    legacy_ids: list[int] = []
    for s in rows:
        cached = _cached_summary_and_count(s)
        cached_values.append(cached)
        if cached is None:
            legacy_ids.append(int(s.id))
    legacy_bodies = _legacy_messages(db, legacy_ids)
    items: list[PrepSessionSummary] = []
    for s, cached in zip(rows, cached_values):
        # Fast path: cached columns maintained by writers via
        # compute_session_summary_and_count (no JSON parse).
        if cached is not None:
            summary, message_count = cached
        else:
            # Fallback for legacy rows predating the cached columns.
            loaded = _parse_history(legacy_bodies.get(int(s.id)), s.id)
            summary, message_count = compute_session_summary_and_count(loaded)
        items.append(
            PrepSessionSummary(
                id=s.id,
                resume_id=s.resume_id,
                resume_filename=names.get(s.resume_id) if s.resume_id else None,
                summary=summary,
                message_count=message_count,
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
