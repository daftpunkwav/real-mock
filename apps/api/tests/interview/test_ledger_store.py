# -*- coding: utf-8 -*-
"""Ledger store tests for src/realmock/domains/interview/ledger/store.py.

The ledger is per-turn rows (``interview_turns``) plus the
``ledger_frozen`` column; ``load_ledger`` aggregates them back into the
historic document shape. Persistence-touching cases run against the real
file-backed sessions DB (conftest ``db`` fixture). Pure parsing/shape
helpers stay on lightweight stubs.
"""

from __future__ import annotations

import json

from realmock.domains.interview.ledger.store import (
    append_last_turn_flag,
    append_pending_tool,
    append_turn,
    begin_pending_tools,
    build_tool_preview,
    empty_ledger,
    freeze_ledger,
    is_frozen,
    load_ledger,
    take_pending_tools,
)
from realmock.domains.interview.models import InterviewSession, InterviewTurn



def _row(db, **overrides) -> InterviewSession:
    base = {
        "profile_id": 1,
        "role": "Backend",
        "level": "junior",
        "company": "acme",
        "workflow_type": "technical",
        "status": "active",
        "current_phase": "summary",
        "messages": json.dumps([{"role": "user", "content": "hi"}]),
    }
    base.update(overrides)
    row = InterviewSession(**base)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _reload(db, row) -> InterviewSession:
    db.expire_all()
    return db.query(InterviewSession).filter(InterviewSession.id == row.id).first()


def _turns(db, session_id: int) -> list[dict]:
    rows = (
        db.query(InterviewTurn)
        .filter(InterviewTurn.session_id == session_id)
        .order_by(InterviewTurn.seq)
        .all()
    )
    return [json.loads(r.turn) for r in rows if r.seq != 0]


# ---- pure helpers ----


def test_empty_ledger_shape() -> None:
    doc = empty_ledger(9)
    assert doc["session_id"] == 9
    assert doc["frozen"] is False
    assert doc["turns"] == []


def test_pending_tools_lifecycle() -> None:
    state: dict = {}
    pending = begin_pending_tools(state)
    assert pending == []
    append_pending_tool(state, {"name": "t"})
    assert len(state["_pending_ledger_tools"]) == 1
    # Non-list collector is reset, not crashed.
    state["_pending_ledger_tools"] = "garbage"
    append_pending_tool(state, {"name": "t2"})
    assert state["_pending_ledger_tools"] == [{"name": "t2"}]
    out = take_pending_tools(state)
    assert out == [{"name": "t2"}]
    assert "_pending_ledger_tools" not in state
    # Pop non-list returns [].
    state["_pending_ledger_tools"] = "garbage"
    assert take_pending_tools(state) == []


def test_build_tool_preview_ok_autodetect() -> None:
    ok = build_tool_preview("t", {"a": 1}, "fine result")
    assert ok["ok"] is True
    assert ok["chars"] == len("fine result")
    assert ok["name"] == "t"
    bad = build_tool_preview("t", {}, "Tool execution failed: boom")
    assert bad["ok"] is False
    explicit = build_tool_preview("t", {}, "whatever", ok=True)
    assert explicit["ok"] is True
    non_str = build_tool_preview("t", {}, {"x": 1})  # type: ignore[arg-type]
    assert non_str["chars"] == len(str({"x": 1}))


# ---- persistence (real DB, per-turn rows) ----


def test_append_turn_persists_rows_and_increments_ids(db) -> None:
    row = _row(db)
    doc = append_turn(
        db,
        row,
        phase="intro",
        assistant_text="hello",
        user_text="hi",
        user_source="voice",
        tools=[{"name": "t"}],
        flags={"k": "v"},
        visible=False,
    )
    assert doc is not None
    turn = doc["turns"][0]
    assert turn["turn_id"] == "t-0001"
    assert turn["assistant"] == {"text": "hello", "visible": False}
    assert turn["user"] == {"text": "hi", "source": "voice"}
    assert turn["flags"] == {"k": "v"}
    # Second append increments the id from the explicit sequence.
    doc2 = append_turn(db, row, phase="p", assistant_text="q2")
    assert doc2 is not None
    assert doc2["turns"][-1]["turn_id"] == "t-0002"
    assert "user" not in doc2["turns"][-1]
    # Both turns survive a full reload from the table.
    reloaded = load_ledger(db, _reload(db, row))
    assert [t["turn_id"] for t in reloaded["turns"]] == ["t-0001", "t-0002"]
    assert reloaded["turns"][0]["flags"] == {"k": "v"}
    # Rows carry an explicit monotonic seq.
    seqs = [
        r.seq
        for r in db.query(InterviewTurn)
        .filter(InterviewTurn.session_id == row.id)
        .order_by(InterviewTurn.seq)
        .all()
    ]
    assert seqs == [1, 2]


def test_append_turn_skipped_when_frozen(db) -> None:
    row = _row(db)
    row.ledger_frozen = True
    db.commit()
    assert append_turn(db, row, phase="p", assistant_text="x") is None
    assert is_frozen(_reload(db, row)) is True
    assert _turns(db, row.id) == []


def test_append_last_turn_flag_updates_newest_turn_only(db) -> None:
    row = _row(db)
    append_turn(db, row, phase="p", assistant_text="a1")
    append_turn(db, row, phase="p", assistant_text="a2")
    # Non-dict flags on the newest turn are reset to a dict, not crashed on.
    append_last_turn_flag(db, row, "k", "v")
    doc = load_ledger(db, _reload(db, row))
    assert doc["turns"][0].get("flags") is None
    assert doc["turns"][1]["flags"] == {"k": "v"}


def test_append_last_turn_flag_noop_without_turns(db) -> None:
    row = _row(db)
    append_last_turn_flag(db, row, "k", "v")  # no turns: silent no-op
    assert _turns(db, row.id) == []


def test_freeze_ledger_sets_column_and_is_idempotent(db) -> None:
    row = _row(db)
    append_turn(db, row, phase="p", assistant_text="a1")
    out = freeze_ledger(db, row)
    assert out["frozen"] is True
    assert is_frozen(_reload(db, row)) is True
    # Idempotent: freezing again keeps the turns.
    out2 = freeze_ledger(db, _reload(db, row))
    assert out2["frozen"] is True
    assert len(out2["turns"]) == 1

def test_load_ledger_rebuilds_corrupt_evidence_row(db) -> None:
    """The migration writes corrupt blobs as the reserved seq=0 row;
    load_ledger must surface it back as corrupt/raw_unparsed."""
    row = _row(db)
    evidence = json.dumps({"corrupt": True, "raw_unparsed": "x" * 40}, ensure_ascii=False)
    db.add(
        InterviewTurn(
            session_id=row.id,
            turn_id="t-0000",
            seq=0,
            turn=evidence,
        )
    )
    db.commit()

    doc = load_ledger(db, _reload(db, row))
    assert doc.get("corrupt") is True
    assert doc.get("raw_unparsed") == "x" * 40
    assert doc["turns"] == []


def test_freeze_ledger_logs_and_keeps_corrupt_evidence(db) -> None:
    """Freezing a ledger with preserved corruption keeps the evidence."""
    row = _row(db)
    evidence = json.dumps({"corrupt": True, "raw_unparsed": "orig blob"}, ensure_ascii=False)
    db.add(
        InterviewTurn(
            session_id=row.id,
            turn_id="t-0000",
            seq=0,
            turn=evidence,
        )
    )
    db.commit()

    out = freeze_ledger(db, row)
    assert out["frozen"] is True
    assert out.get("corrupt") is True
    assert out.get("raw_unparsed") == "orig blob"
