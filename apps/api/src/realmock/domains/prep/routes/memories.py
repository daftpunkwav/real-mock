"""Prep long-term memory API: user-facing CRUD for rated turns and agent notes.

Creation is intentionally narrow: memories are recorded from the rating flow
or the agent's memory_write tool — there is no blank form that invents a
memory from nothing (an empty summary falls back to the source turn text, or
"User-rated turn"). Single-user app: no capability token required (unlike
per-session chat routes); mutating endpoints still require same-origin CSRF
protection.
"""

from __future__ import annotations

import json

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from realmock.domains.prep.models import commit_session
from realmock.platform.core.session_auth.csrf import assert_csrf_if_cookie_only
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
    note_rating_into_session,
    touch_memory,
)
from realmock.platform.core.errors import raise_error
from realmock.platform.database import get_sessions_db


def _not_found() -> None:
    raise_error("A0404")


async def create_memory_from_rating(
    body: PrepMemoryCreate,
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Record a long-term memory from the rating flow (or an agent note).

    Args:
        body: Validated memory payload (user/agent turns, score, tags, origin).
        request: Active request (used for CSRF validation).
        db: Sessions database session (injected).

    Returns:
        The persisted memory detail view.

    Raises:
        ApiBusinessError: A0001 (user_rating without score).
        ValueError: Out-of-range score rejected by the memory store.
    """
    # Owner-level write: same-origin CSRF protection, no capability token
    # (consistent with manage.py — orphans must stay manageable).
    assert_csrf_if_cookie_only(request, used_header=False)
    # Schema already restricts origin to MEMORY_ORIGINS; keep a defensive
    # fallback so a future schema relaxation never writes an unknown origin.
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
        note_rating_into_session(db, body.session_id, row.id, body.score)
    return memory_to_detail(row)


async def list_memory_summaries(
    tag: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_sessions_db),
):
    """List memory index entries, newest first (clamped server-side to 1..50).

    Args:
        tag: Optional single-tag filter.
        limit: Max entries requested (server clamps to the allowed window).
        db: Sessions database session (injected).

    Returns:
        Index views (id/summary/tags only, no turn bodies).
    """
    return [memory_to_summary(r) for r in list_memories(db, tag=tag or None, limit=limit)]


async def list_memory_tags(db: Session = Depends(get_sessions_db)):
    """List distinct memory tags, most-recently-used first.

    Args:
        db: Sessions database session (injected).

    Returns:
        Mapping with the tag list.
    """
    return {"tags": memory_tags(db)}


async def get_memory_detail(
    memory_id: int,
    db: Session = Depends(get_sessions_db),
):
    """Load one memory with its full turn bodies.

    Args:
        memory_id: Target memory id.
        db: Sessions database session (injected).

    Returns:
        The full memory detail view.

    Raises:
        ApiBusinessError: A0404 (unknown id).
    """
    row = get_memory(db, memory_id)
    if row is None:
        _not_found()
        return None
    return memory_to_detail(row)


async def update_memory(
    memory_id: int,
    body: PrepMemoryUpdate,
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Patch a memory's summary/tags/comment/score (CSRF-protected).

    Args:
        memory_id: Target memory id.
        body: Partial update payload (only set fields are applied).
        request: Active request (used for CSRF validation).
        db: Sessions database session (injected).

    Returns:
        The refreshed memory detail view.

    Raises:
        ApiBusinessError: A0404 (unknown id), A0001 (empty summary).
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    row = get_memory(db, memory_id)
    if row is None:
        _not_found()
        return None
    patch = body.model_dump(exclude_unset=True)
    if "summary" in patch and patch["summary"] is not None:
        cleaned_summary = str(patch["summary"]).strip()[:200]
        if not cleaned_summary:
            raise_error("A0001")
        row.summary = cleaned_summary
    if "tags" in patch and patch["tags"] is not None:
        row.tags = json.dumps(clean_tags(patch["tags"]), ensure_ascii=False)
    if "comment" in patch and patch["comment"] is not None:
        row.comment = str(patch["comment"])
    if "score" in patch:
        row.score = patch["score"]
    touch_memory(row)
    commit_session(db)
    db.refresh(row)
    return memory_to_detail(row)


async def delete_memory(
    memory_id: int,
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Delete one memory permanently (CSRF-protected).

    Args:
        memory_id: Target memory id.
        request: Active request (used for CSRF validation).
        db: Sessions database session (injected).

    Returns:
        Mapping with the deleted id.

    Raises:
        ApiBusinessError: A0404 (unknown id).
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    row = get_memory(db, memory_id)
    if row is None:
        _not_found()
        return None
    db.delete(row)
    commit_session(db)
    return {"deleted": memory_id}


async def batch_delete_memories(
    body: PrepMemoryBatchDelete,
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Delete up to 100 memories in one request (CSRF-protected, rate-limited).

    Unknown ids are skipped silently; one malformed id never fails the batch.

    Args:
        body: Batch payload (1..100 ids).
        request: Active request (used for CSRF validation).
        db: Sessions database session (injected).

    Returns:
        Mapping with the deleted row count.
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    # Schema guarantees ints, but coerce defensively: one bad id must not 500 the batch.
    ids: set[int] = set()
    for raw in body.ids:
        try:
            value = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if value > 0:
            ids.add(value)
    deleted = 0
    for memory_id in sorted(ids):
        row = get_memory(db, memory_id)
        if row is not None:
            db.delete(row)
            deleted += 1
    commit_session(db)
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
