"""Prep long-term memory store: serialization helpers and CRUD used by routes and agent tools.

Storage is the ``prep_memories`` sessions.db table (single-user app: no owner column).
Summaries and tags are maintained by the LLM (one line, topic-organized); this
module only cleans bounds (lengths, counts) and serializes rows.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from realmock.domains.prep.models import PrepMemory, utcnow
from realmock.domains.prep.schemas import (
    PrepMemoryDetail,
    PrepMemorySummary,
)

MEMORY_SUMMARY_MAX_CHARS = 200
MEMORY_BODY_MAX_CHARS = 8000
MEMORY_TAG_MAX_CHARS = 30
MEMORY_TAGS_MAX_COUNT = 20
MEMORY_LIST_DEFAULT_LIMIT = 20
MEMORY_LIST_MAX_LIMIT = 50


def clean_tags(raw: Any) -> list[str]:
    """Normalize a tag list: plain strings, trimmed, deduped, bounded."""
    seen: set[str] = set()
    tags: list[str] = []
    items = raw if isinstance(raw, list) else []
    for item in items:
        tag = str(item or "").strip()[:MEMORY_TAG_MAX_CHARS]
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
        if len(tags) >= MEMORY_TAGS_MAX_COUNT:
            break
    return tags


def clean_reasons(raw: Any) -> list[str]:
    """Normalize reason chips the same way tags are cleaned (at most 10)."""
    seen: set[str] = set()
    reasons: list[str] = []
    items = raw if isinstance(raw, list) else []
    for item in items:
        reason = str(item or "").strip()[:MEMORY_TAG_MAX_CHARS]
        if reason and reason not in seen:
            seen.add(reason)
            reasons.append(reason)
        if len(reasons) >= 10:
            break
    return reasons


def _decode_list(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def memory_to_summary(row: PrepMemory) -> PrepMemorySummary:
    """Serialize the index view (id/summary/tags only — no turn bodies)."""
    return PrepMemorySummary(
        id=row.id,
        summary=row.summary or "",
        tags=_decode_list(row.tags),
        origin=row.origin or "",
        score=row.score,
        session_id=row.session_id,
        updated_at=row.updated_at,
    )


def memory_to_detail(row: PrepMemory) -> PrepMemoryDetail:
    """Serialize the full record for on-demand detail loads."""
    return PrepMemoryDetail(
        **memory_to_summary(row).model_dump(),
        user_input=row.user_input or "",
        agent_output=row.agent_output or "",
        comment=row.comment or "",
        reasons=_decode_list(row.reasons),
        created_at=row.created_at,
    )


def create_memory(
    db: Session,
    *,
    summary: str,
    user_input: str = "",
    agent_output: str = "",
    score: int | None = None,
    reasons: list[str] | None = None,
    comment: str = "",
    tags: list[str] | None = None,
    origin: str = "agent_note",
    session_id: int | None = None,
) -> PrepMemory:
    """Insert one memory row with bounds applied; caller commits via session flush."""
    row = PrepMemory(
        summary=str(summary or "").strip()[:MEMORY_SUMMARY_MAX_CHARS],
        user_input=str(user_input or "")[:MEMORY_BODY_MAX_CHARS],
        agent_output=str(agent_output or "")[:MEMORY_BODY_MAX_CHARS],
        score=score,
        comment=str(comment or ""),
        reasons=json.dumps(clean_reasons(reasons), ensure_ascii=False),
        tags=json.dumps(clean_tags(tags), ensure_ascii=False),
        origin=origin,
        session_id=session_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_memories(db: Session, *, tag: str | None = None, limit: int = MEMORY_LIST_DEFAULT_LIMIT) -> list[PrepMemory]:
    """Newest-first memory rows, optionally filtered by one tag (Python-side match)."""
    limit = max(1, min(MEMORY_LIST_MAX_LIMIT, limit or MEMORY_LIST_DEFAULT_LIMIT))
    rows = db.execute(
        select(PrepMemory).order_by(desc(PrepMemory.updated_at)).limit(500)
    ).scalars().all()
    if tag:
        rows = [r for r in rows if tag in _decode_list(r.tags)]
    return list(rows[:limit])


def memory_tags(db: Session) -> list[str]:
    """Distinct tags across all memories, most-recently-used first."""
    seen: list[str] = []
    rows = db.execute(
        select(PrepMemory.tags, PrepMemory.updated_at).order_by(desc(PrepMemory.updated_at)).limit(500)
    ).all()
    for raw_tags, _ in rows:
        for tag in _decode_list(raw_tags):
            if tag not in seen:
                seen.append(tag)
    return seen


def get_memory(db: Session, memory_id: int) -> PrepMemory | None:
    """Fetch one memory row by id."""
    return db.get(PrepMemory, memory_id)


def touch_memory(row: PrepMemory) -> None:
    """Bump updated_at so edited memories surface first."""
    row.updated_at = utcnow()


__all__ = [
    "MEMORY_BODY_MAX_CHARS",
    "MEMORY_LIST_DEFAULT_LIMIT",
    "MEMORY_LIST_MAX_LIMIT",
    "MEMORY_SUMMARY_MAX_CHARS",
    "MEMORY_TAGS_MAX_COUNT",
    "MEMORY_TAG_MAX_CHARS",
    "clean_reasons",
    "clean_tags",
    "create_memory",
    "get_memory",
    "list_memories",
    "memory_tags",
    "memory_to_detail",
    "memory_to_summary",
    "touch_memory",
]
