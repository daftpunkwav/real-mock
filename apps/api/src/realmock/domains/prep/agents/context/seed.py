"""First-turn system seed: pinned instructions + resume/profile/company + memories/linked tail.

Cache layout (prefix-stable for prompt caching): the seed is a run of system
messages ordered stable-first — [pinned instructions] [resume/profile/company]
[memories/linked] — so volatile tail blocks invalidate only their own suffix.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from realmock.domains.prep.agents.context.linked import format_linked_session
from realmock.domains.prep.prompts import PREP_SYSTEM
from realmock.domains.prep.services import list_memories
from realmock.platform.catalogs.company import get_company_context
from realmock.platform.database import api_db_session, sessions_db_session
from realmock.platform.services.candidate_read import format_profile_summary, format_resume_summary

# Long-term memories injected into the system prompt (index only; details on
# demand). Default 10; callers may pass a wider limit (0 = all memories).
_MEMORY_INDEX_LIMIT = 10
_MEMORY_SUMMARY_CHARS = 120

def format_memory_index(db: Session | None = None, *, limit: int | None = None) -> str:
    """Render the long-term memory index block for the system prompt (never raises).

    Args:
        db: Optional live sessions Session to reuse (seed path passes its own
            session to avoid opening a second connection). When None, a short
            session is opened internally for standalone callers.
        limit: Entries injected (0 = every memory); None keeps the default 10.
    """
    if db is None:
        try:
            with sessions_db_session() as owned:
                return format_memory_index(owned, limit=limit)
        except Exception:
            return ""
    effective = _MEMORY_INDEX_LIMIT if limit is None else max(0, int(limit))
    try:
        rows = list_memories(db, limit=effective)
    except Exception:
        return ""
    if not rows:
        return ""
    lines = []
    for row in rows:
        try:
            tags = json.loads(row.tags or "[]")
            tag_text = ",".join(str(t) for t in tags) if isinstance(tags, list) else ""
        except (ValueError, TypeError):
            tag_text = ""
        summary = str(row.summary or "")[:_MEMORY_SUMMARY_CHARS]
        suffix = f" [{tag_text}]" if tag_text else ""
        lines.append(f"- [memory #{row.id}]{suffix} {summary}")
    return (
        "Long-term memories (concise index; use memory_get_detail for full text). "
        "This index is a snapshot from session start — memories saved during this "
        "session are not listed, so query memory_list_summaries before writing:\n"
        + "\n".join(lines)
    )


def build_system_message(
    db: Session,
    *,
    resume_id: int | None,
    target_company: str,
    ui_locale: str | None = None,
    linked_session_id: int | None = None,
    memory_index_limit: int | None = None,
) -> str:
    """Legacy single-string seed: the system blocks joined with blank lines.

    New sessions seed via :func:`build_system_messages` (prefix-stable block
    run). This wrapper stays for backward compatibility and debugging; the
    reply-language hint is intentionally excluded (per-turn suffix instead).
    """
    return "\n\n".join(
        block for block in _system_blocks(
            db, resume_id=resume_id, target_company=target_company,
            linked_session_id=linked_session_id,
            memory_index_limit=memory_index_limit,
        )
        if block
    )


def build_system_messages(
    db: Session,
    *,
    resume_id: int | None,
    target_company: str,
    linked_session_id: int | None = None,
    memory_index_limit: int | None = None,
) -> list[dict[str, str]]:
    """First-turn system seed as an ordered stable-first block run.

    [0] pinned coach instructions (never changes) → [1] resume/profile/company
    snapshot → [2] memories/linked volatile tail (omitted when empty). Callers
    store each block as one ``{"role": "system"}`` message so prompt-cache
    prefixes survive tail-block churn.
    """
    blocks = [
        block for block in _system_blocks(
            db, resume_id=resume_id, target_company=target_company,
            linked_session_id=linked_session_id,
            memory_index_limit=memory_index_limit,
        )
        if block
    ]
    if not blocks:
        blocks = [PREP_SYSTEM]
    return [{"role": "system", "content": block} for block in blocks]


def _system_blocks(
    db: Session,
    *,
    resume_id: int | None,
    target_company: str,
    linked_session_id: int | None,
    memory_index_limit: int | None = None,
) -> list[str]:
    """Shared block builders for the single-string and multi-message seeds."""
    with api_db_session() as api_db:
        ctx = format_resume_summary(api_db, resume_id)
        profile = format_profile_summary(api_db)
    company = get_company_context(target_company or "")
    memories = format_memory_index(db, limit=memory_index_limit)
    linked = format_linked_session(db, linked_session_id)
    context_block = "\n".join(part for part in (company, ctx, profile) if part)
    tail_block = "\n".join(part for part in (memories, linked) if part)
    return [PREP_SYSTEM, context_block, tail_block]


__all__ = [
    "PREP_SYSTEM",
    "build_system_message",
    "build_system_messages",
    "format_memory_index",
]
