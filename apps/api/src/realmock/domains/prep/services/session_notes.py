"""Session working-memory notes: mirror memory events into live sessions.

The long-term memory index is injected at session start only; rating notes
written here make feedback visible in the current session without a restart.
Best-effort by design: note failures never fail the caller's request.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from realmock.domains.prep.models import PrepSession, commit_session, utcnow
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.context.manager import upsert_memory_block

logger = logging.getLogger(__name__)


def note_rating_into_session(db: Session, session_id: int, memory_id: int, score: int | None) -> None:
    """Mirror a rating into the session's working memory.

    Args:
        db: Active Session; committed on success, rolled back on failure.
        session_id: Target coaching session id (missing rows are ignored).
        memory_id: Long-term memory id referenced in the note.
        score: User rating 1-10 (or None for non-rating origins).

    Returns:
        None. Never raises.
    """
    try:
        session = db.get(PrepSession, session_id)
        if session is None:
            return
        try:
            messages = json.loads(session.messages or "[]")
        except json.JSONDecodeError:
            return
        if not isinstance(messages, list):
            return
        memory = WorkingMemory.load_from_messages(messages)
        rating = f"{score}/10" if isinstance(score, int) else "unrated"
        memory.remember(
            "note",
            f"User rated a reply {rating} (long-term memory #{memory_id}); "
            "honor this feedback in later turns.",
        )
        session.messages = json.dumps(upsert_memory_block(messages, memory), ensure_ascii=False)
        session.updated_at = utcnow()
        commit_session(db)
    except Exception as exc:
        db.rollback()
        logger.warning("Rating working-memory note failed sid=%s: %s", session_id, exc)


__all__ = ["note_rating_into_session"]
