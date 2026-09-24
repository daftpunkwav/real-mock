"""Prep long-term memory store: serialization helpers and CRUD used by routes and agent tools.

Storage is the ``prep_memories`` sessions.db table (single-user app: no owner column).
Summaries and tags are maintained by the LLM (one line, topic-organized); this
module only cleans bounds (lengths, counts) and serializes rows.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from realmock.domains.prep.models import PrepMemory, commit_session, utcnow
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
# Scan window for newest-first unfiltered listing/tag aggregation (single-user
# scale). Single-tag filtering is pushed down to SQL via a literal substring
# predicate so deep history stays reachable; unfiltered reads still cap here.
MEMORY_SCAN_LIMIT = 500


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
    """Insert one memory row with bounds applied and commit it.

    Args:
        db: Active Session; committed (or rolled back on failure) here.
        summary: One-line index, stripped and capped at 200 chars.
        user_input: Source user turn, capped at 8000 chars.
        agent_output: Source agent turn, capped at 8000 chars.
        score: Optional 1-10 rating (validated here as well as in routes).
        reasons: Reason chips, cleaned to at most 10 items.
        comment: Free-form note, truncated to 2000 chars here.
        tags: Topic tags, cleaned to at most 20 items.
        origin: One of user_rating | user_emphasis | agent_note.
        session_id: Origin session id, if any.

    Returns:
        The persisted PrepMemory row (refreshed).

    Raises:
        ValueError: When score is outside 1..10.
    """
    if score is not None and not 1 <= score <= 10:
        raise ValueError("score must be within 1..10")
    row = PrepMemory(
        summary=str(summary or "").strip()[:MEMORY_SUMMARY_MAX_CHARS],
        user_input=str(user_input or "")[:MEMORY_BODY_MAX_CHARS],
        agent_output=str(agent_output or "")[:MEMORY_BODY_MAX_CHARS],
        score=score,
        comment=str(comment or "")[:2000],
        reasons=json.dumps(clean_reasons(reasons), ensure_ascii=False),
        tags=json.dumps(clean_tags(tags), ensure_ascii=False),
        origin=origin,
        session_id=session_id,
    )
    db.add(row)
    commit_session(db)
    db.refresh(row)
    return row


def list_memories(db: Session, *, tag: str | None = None, limit: int = MEMORY_LIST_DEFAULT_LIMIT) -> list[PrepMemory]:
    """Newest-first memory rows, optionally filtered by one tag.

    Args:
        db: Read Session (no commit).
        tag: Optional single-tag filter; unknown tags yield []. When given,
            the predicate is pushed down to SQL as a literal substring match
            on the quoted tag, which is an exact-element match since tags
            persist as a JSON string array via :func:`clean_tags`, so deep
            history beyond any scan window is still reachable.
        limit: Max rows returned. ``0`` (or negative) means the full scan
            window ("all memories" — the session-seed index setting uses this).
            Positive values clamp to 1..MEMORY_SCAN_LIMIT; the tool and HTTP
            callers clamp themselves to MEMORY_LIST_MAX_LIMIT before calling.

    Returns:
        At most ``limit`` rows newest-first (tag path hits SQL directly;
        unfiltered path reads the newest MEMORY_SCAN_LIMIT scan window).
    """
    limit = MEMORY_SCAN_LIMIT if limit <= 0 else min(limit, MEMORY_SCAN_LIMIT)
    if tag:
        # Tags persist as JSON arrays (e.g. '["a", "b"]'); the surrounding
        # double quotes give a strict element boundary, avoiding prefix hits.
        # A literal '"' would break that boundary, and a lone '\' is stored
        # JSON-escaped ('\\'), which byte matching would miss — either way
        # fall back to Python-side matching for such pathological input.
        if '"' in tag or "\\" in tag:
            rows = db.execute(
                select(PrepMemory).order_by(desc(PrepMemory.updated_at)).limit(MEMORY_SCAN_LIMIT)
            ).scalars().all()
            rows = [r for r in rows if tag in _decode_list(r.tags)]
            return list(rows[:limit])
        # instr() is a literal byte-substring search: unlike LIKE it treats
        # '%', '_' as ordinary chars and stays case-sensitive, matching the
        # Python exact-element semantics in _decode_list.
        rows = db.execute(
            select(PrepMemory)
            .where(func.instr(PrepMemory.tags, f'"{tag}"') > 0)
            .order_by(desc(PrepMemory.updated_at))
            .limit(limit)
        ).scalars().all()
        return list(rows)
    rows = db.execute(
        select(PrepMemory).order_by(desc(PrepMemory.updated_at)).limit(MEMORY_SCAN_LIMIT)
    ).scalars().all()
    return list(rows[:limit])


def memory_tags(db: Session) -> list[str]:
    """Distinct tags across all memories, most-recently-used first."""
    seen: set[str] = set()
    ordered: list[str] = []
    rows = db.execute(
        select(PrepMemory.tags, PrepMemory.updated_at).order_by(desc(PrepMemory.updated_at)).limit(MEMORY_SCAN_LIMIT)
    ).all()
    for raw_tags, _ in rows:
        for tag in _decode_list(raw_tags):
            if tag not in seen:
                seen.add(tag)
                ordered.append(tag)
    return ordered


def get_memory(db: Session, memory_id: int) -> PrepMemory | None:
    """Fetch one memory row by id."""
    return db.get(PrepMemory, memory_id)


def find_memory_by_summary(db: Session, summary: str) -> PrepMemory | None:
    """Fetch the newest memory with an exact summary match (cross-turn dedupe).

    Args:
        db: Read Session (no commit).
        summary: Stripped one-line index to match exactly.

    Returns:
        The newest matching row, or None.
    """
    text = str(summary or "").strip()
    if not text:
        return None
    return (
        db.query(PrepMemory)
        .filter(PrepMemory.summary == text)
        .order_by(desc(PrepMemory.id))
        .first()
    )


def touch_memory(row: PrepMemory) -> None:
    """Bump updated_at so edited memories surface first."""
    row.updated_at = utcnow()


__all__ = [
    "MEMORY_BODY_MAX_CHARS",
    "MEMORY_LIST_DEFAULT_LIMIT",
    "MEMORY_LIST_MAX_LIMIT",
    "MEMORY_SCAN_LIMIT",
    "MEMORY_SUMMARY_MAX_CHARS",
    "MEMORY_TAGS_MAX_COUNT",
    "MEMORY_TAG_MAX_CHARS",
    "clean_reasons",
    "clean_tags",
    "create_memory",
    "find_memory_by_summary",
    "get_memory",
    "list_memories",
    "memory_tags",
    "memory_to_detail",
    "memory_to_summary",
    "touch_memory",
]
