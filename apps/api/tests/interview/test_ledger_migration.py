# -*- coding: utf-8 -*-
"""Ledger migration acceptance (backfill + column drop).

Simulates a pre-migration database by ALTER-ing the legacy ``ledger`` column
onto the conftest-created table (and removing it again on teardown), then
drives ``backfill_ledger_rows`` / ``drop_legacy_ledger_column``:

- turn counts, turn ids and their JSON payloads survive verbatim;
- the ``frozen`` flag lands on the new column;
- a corrupt blob becomes the reserved seq=0 evidence row;
- both steps are idempotent (second run is a no-op);
- a fresh database without the column skips cleanly.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import inspect, text

from realmock.domains.interview.ledger.migration import (
    backfill_ledger_rows,
    drop_legacy_ledger_column,
)
from realmock.domains.interview.ledger.store import load_ledger
from realmock.domains.interview.models import InterviewSession, InterviewTurn


LEGACY_TURNS = [
    {"turn_id": "t-0001", "phase": "intro", "assistant": {"text": "hi", "visible": True},
     "tools": [], "user": {"text": "hello", "source": "text"}, "flags": {}},
    {"turn_id": "t-0002", "phase": "summary", "assistant": {"text": "bye", "visible": True},
     "tools": []},
]


@pytest.fixture
def legacy_db(db):
    """Sessions DB with the legacy ``ledger`` column re-added; dropped after."""
    if "ledger" not in {c["name"] for c in inspect(db.get_bind()).get_columns("interview_sessions")}:
        db.execute(text("ALTER TABLE interview_sessions ADD COLUMN ledger TEXT DEFAULT '{}'"))
        db.commit()
    yield db
    bind = db.get_bind()
    if "ledger" in {c["name"] for c in inspect(bind).get_columns("interview_sessions")}:
        db.execute(text("ALTER TABLE interview_sessions DROP COLUMN ledger"))
        db.commit()


def _insert_legacy_row(db, blob: str) -> InterviewSession:
    """Insert one session row and write the legacy blob onto its column."""
    row = InterviewSession(
        profile_id=1, role="Backend", level="junior", company="acme",
        workflow_type="technical", status="completed", current_phase="summary",
        messages="[]", agent_state="{}",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    db.execute(
        text("UPDATE interview_sessions SET ledger = :blob WHERE id = :sid").bindparams(
            blob=blob, sid=row.id
        )
    )
    db.commit()
    return row


def test_backfill_copies_turns_and_freeze_flag(legacy_db) -> None:
    blob = json.dumps({
        "schema": "realmock.ledger.v1", "session_id": 0, "frozen": True,
        "turns": LEGACY_TURNS,
    }, ensure_ascii=False)
    row = _insert_legacy_row(legacy_db, blob)

    assert backfill_ledger_rows(legacy_db) == 2

    row = legacy_db.get(InterviewSession, row.id)
    assert row.ledger_frozen is True
    rows = (
        legacy_db.query(InterviewTurn)
        .filter(InterviewTurn.session_id == row.id)
        .order_by(InterviewTurn.seq)
        .all()
    )
    assert [r.seq for r in rows] == [1, 2]
    assert [r.turn_id for r in rows] == ["t-0001", "t-0002"]
    assert [json.loads(r.turn) for r in rows] == LEGACY_TURNS

    # Drop the column; the transcript is intact through the store.
    assert drop_legacy_ledger_column(legacy_db) is True
    assert "ledger" not in {
        c["name"] for c in inspect(legacy_db.get_bind()).get_columns("interview_sessions")
    }
    doc = dict(load_ledger(legacy_db, row))
    assert doc["frozen"] is True
    assert [t["turn_id"] for t in doc["turns"]] == ["t-0001", "t-0002"]


def test_backfill_preserves_corrupt_blob_as_evidence_row(legacy_db) -> None:
    row = _insert_legacy_row(legacy_db, "{corrupt blob")

    assert backfill_ledger_rows(legacy_db) == 1
    row = legacy_db.get(InterviewSession, row.id)
    assert row.ledger_frozen is False
    evidence = (
        legacy_db.query(InterviewTurn)
        .filter(InterviewTurn.session_id == row.id, InterviewTurn.seq == 0)
        .first()
    )
    assert evidence is not None
    payload = json.loads(evidence.turn)
    assert payload["corrupt"] is True
    assert payload["raw_unparsed"] == "{corrupt blob"


def test_backfill_and_drop_are_idempotent(legacy_db) -> None:
    blob = json.dumps({"frozen": False, "turns": LEGACY_TURNS}, ensure_ascii=False)
    row = _insert_legacy_row(legacy_db, blob)

    assert backfill_ledger_rows(legacy_db) == 2
    assert backfill_ledger_rows(legacy_db) == 0  # second run: nothing to do
    assert drop_legacy_ledger_column(legacy_db) is True
    assert drop_legacy_ledger_column(legacy_db) is False  # already gone

    row = legacy_db.get(InterviewSession, row.id)
    doc = dict(load_ledger(legacy_db, row))
    assert len(doc["turns"]) == 2


def test_fresh_database_without_column_is_a_noop(db) -> None:
    # conftest-created table has no legacy column at all.
    assert "ledger" not in {
        c["name"] for c in inspect(db.get_bind()).get_columns("interview_sessions")
    }
    assert backfill_ledger_rows(db) == 0
    assert drop_legacy_ledger_column(db) is False


def test_backfill_empty_turns_frozen_blob_still_sets_flag(legacy_db) -> None:
    """A legitimately empty but frozen blob (finish right after start) must
    persist its frozen flag even though zero turn rows are inserted."""
    blob = json.dumps({"frozen": True, "turns": []}, ensure_ascii=False)
    row = _insert_legacy_row(legacy_db, blob)

    assert backfill_ledger_rows(legacy_db) == 0
    legacy_db.expire_all()
    assert legacy_db.get(InterviewSession, row.id).ledger_frozen is True


def test_backfill_survives_duplicate_and_non_dict_turns(legacy_db) -> None:
    """Duplicate legacy turn_ids fall back to seq ids and non-dict elements
    are normalised to JSON — neither may crash the boot-time migration or
    leave load_ledger permanently broken."""
    blob = json.dumps({
        "frozen": False,
        "turns": [
            {"turn_id": "t-0001", "phase": "p", "assistant": {"text": "a"}},
            {"turn_id": "t-0001", "phase": "p", "assistant": {"text": "b"}},
            "raw string turn",
        ],
    }, ensure_ascii=False)
    row = _insert_legacy_row(legacy_db, blob)

    assert backfill_ledger_rows(legacy_db) == 3
    doc = dict(load_ledger(legacy_db, row))
    # The third element is a legacy raw string; load_ledger passes it through
    # verbatim (only dict turns carry ids).
    ids = [t.get("turn_id") if isinstance(t, dict) else None for t in doc["turns"]]
    assert ids == ["t-0001", "t-0002", None]
    assert doc["turns"][2] == "raw string turn"  # normalised verbatim as JSON text

def test_drop_skips_on_old_sqlite(legacy_db, monkeypatch) -> None:
    """Engines older than 3.35 keep the column and report not-dropped."""
    import sqlite3

    class _OldVersion:
        sqlite_version = "3.31.1"

    monkeypatch.setattr(sqlite3, "sqlite_version", "3.31.1")
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 31, 1))
    del _OldVersion
    assert drop_legacy_ledger_column(legacy_db) is False
    assert "ledger" in {
        c["name"]
        for c in inspect(legacy_db.get_bind()).get_columns("interview_sessions")
    }


def test_backfill_non_dict_root_becomes_evidence_row(legacy_db) -> None:
    """A legacy blob whose root is a JSON array must not be dropped on the
    floor: it lands as the reserved evidence row with frozen=False."""
    row = _insert_legacy_row(legacy_db, "[1, 2, 3]")

    assert backfill_ledger_rows(legacy_db) == 1
    legacy_db.expire_all()
    fresh = legacy_db.get(InterviewSession, row.id)
    assert fresh.ledger_frozen is False
    evidence = (
        legacy_db.query(InterviewTurn)
        .filter(InterviewTurn.session_id == row.id, InterviewTurn.seq == 0)
        .first()
    )
    assert evidence is not None
    assert json.loads(evidence.turn)["raw_unparsed"] == "[1, 2, 3]"


def test_column_helpers_report_missing_table(db, monkeypatch) -> None:
    from realmock.domains.interview.ledger.migration import (
        _column_exists,
        _table_exists,
    )

    bind = db.get_bind()
    assert _table_exists(bind, "definitely_not_a_table") is False
    assert _column_exists(bind, "definitely_not_a_table", "any") is False
