"""Persist and mutate the interview session ledger (append / freeze).

Interview is the sole writer. After ``frozen=true``, appends are skipped with a
warning. Persistence matches ``InterviewSessionState.save_state`` (commit).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.interview.ledger.constants import SCHEMA, is_tool_failure_result
from realmock.domains.interview.ledger.preview import truncate_preview
from realmock.domains.interview.ledger.types import LedgerDocument, LedgerTurn, ToolPreview

logger = logging.getLogger(__name__)

PENDING_TOOLS_KEY = "_pending_ledger_tools"
# Max chars of corrupt raw JSON preserved on freeze (avoid unbounded growth).
_CORRUPT_RAW_MAX = 65536


def empty_ledger(session_id: int) -> LedgerDocument:
    """Return a fresh ledger document for ``session_id``."""
    return {
        "schema": SCHEMA,
        "session_id": int(session_id),
        "frozen": False,
        "turns": [],
    }


def load_ledger(session: Any) -> LedgerDocument:
    """Parse ``session.ledger`` JSON.

    On corrupt JSON, returns an empty document marked ``corrupt=True`` and keeps
    a truncated ``raw_unparsed`` so freeze/notify does not silently wipe history.
    """
    session_id = int(getattr(session, "id", 0) or 0)
    raw = getattr(session, "ledger", None) or ""
    raw_str = str(raw)
    if not raw_str.strip() or raw_str.strip() in ("{}", "null"):
        return empty_ledger(session_id)
    try:
        data = json.loads(raw_str)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(
            "corrupt ledger JSON sid=%s err=%s; marking corrupt (raw preserved on freeze)",
            session_id,
            exc,
        )
        doc = empty_ledger(session_id)
        doc["corrupt"] = True
        doc["raw_unparsed"] = raw_str[:_CORRUPT_RAW_MAX]
        return doc
    if not isinstance(data, dict):
        logger.error("ledger root not an object sid=%s; marking corrupt", session_id)
        doc = empty_ledger(session_id)
        doc["corrupt"] = True
        doc["raw_unparsed"] = raw_str[:_CORRUPT_RAW_MAX]
        return doc
    turns = data.get("turns")
    if not isinstance(turns, list):
        turns = []
    out: LedgerDocument = {
        "schema": str(data.get("schema") or SCHEMA),
        "session_id": int(data.get("session_id") or session_id),
        "frozen": bool(data.get("frozen")),
        "turns": turns,
    }
    if data.get("corrupt"):
        out["corrupt"] = True
        if isinstance(data.get("raw_unparsed"), str):
            out["raw_unparsed"] = data["raw_unparsed"][:_CORRUPT_RAW_MAX]
    return out


def save_ledger(db: Session, session: Any, doc: LedgerDocument | dict[str, Any]) -> None:
    """Persist ledger JSON on the session column and commit (like save_state)."""
    session.ledger = json.dumps(doc, ensure_ascii=False)
    db.commit()


def next_turn_id(doc: LedgerDocument | dict[str, Any]) -> str:
    """Allocate the next monotonic turn id (``t-0001``, …)."""
    turns = doc.get("turns") or []
    return f"t-{len(turns) + 1:04d}"


def is_frozen(session: Any) -> bool:
    """Return True when the session ledger is frozen."""
    return bool(load_ledger(session).get("frozen"))


def begin_pending_tools(agent_state: dict[str, Any]) -> list[ToolPreview]:
    """Reset and return the in-memory pending tool preview list for this turn."""
    pending: list[ToolPreview] = []
    agent_state[PENDING_TOOLS_KEY] = pending
    return pending


def append_pending_tool(agent_state: dict[str, Any], tool: ToolPreview | dict[str, Any]) -> None:
    """Append one tool preview onto the pending collector."""
    pending = agent_state.setdefault(PENDING_TOOLS_KEY, [])
    if not isinstance(pending, list):
        pending = []
        agent_state[PENDING_TOOLS_KEY] = pending
    pending.append(tool)  # type: ignore[arg-type]


def take_pending_tools(agent_state: dict[str, Any]) -> list[ToolPreview]:
    """Pop and return pending tool previews (empty list if none)."""
    raw = agent_state.pop(PENDING_TOOLS_KEY, None) or []
    if not isinstance(raw, list):
        return []
    return list(raw)  # type: ignore[arg-type]


def append_turn(
    db: Session,
    session: Any,
    *,
    phase: str,
    assistant_text: str,
    user_text: str | None = None,
    user_source: str = "text",
    tools: list[ToolPreview] | list[dict[str, Any]] | None = None,
    flags: dict[str, Any] | None = None,
    visible: bool = True,
) -> LedgerDocument | None:
    """Append one turn to the ledger and persist.

    Returns the updated document, or None when skipped because ledger is frozen.
    """
    doc = load_ledger(session)
    if doc.get("frozen"):
        logger.warning(
            "ledger frozen; skip append_turn sid=%s phase=%s",
            getattr(session, "id", None),
            phase,
        )
        return None

    turn: LedgerTurn = {
        "turn_id": next_turn_id(doc),
        "phase": phase or "",
        "assistant": {
            "text": assistant_text or "",
            "visible": bool(visible),
        },
        "tools": list(tools or []),
    }
    if user_text is not None:
        turn["user"] = {"text": user_text, "source": user_source or "text"}
    if flags:
        turn["flags"] = dict(flags)

    turns = list(doc.get("turns") or [])
    turns.append(turn)
    doc["turns"] = turns
    doc["schema"] = SCHEMA
    doc["session_id"] = int(getattr(session, "id", 0) or doc.get("session_id") or 0)
    doc["frozen"] = False
    save_ledger(db, session, doc)
    return doc


def freeze_ledger(db: Session, session: Any) -> dict[str, Any]:
    """Set ``frozen=true``, persist, and return the snapshot dict.

    Corrupt ledgers keep ``raw_unparsed`` and ``corrupt=True`` so debrief can
    detect empty turns without destroying the original blob.
    """
    doc = load_ledger(session)
    doc["frozen"] = True
    doc["schema"] = SCHEMA
    doc["session_id"] = int(getattr(session, "id", 0) or doc.get("session_id") or 0)
    if not isinstance(doc.get("turns"), list):
        doc["turns"] = []
    if doc.get("corrupt"):
        logger.error(
            "freezing corrupt ledger sid=%s turns=%d raw_preserved=%s",
            getattr(session, "id", None),
            len(doc.get("turns") or []),
            bool(doc.get("raw_unparsed")),
        )
    save_ledger(db, session, doc)
    return dict(doc)


def build_tool_preview(
    name: str,
    args: dict[str, Any],
    result: str,
    *,
    ok: bool | None = None,
) -> ToolPreview:
    """Build a curtain-layer tool preview from a live tool call.

    ``ok`` defaults to detecting agent-loop failure prefixes when omitted.
    """
    result_text = result if isinstance(result, str) else str(result)
    if ok is None:
        ok = not is_tool_failure_result(result_text)
    return {
        "name": name,
        "args_preview": truncate_preview(args),
        "result_preview": truncate_preview(result_text),
        "ok": bool(ok),
        "chars": len(result_text),
    }


__all__ = [
    "PENDING_TOOLS_KEY",
    "append_pending_tool",
    "append_turn",
    "begin_pending_tools",
    "build_tool_preview",
    "empty_ledger",
    "freeze_ledger",
    "is_frozen",
    "load_ledger",
    "next_turn_id",
    "save_ledger",
    "take_pending_tools",
]
