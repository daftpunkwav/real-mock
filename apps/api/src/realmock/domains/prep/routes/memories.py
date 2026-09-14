"""Prep long-term memory API: user-facing CRUD for rated turns and agent notes.

Creation is intentionally narrow: memories are recorded by the agent (rating flow
or memory_write tool), so there is no blank-create endpoint — the settings page
can only edit or delete what the agent recorded. Single-user app: no capability
token required (unlike per-session chat routes).
"""

from __future__ import annotations

import json
import logging

from fastapi import Depends
from sqlalchemy.orm import Session

from realmock.domains.prep.models import PrepSession, utcnow
from realmock.domains.prep.schemas import (
    MEMORY_ORIGINS,
    PrepMemoryBatchDelete,
    PrepMemoryCreate,
    PrepMemoryUpdate,
)
from realmock.domains.prep.services import (
    clean_reasons,
    clean_tags,
    create_memory,
    get_memory,
    list_memories,
    memory_tags,
    memory_to_detail,
    memory_to_summary,
    touch_memory,
)
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.context.manager import upsert_memory_block
from realmock.platform.core.errors import raise_error
from realmock.platform.database import get_sessions_db

logger = logging.getLogger(__name__)


def _not_found() -> None:
    raise_error("A0404")


async def create_memory_from_rating(
    body: PrepMemoryCreate,
    db: Session = Depends(get_sessions_db),
):
    origin = body.origin if body.origin in MEMORY_ORIGINS else "user_rating"
    # Rating flow always carries a score; agent notes may omit it.
    if origin == "user_rating" and body.score is None:
        raise_error("A0001")
    row = create_memory(
        db,
        summary=(body.comment or body.user_input or "")[:200] or "User-rated turn",
        user_input=body.user_input,
        agent_output=body.agent_output,
        score=body.score,
        reasons=clean_reasons(body.reasons),
        comment=body.comment,
        tags=clean_tags(body.tags),
        origin=origin,
        session_id=body.session_id,
    )
    if body.session_id:
        _note_rating_into_session(db, body.session_id, row.id, body.score)
    return memory_to_detail(row)


def _note_rating_into_session(db: Session, session_id: int, memory_id: int, score: int | None) -> None:
    """Mirror the rating into the session's working memory so the current session sees it immediately.

    The long-term index is injected at session start only; without this note the
    rating would stay invisible until a new session. Best-effort: never fail the request.
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
        memory.remember(
            "note",
            f"User rated a reply {score}/10 (long-term memory #{memory_id}); "
            "honor this feedback in later turns.",
        )
        session.messages = json.dumps(upsert_memory_block(messages, memory), ensure_ascii=False)
        session.updated_at = utcnow()
        db.commit()
    except Exception as exc:
        logger.warning("Rating working-memory note failed sid=%s: %s", session_id, exc)


async def list_memory_summaries(
    tag: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_sessions_db),
):
    return [memory_to_summary(r) for r in list_memories(db, tag=tag or None, limit=limit)]


async def list_memory_tags(db: Session = Depends(get_sessions_db)):
    return {"tags": memory_tags(db)}


async def get_memory_detail(
    memory_id: int,
    db: Session = Depends(get_sessions_db),
):
    row = get_memory(db, memory_id)
    if row is None:
        _not_found()
        return None
    return memory_to_detail(row)


async def update_memory(
    memory_id: int,
    body: PrepMemoryUpdate,
    db: Session = Depends(get_sessions_db),
):
    row = get_memory(db, memory_id)
    if row is None:
        _not_found()
        return None
    patch = body.model_dump(exclude_unset=True)
    if "summary" in patch and patch["summary"] is not None:
        row.summary = str(patch["summary"]).strip()[:200]
    if "tags" in patch and patch["tags"] is not None:
        row.tags = json.dumps(clean_tags(patch["tags"]), ensure_ascii=False)
    if "comment" in patch and patch["comment"] is not None:
        row.comment = str(patch["comment"])
    if "score" in patch:
        row.score = patch["score"]
    touch_memory(row)
    db.commit()
    db.refresh(row)
    return memory_to_detail(row)


async def delete_memory(
    memory_id: int,
    db: Session = Depends(get_sessions_db),
):
    row = get_memory(db, memory_id)
    if row is None:
        _not_found()
        return None
    db.delete(row)
    db.commit()
    return {"deleted": memory_id}


async def batch_delete_memories(
    body: PrepMemoryBatchDelete,
    db: Session = Depends(get_sessions_db),
):
    ids = sorted({int(i) for i in body.ids if int(i) > 0})
    deleted = 0
    for memory_id in ids:
        row = get_memory(db, memory_id)
        if row is not None:
            db.delete(row)
            deleted += 1
    db.commit()
    return {"deleted": deleted}


__all__ = [
    "batch_delete_memories",
    "create_memory_from_rating",
    "delete_memory",
    "get_memory_detail",
    "list_memory_summaries",
    "list_memory_tags",
    "update_memory",
]
