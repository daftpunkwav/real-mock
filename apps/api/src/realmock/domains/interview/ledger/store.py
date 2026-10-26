"""Persist and mutate the interview session ledger (per-turn table).

The ledger is stored as one ``interview_turns`` row per turn (O(1) appends,
explicit per-session sequence instead of ``len(turns)+1``) plus a first-class
``interview_sessions.ledger_frozen`` boolean, so freezing and list reads never
parse a JSON blob. ``load_ledger`` aggregates the rows back into the historic
``LedgerDocument`` dict shape — downstream consumers (records domain) keep
their ``{"turns": [...]}`` contract unchanged.

Legacy migration: a non-empty ``session.ledger`` blob is only read as a
fallback when the turn table has no rows for the session (pre-backfill
databases); bootstrap copies the blob into the table and drops the column
(see :mod:`realmock.domains.interview.ledger.migration`).

Interview is the sole writer. After ``ledger_frozen=true``, appends are
skipped with a warning. Persistence matches ``save_state`` (commit).
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from sqlalchemy.orm import Session

from realmock.domains.interview.ledger.constants import (
    CORRUPT_RAW_MAX,
    CORRUPT_SEQ,
    SCHEMA,
    is_tool_failure_result,
)
from realmock.domains.interview.ledger.preview import truncate_preview
from realmock.domains.interview.ledger.types import LedgerDocument, LedgerTurn, ToolPreview
from realmock.domains.interview.models import InterviewTurn

logger = logging.getLogger(__name__)

PENDING_TOOLS_KEY = "_pending_ledger_tools"


def empty_ledger(session_id: int) -> LedgerDocument:
    """Return a fresh ledger document for ``session_id``."""
    return {
        "schema": SCHEMA,
        "session_id": int(session_id),
        "frozen": False,
        "turns": [],
    }


def _turn_rows(db: Session, session_id: int) -> list[InterviewTurn]:
    """Turn rows for one session ordered by append sequence."""
    return (
        db.query(InterviewTurn)
        .filter(InterviewTurn.session_id == session_id)
        .order_by(InterviewTurn.seq)
        .all()
    )


# The report reader of an earlier release looked the tool result up under
# ``result`` instead of the declared ``result_preview``. A stored preview can
# carry that key; rename it on read so a reader sees the result text instead
# of projecting an empty preview.
_LEGACY_PREVIEW_KEY = "result"
_DECLARED_PREVIEW_KEY = "result_preview"


def _drop_tools(turn: dict[str, Any]) -> LedgerTurn:
    """Return the turn without its ``tools`` key."""
    normalized = dict(turn)
    normalized.pop("tools", None)
    return cast("LedgerTurn", normalized)


def _normalize_tool_preview(value: Any) -> ToolPreview | None:
    """Return one stored preview under the declared key names.

    ``None`` means the value is not a mapping and cannot become a preview.
    """
    if not isinstance(value, dict):
        return None
    preview = dict(value)
    if _LEGACY_PREVIEW_KEY in preview:
        # The declared key wins when both are present; the legacy key is
        # dropped either way so a published preview has one result field.
        preview.setdefault(_DECLARED_PREVIEW_KEY, preview.pop(_LEGACY_PREVIEW_KEY))
    return cast("ToolPreview", preview)


def _normalize_tool_previews(raw_tools: list[Any]) -> tuple[list[ToolPreview], bool]:
    """Return publishable previews and whether a non-null entry was dropped.

    A JSON ``null`` slot carries no tool data, so dropping it is not content
    loss and does not flag the document corrupt.
    """
    candidates = [item for item in raw_tools if item is not None]
    previews = [
        preview for item in candidates if (preview := _normalize_tool_preview(item)) is not None
    ]
    return previews, len(previews) != len(candidates)


def _normalize_turn(turn: dict[str, Any]) -> tuple[LedgerTurn, bool]:
    """Publish one stored turn under the declared tool-preview shape.

    The storage writer produces the declared keys, but a legacy or hand-edited
    row can carry a preview under a key the contract does not declare, or a
    ``tools`` value that is not a list of mappings. Readers key their lookups
    on the contract, so previews are normalized here and entries that cannot
    be previews are dropped. The boolean reports whether content was dropped;
    the caller marks the document corrupt in that case instead of losing the
    evidence silently.
    """
    raw_tools = turn.get("tools")
    if raw_tools is None:
        # JSON null is not a preview list: drop the key (no content is lost)
        # so the published turn matches the declared optional shape.
        return _drop_tools(turn), False
    if not isinstance(raw_tools, list):
        return _drop_tools(turn), True
    previews, dropped = _normalize_tool_previews(raw_tools)
    normalized = dict(turn)
    normalized["tools"] = previews
    return cast("LedgerTurn", normalized), dropped


def _doc_from_rows(session_id: int, rows: list[InterviewTurn], *, frozen: bool) -> LedgerDocument:
    doc: LedgerDocument = {
        "schema": SCHEMA,
        "session_id": int(session_id),
        "frozen": bool(frozen),
        "turns": [],
    }
    # One corrupt turn row (hand-edited DB, torn write) must degrade to a
    # skipped turn, not kill every read of the session's ledger.
    for r in rows:
        if r.seq == CORRUPT_SEQ:
            try:
                evidence = json.loads(r.turn)
            except json.JSONDecodeError:
                continue
            if isinstance(evidence, dict) and evidence.get("corrupt"):
                doc["corrupt"] = True
                if isinstance(evidence.get("raw_unparsed"), str):
                    doc["raw_unparsed"] = evidence["raw_unparsed"][:CORRUPT_RAW_MAX]
            continue
        try:
            turn = json.loads(r.turn)
        except (json.JSONDecodeError, TypeError):
            doc["corrupt"] = True
            logger.warning(
                "ledger turn row unparsable sid=%s seq=%s; skipped",
                session_id,
                r.seq,
            )
            continue
        if not isinstance(turn, dict):
            # A legacy migrated blob can hold a non-mapping element (a raw
            # string turn). The document contract types every turn as a
            # mapping, so the row is not published as a turn; the corrupt flag
            # records that the document omits stored content.
            doc["corrupt"] = True
            logger.warning(
                "ledger turn row not a mapping sid=%s seq=%s; skipped",
                session_id,
                r.seq,
            )
            continue
        turn_doc, dropped = _normalize_turn(turn)
        if dropped:
            doc["corrupt"] = True
            logger.warning(
                "ledger turn row lost tool previews sid=%s seq=%s",
                session_id,
                r.seq,
            )
        doc["turns"].append(turn_doc)
    return doc


def load_ledger(db: Session, session: Any) -> LedgerDocument:
    """Aggregate the session's ledger document from the turn table."""
    session_id = int(getattr(session, "id", 0) or 0)
    rows = _turn_rows(db, session_id)
    frozen = bool(getattr(session, "ledger_frozen", False))
    return _doc_from_rows(session_id, rows, frozen=frozen)


