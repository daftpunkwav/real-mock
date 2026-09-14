"""Cross-round record retrieval: search and page through prior-round ledgers.

Backs the interviewer's ``search_past_interviews`` / ``read_past_round``
tools so later rounds can ground questions in earlier ones on demand instead
of relying only on the condensed process memory.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.interview.models import InterviewSession

logger = logging.getLogger(__name__)

_SEARCH_TURN_LIMIT = 8
_SNIPPET_CHARS = 200
_READ_PAGE_TURNS = 12
_READ_TURN_CHARS = 700


def _load_ledger(session: InterviewSession) -> list[dict[str, Any]]:
    try:
        ledger = json.loads(session.ledger or "{}")
    except (json.JSONDecodeError, TypeError):
        return []
    turns = ledger.get("turns") if isinstance(ledger, dict) else None
    return [t for t in turns if isinstance(t, dict)] if isinstance(turns, list) else []


def prior_round_sessions(
    db: Session, session: InterviewSession
) -> list[InterviewSession]:
    """Completed earlier rounds of the same process, oldest first."""
    process_id = getattr(session, "process_id", None)
    round_no = getattr(session, "round_no", None)
    if not process_id or not round_no or round_no <= 1:
        return []
    return (
        db.query(InterviewSession)
        .filter(
            InterviewSession.process_id == process_id,
            InterviewSession.round_no < round_no,
            InterviewSession.status == "completed",
        )
        .order_by(InterviewSession.round_no.asc())
        .all()
    )


def has_prior_rounds(db: Session, session: InterviewSession) -> bool:
    return bool(prior_round_sessions(db, session))


def _turn_text(turn: dict[str, Any]) -> str:
    """Flatten a ledger turn's assistant/user payloads into lowercase text."""
    parts: list[str] = []
    for key in ("assistant", "user"):
        val = turn.get(key)
        if isinstance(val, dict):
            parts.append(str(val.get("text", "")))
        elif val:
            parts.append(str(val))
    return " ".join(parts).lower()


def search_past_interviews(db: Session, session: InterviewSession, query: str) -> str:
    """Keyword search over prior-round ledgers; returns bounded JSON."""
    q = (query or "").strip().lower()
    if not q:
        return json.dumps({"error": "empty_query"}, ensure_ascii=False)
    keywords = [w for w in q.split() if w] or [q]
    hits: list[dict[str, Any]] = []
    for row in prior_round_sessions(db, session):
        for turn in _load_ledger(row):
            haystack = _turn_text(turn)
            score = sum(1 for kw in keywords if kw in haystack)
            if not score:
                continue
            assistant = turn.get("assistant") or {}
            user = turn.get("user") or {}
            hits.append({
                "round_no": row.round_no,
                "turn_id": turn.get("turn_id"),
                "question": str(assistant.get("text", ""))[:_SNIPPET_CHARS],
                "answer": str(user.get("text", ""))[:_SNIPPET_CHARS],
                "score": score,
            })
    hits.sort(key=lambda h: (-h["score"], h["round_no"]))
    return json.dumps({"matches": hits[:_SEARCH_TURN_LIMIT]}, ensure_ascii=False)


def read_past_round(
    db: Session, session: InterviewSession, round_no: int, offset: int = 0
) -> str:
    """Page through one prior round's transcript (bounded turns per page)."""
    round_no = int(round_no or 0)
    rows = {
        row.round_no: row for row in prior_round_sessions(db, session)
    }
    row = rows.get(round_no)
    if row is None:
        return json.dumps(
            {"error": "round_not_found", "available": sorted(rows.keys())},
            ensure_ascii=False,
        )
    turns = _load_ledger(row)
    offset = max(0, int(offset or 0))
    page = turns[offset : offset + _READ_PAGE_TURNS]
    items = []
    for turn in page:
        assistant = turn.get("assistant") or {}
        user = turn.get("user") or {}
        items.append({
            "turn_id": turn.get("turn_id"),
            "question": str(assistant.get("text", ""))[:_READ_TURN_CHARS],
            "answer": str(user.get("text", ""))[:_READ_TURN_CHARS],
        })
    return json.dumps(
        {
            "round_no": round_no,
            "offset": offset,
            "total_turns": len(turns),
            "next_offset": offset + len(page) if offset + len(page) < len(turns) else None,
            "turns": items,
        },
        ensure_ascii=False,
    )


__all__ = [
    "has_prior_rounds",
    "prior_round_sessions",
    "read_past_round",
    "search_past_interviews",
]
