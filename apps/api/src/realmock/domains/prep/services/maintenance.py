"""Destructive session maintenance: what counts as deletable.

Route handlers stay thin (CSRF + response shaping in ``routes/manage.py``);
the selection rules for contentless sessions live here.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from realmock.domains.prep.models import PrepSession, commit_session

logger = logging.getLogger(__name__)


def purge_empty_sessions(db: Session) -> int:
    """Delete sessions that never accumulated user/assistant content.

    Returns the number of deleted rows.
    """
    rows = db.query(PrepSession).all()
    deleted = 0
    for row in rows:
        try:
            messages = json.loads(row.messages or "[]")
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            # Corrupt rows may still hold content: never purge them silently
            # by type confusion (same contract as _load_session_messages).
            logger.warning(
                "Prep history unreadable, skipping purge sid=%s",
                getattr(row, "id", ""),
            )
            continue
        if isinstance(messages, list) and not any(
            m.get("role") in ("user", "assistant") and str(m.get("content") or "").strip()
            for m in messages
            if isinstance(m, dict)
        ):
            db.delete(row)
            deleted += 1
    commit_session(db)
    return deleted


__all__ = ["purge_empty_sessions"]