def _next_seq(db: Session, session_id: int) -> tuple[int, str]:
    """Next append sequence and turn id (``t-0001``, …) for the session."""
    max_seq = (
        db.query(InterviewTurn.seq)
        .filter(
            InterviewTurn.session_id == session_id,
            InterviewTurn.seq != CORRUPT_SEQ,
        )
        .order_by(InterviewTurn.seq.desc())
        .first()
    )
    seq = (max_seq[0] if max_seq else 0) + 1
    return seq, f"t-{seq:04d}"


def is_frozen(session: Any) -> bool:
    """Return True when the session ledger is frozen (column read, no JSON)."""
    return bool(getattr(session, "ledger_frozen", False))


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


def append_turn_row(
    db: Session,
    session: Any,
    *,
    phase: str,
    assistant_text: str,
    user_text: str | None = None,
    user_source: str = "text",
    tools: list[ToolPreview] | None = None,
    flags: dict[str, Any] | None = None,
    visible: bool = True,
) -> str | None:
    """Append one turn as a single row and persist.

    Returns the new turn id, or None when the append was skipped because the
    ledger is frozen. The caller gets no document back on purpose: rebuilding
    it means re-reading and re-parsing every turn of the session, which turns
    a session of T turns into O(T^2) JSON parses. Read the aggregated document
    with :func:`load_ledger` when it is actually needed.
    """
    session_id = int(getattr(session, "id", 0) or 0)
    if is_frozen(session):
        logger.warning(
            "ledger frozen; skip append_turn_row sid=%s phase=%s",
            session_id,
            phase,
        )
        return None

    seq, turn_id = _next_seq(db, session_id)
    turn: LedgerTurn = {
        "turn_id": turn_id,
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

    db.add(
        InterviewTurn(
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            turn=json.dumps(turn, ensure_ascii=False),
        )
    )
    db.commit()
    return turn_id


def append_last_turn_flag(
    db: Session,
    session: Any,
    key: str,
    value: Any,
) -> None:
    """Merge one flag into the newest ledger turn and persist.

    Used by the realtime layer for events that happen against the current
    question but outside the runner (e.g. silence probes), so the report
    sees them against the turn they belong to. No-op when frozen or when
    the ledger has no turns. The flag write is a single-row UPDATE — it can
    no longer clobber concurrent appends with a stale blob snapshot.
    """
    session_id = int(getattr(session, "id", 0) or 0)
    if is_frozen(session):
        logger.warning(
            "ledger frozen; skip append_last_turn_flag sid=%s key=%s",
            session_id,
            key,
        )
        return
    # Only the newest turn is annotated: read that one row instead of the
    # whole turn table, whose JSON bodies would be loaded for nothing.
    row = (
        db.query(InterviewTurn)
        .filter(
            InterviewTurn.session_id == session_id,
            InterviewTurn.seq != CORRUPT_SEQ,
        )
        .order_by(InterviewTurn.seq.desc())
        .first()
    )
    if row is None:
        return
    try:
        turn = json.loads(row.turn)
    except (json.JSONDecodeError, TypeError):
        # A corrupt newest row cannot take a flag; skipping beats failing the
        # realtime event that merely wanted to annotate it.
        logger.warning(
            "ledger newest turn unparsable sid=%s seq=%s; flag %s skipped",
            session_id,
            row.seq,
            key,
        )
        return
    if not isinstance(turn, dict):
        return
    flags = turn.get("flags")
    if not isinstance(flags, dict):
        flags = {}
    flags[key] = value
    turn["flags"] = flags
    row.turn = json.dumps(turn, ensure_ascii=False)
    db.commit()


def freeze_ledger(db: Session, session: Any) -> dict[str, Any]:
    """Set ``ledger_frozen=true``, persist, and return the snapshot dict.

    Corrupt-ledger evidence (``raw_unparsed`` from the legacy blob era) lives
    in its reserved turn row (written once by the migration), so debrief can
    still detect empty turns.
    """
    session_id = int(getattr(session, "id", 0) or 0)
    session.ledger_frozen = True
    db.commit()
    doc = load_ledger(db, session)
    doc["frozen"] = True
    if not isinstance(doc.get("turns"), list):
        doc["turns"] = []
    if doc.get("corrupt"):
        logger.error(
            "freezing corrupt ledger sid=%s turns=%d raw_preserved=%s",
            session_id,
            len(doc.get("turns") or []),
            bool(doc.get("raw_unparsed")),
        )
    return dict(doc)


def build_tool_preview(
    name: str,
    args: dict[str, Any],
    result: str,
    *,
    ok: bool | None = None,
) -> ToolPreview:
    """Build the ledger tool preview (truncated args / result) from a live tool call.

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
    "append_last_turn_flag",
    "append_pending_tool",
    "append_turn_row",
    "begin_pending_tools",
    "build_tool_preview",
    "empty_ledger",
    "freeze_ledger",
    "is_frozen",
    "load_ledger",
    "take_pending_tools",
]
