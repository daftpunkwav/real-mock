"""Cross-session linking: single-level target + recent-turn rendering.

Single truth for linked-session formatting, shared by the agent context seed
(per-turn injection) and the management route (link refresh). Both callers
pass their own Session; this module never opens connections.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.prep.models import PrepSession, commit_session, utcnow
from realmock.platform.core.security import redact_api_key

logger = logging.getLogger(__name__)

# Per-turn referenced-session block marker (transient; stripped before persist).
REF_BLOCK_MARKER = "[Referenced sessions]"
# Persisted linked-session block marker (routes/manage.py refresh path).
LINKED_BLOCK_MARKER = "[Linked session context]"

# Linked-session context budgets (single direct level, no chains).
_LINKED_TURNS = 6
_LINKED_TURN_CHARS = 300
# Per-turn # references honor at most this many sessions (prompt-budget guard).
_MAX_LINKED_SESSIONS = 5


def format_linked_session(db: Session, linked_id: int | None) -> str:
    """Render the linked session's target + recent turns for context injection.

    Single direct level only; missing rows yield "". Never raises (a broken
    link must not fail session startup).
    """
    if not linked_id:
        return ""
    try:
        row = db.get(PrepSession, linked_id)
        if row is None:
            return ""
        try:
            messages = json.loads(row.messages or "[]")
        except json.JSONDecodeError:
            return ""
        if not isinstance(messages, list):
            return ""
        turns = [
            str(m.get("content") or "").strip()[:_LINKED_TURN_CHARS]
            for m in messages
            if isinstance(m, dict)
            and m.get("role") in ("user", "assistant")
            and str(m.get("content") or "").strip()
        ][-_LINKED_TURNS * 2:]
        header = (
            f"Linked session #{linked_id}"
            f" (role: {row.target_role or '-'}, company: {row.target_company or '-'})"
        )
        if not turns:
            return f"{header}: no conversation yet."
        lines = [f"- {text}" for text in turns if text]
        return f"{header}, recent turns:\n" + "\n".join(lines)
    except Exception:
        logger.debug("format_linked_session failed linked_id=%s", linked_id, exc_info=True)
        return ""


def format_linked_sessions(
    db: Session, linked_ids: list[int] | None, *, exclude_id: int | None = None
) -> str:
    """Render several linked sessions' targets + recent turns for per-turn injection.

    Same single-level budgets as :func:`format_linked_session`; unknown ids are
    skipped silently (a deleted session must not fail the turn). At most
    ``_MAX_LINKED_SESSIONS`` ids are honored; the caller's own id is excluded.
    """
    ids: list[int] = []
    for raw in linked_ids or []:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value == exclude_id or value in ids:
            continue
        ids.append(value)
        if len(ids) >= _MAX_LINKED_SESSIONS:
            break
    blocks = [format_linked_session(db, linked_id) for linked_id in ids]
    blocks = [block for block in blocks if block]
    if not blocks:
        return ""
    return f"{REF_BLOCK_MARKER}\n" + "\n\n".join(blocks)


def strip_ref_blocks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop per-turn referenced-session blocks (transient: never persisted)."""
    return [
        m for m in messages
        if not (
            isinstance(m, dict)
            and m.get("role") == "system"
            and isinstance(m.get("content"), str)
            and str(m.get("content")).startswith(REF_BLOCK_MARKER)
        )
    ]


def refresh_linked_block(session: PrepSession, db: Session) -> None:
    """Rewrite the linked-session system block so linking takes effect this turn.

    The seeded system messages (prompt + context blocks) are never touched;
    only the dedicated linked block after the leading system run is replaced.
    Best-effort: a broken history must not fail the link itself.
    """
    try:
        try:
            messages = json.loads(session.messages or "[]")
        except json.JSONDecodeError:
            return
        if not isinstance(messages, list):
            return
        kept = [
            m for m in messages
            if not (
                isinstance(m, dict)
                and m.get("role") == "system"
                and isinstance(m.get("content"), str)
                and m["content"].startswith(LINKED_BLOCK_MARKER)
            )
        ]
        block = format_linked_session(db, session.linked_session_id)
        if block:
            # Anchor after the leading system run (multi-message seeding):
            # the block reads as one more pinned context section.
            anchor = 0
            while (
                anchor < len(kept)
                and isinstance(kept[anchor], dict)
                and kept[anchor].get("role") == "system"
            ):
                anchor += 1
            kept.insert(anchor, {"role": "system", "content": f"{LINKED_BLOCK_MARKER}\n{block}"})
        session.messages = json.dumps(kept, ensure_ascii=False)
        session.updated_at = utcnow()
        commit_session(db)
    except Exception as exc:
        db.rollback()
        logger.warning(
            "Linked-block refresh failed sid=%s: %s",
            session.id, redact_api_key(str(exc)),
        )


__all__ = [
    "LINKED_BLOCK_MARKER",
    "REF_BLOCK_MARKER",
    "format_linked_session",
    "format_linked_sessions",
    "refresh_linked_block",
    "strip_ref_blocks",
]
