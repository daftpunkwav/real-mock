"""One-time migration of the legacy ledger blob into ``interview_turns``.

Order matters and is idempotent (safe to re-run on every boot):

1. backfill: for every session whose turn table is empty, read the legacy
   ``interview_sessions.ledger`` column **via raw SQL** (the ORM no longer
   maps it), insert one row per turn plus the reserved ``seq=0`` evidence
   row for corrupt blobs, and set ``ledger_frozen`` from the blob flag;
2. drop: physically ``ALTER TABLE interview_sessions DROP COLUMN ledger``.

``DROP COLUMN`` needs SQLite >= 3.35 (verified 3.50 on the dev machine).
Both steps skip cleanly when the table/column do not exist (fresh databases
created by ``create_all`` already have the final shape).
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from realmock.domains.interview.models import InterviewTurn

logger = logging.getLogger(__name__)

_CORRUPT_SEQ = 0
_CORRUPT_TURN_ID = "t-0000"
_CORRUPT_RAW_MAX = 65536


def _table_exists(engine, table: str) -> bool:
    return inspect(engine).has_table(table)


def _column_exists(engine, table: str, column: str) -> bool:
    if not _table_exists(engine, table):
        return False
    return column in {c["name"] for c in inspect(engine).get_columns(table)}


def _derive_turn_id(base: str, seen: set[str]) -> str:
    # The seq-derived fallback can itself equal an earlier id (a duplicate AT
    # its own index, or a non-dict element behind a dict carrying that id);
    # disambiguate deterministically within the column width instead of
    # tripping the UNIQUE constraint at commit — that would turn the boot
    # migration into a crash loop.
    turn_id = base
    n = 2
    while turn_id in seen:
        turn_id = f"{base[:11]}#{n}"
        n += 1
    return turn_id


def backfill_ledger_rows(db: Session) -> int:
    """Copy legacy ``ledger`` blobs into ``interview_turns``; returns row count.

    Idempotent: sessions that already have turn rows are skipped, and empty /
    ``{}`` / ``null`` blobs are ignored. Corrupt blobs land as the reserved
    ``seq=0`` evidence row so the corruption survives the column drop.
    """
    bind = db.get_bind()
    if not _column_exists(bind, "interview_sessions", "ledger"):
        return 0
    legacy_rows = db.execute(
        text("SELECT id, ledger FROM interview_sessions WHERE ledger IS NOT NULL")
    ).fetchall()
    existing_ids = {
        row[0]
        for row in db.query(InterviewTurn.session_id).distinct().all()
    }
    inserted = 0
    dirty = False  # any write (row OR frozen-flag UPDATE) must be committed
    for session_id, blob in legacy_rows:
        sid = int(session_id)
        if sid in existing_ids:
            continue
        blob = str(blob or "")
        if not blob.strip() or blob.strip() in ("{}", "null"):
            continue
        try:
            data = json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            db.add(_evidence_row(sid, blob))
            inserted += 1
            dirty = True
            _set_frozen(db, sid, _blob_frozen_flag(blob))
            continue
        if not isinstance(data, dict):
            db.add(_evidence_row(sid, blob))
            inserted += 1
            dirty = True
            _set_frozen(db, sid, False)
            continue
        turns = data.get("turns")
        if not isinstance(turns, list):
            turns = []
        seen_turn_ids: set[str] = set()
        for seq, turn in enumerate(turns, start=1):
            # Normalise every element to its JSON text (a raw str element
            # would land in the column unquoted and break load_ledger), and
            # fall back to the seq-derived id when a legacy blob carries a
            # duplicate turn_id — the UNIQUE constraint must never turn a
            # boot-time migration into a crash loop.
            if isinstance(turn, dict):
                turn_id = str(turn.get("turn_id") or "").strip()
                if not turn_id or turn_id in seen_turn_ids:
                    turn_id = _derive_turn_id(f"t-{seq:04d}", seen_turn_ids)
                # Keep the payload's inner turn_id consistent with the column:
                turn["turn_id"] = turn_id
                payload = json.dumps(turn, ensure_ascii=False)
            else:
                turn_id = _derive_turn_id(f"t-{seq:04d}", seen_turn_ids)
                payload = json.dumps(turn, ensure_ascii=False)
            seen_turn_ids.add(turn_id)
            db.add(
                InterviewTurn(
                    session_id=sid,
                    turn_id=turn_id,
                    seq=seq,
                    turn=payload,
                )
            )
        if data.get("corrupt"):
            raw = data.get("raw_unparsed")
            db.add(_evidence_row(sid, raw if isinstance(raw, str) else blob))
        _set_frozen(db, sid, bool(data.get("frozen")))
        inserted += len(turns)
        dirty = True
    if dirty:
        db.commit()
        logger.info("ledger backfill complete: %d turn rows inserted", inserted)
    return inserted


def _set_frozen(db: Session, session_id: int, frozen: bool) -> None:
    db.execute(
        text(
            "UPDATE interview_sessions SET ledger_frozen = :frozen WHERE id = :sid"
        ).bindparams(frozen=int(frozen), sid=session_id)
    )


def _blob_frozen_flag(blob: str) -> bool:
    try:
        data = json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return False
    return bool(data.get("frozen")) if isinstance(data, dict) else False


def _evidence_row(session_id: int, raw: str) -> InterviewTurn:
    return InterviewTurn(
        session_id=session_id,
        turn_id=_CORRUPT_TURN_ID,
        seq=_CORRUPT_SEQ,
        turn=json.dumps({"corrupt": True, "raw_unparsed": raw[:_CORRUPT_RAW_MAX]}),
    )


def drop_legacy_ledger_column(db: Session) -> bool:
    """Physically drop ``interview_sessions.ledger``; True when dropped.

    Requires SQLite >= 3.35 for ``DROP COLUMN``: older engines are skipped
    with a warning (the column stays, the backfill stays idempotent, and
    the system keeps working). Must run AFTER
    :func:`backfill_ledger_rows`. Skips when the column is
    already gone (fresh databases created by the current ``create_all``).
    """
    bind = db.get_bind()
    if not _column_exists(bind, "interview_sessions", "ledger"):
        return False
    import sqlite3

    if tuple(int(x) for x in sqlite3.sqlite_version.split(".")[:2]) < (3, 35):
        logger.warning(
            "SQLite %s cannot DROP COLUMN (needs >= 3.35); the legacy "
            "interview_sessions.ledger column is kept and will be retried "
            "on the next boot",
            sqlite3.sqlite_version,
        )
        return False
    db.execute(text("ALTER TABLE interview_sessions DROP COLUMN ledger"))
    db.commit()
    logger.info("legacy interview_sessions.ledger column dropped")
    return True


__all__ = ["backfill_ledger_rows", "drop_legacy_ledger_column"]
