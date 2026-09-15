"""Ledger store tests for src/realmock/domains/interview/ledger/store.py.

Covers: empty/load/save/frozen/pending/append/freeze/preview branches
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
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
    next_turn_id,
    save_ledger,
    take_pending_tools,
)
from realmock.domains.interview.models import InterviewSession
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def _db() -> MagicMock:
    return MagicMock()


def _session_doc(doc: dict) -> SimpleNamespace:
    return SimpleNamespace(id=7, ledger=json.dumps(doc))


def _db_session(db, **overrides) -> InterviewSession:
    base = {
        "profile_id": 1,
        "role": "Backend",
        "level": "junior",
        "company": "acme",
        "workflow_type": "technical",
        "status": "completed",
        "current_phase": "summary",
        "messages": json.dumps([{"role": "user", "content": "hi"}]),
        "ledger": json.dumps(empty_ledger(0)),
    }
    base.update(overrides)
    row = InterviewSession(**base)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---- ledger store ----


def test_empty_ledger_shape() -> None:
    doc = empty_ledger(9)
    assert doc["session_id"] == 9
    assert doc["frozen"] is False
    assert doc["turns"] == []


def test_load_ledger_empty_variants() -> None:
    assert load_ledger(SimpleNamespace(id=1, ledger=""))["turns"] == []
    assert load_ledger(SimpleNamespace(id=1, ledger="{}"))["turns"] == []
    assert load_ledger(SimpleNamespace(id=1, ledger="null"))["turns"] == []
    assert load_ledger(SimpleNamespace(id=1))["turns"] == []


def test_load_ledger_corrupt_marks_raw() -> None:
    doc = load_ledger(SimpleNamespace(id=3, ledger="{bad json"))
    assert doc.get("corrupt") is True
    assert "raw_unparsed" in doc
    assert doc["session_id"] == 3


def test_load_ledger_non_dict_root_marks_corrupt() -> None:
    doc = load_ledger(SimpleNamespace(id=4, ledger="[1,2]"))
    assert doc.get("corrupt") is True
    assert doc["turns"] == []


def test_load_ledger_non_list_turns_coerced() -> None:
    raw = json.dumps({"schema": "x", "session_id": 5, "frozen": False, "turns": {"a": 1}})
    doc = load_ledger(SimpleNamespace(id=5, ledger=raw))
    assert doc["turns"] == []
    assert doc["schema"] == "x"


def test_load_ledger_keeps_corrupt_flag_and_truncates() -> None:
    raw = json.dumps({"turns": [], "corrupt": True, "raw_unparsed": "z" * 10})
    doc = load_ledger(SimpleNamespace(id=6, ledger=raw))
    assert doc.get("corrupt") is True
    assert doc["raw_unparsed"] == "z" * 10


def test_save_and_next_turn_id() -> None:
    db = _db()
    sess = SimpleNamespace(id=11, ledger="")
    save_ledger(db, sess, empty_ledger(11))
    assert json.loads(sess.ledger)["session_id"] == 11
    assert next_turn_id({"turns": []}) == "t-0001"
    assert next_turn_id({"turns": [{}, {}]}) == "t-0003"
    assert next_turn_id({}) == "t-0001"
    db.commit.assert_called_once()


def test_is_frozen_true_false() -> None:
    assert is_frozen(_session_doc({**empty_ledger(7), "frozen": True})) is True
    assert is_frozen(_session_doc(empty_ledger(7))) is False


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


def test_append_turn_ok_with_user_flags_invisible() -> None:
    db = _db()
    sess = _session_doc(empty_ledger(7))
    doc = append_turn(
        db,
        sess,
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
    # Second append increments id.
    doc2 = append_turn(db, sess, phase="p", assistant_text="q2")
    assert doc2 is not None
    assert doc2["turns"][-1]["turn_id"] == "t-0002"
    assert "user" not in doc2["turns"][-1]


def test_append_turn_skipped_when_frozen() -> None:
    db = _db()
    sess = _session_doc({**empty_ledger(7), "frozen": True})
    assert append_turn(db, sess, phase="p", assistant_text="x") is None
    db.commit.assert_not_called()


def test_append_last_turn_flag_non_dict_flags_reset() -> None:
    doc = empty_ledger(7)
    doc["turns"] = [{"turn_id": "t-0001", "flags": ["bad"]}]
    sess = _session_doc(doc)
    append_last_turn_flag(_db(), sess, "k", "v")
    assert json.loads(sess.ledger)["turns"][0]["flags"] == {"k": "v"}


def test_freeze_ledger_marks_and_keeps_corrupt() -> None:
    db = _db()
    raw = json.dumps({"turns": [], "corrupt": True, "raw_unparsed": "orig"})
    sess = SimpleNamespace(id=8, ledger=raw)
    out = freeze_ledger(db, sess)
    assert out["frozen"] is True
    assert out.get("corrupt") is True
    assert out["raw_unparsed"] == "orig"


def test_freeze_ledger_coerces_non_list_turns() -> None:
    db = _db()
    sess = SimpleNamespace(id=8, ledger=json.dumps({"turns": "bad"}))
    out = freeze_ledger(db, sess)
    assert out["turns"] == []
    assert out["frozen"] is True


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


# ---- catalog ----






















