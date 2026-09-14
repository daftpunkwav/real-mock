"""Ledger store: turn append/freeze plus last-turn flag patching."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from realmock.domains.interview.ledger.store import (
    append_last_turn_flag,
    empty_ledger,
    freeze_ledger,
)


def _session(doc: dict) -> SimpleNamespace:
    return SimpleNamespace(id=7, ledger=json.dumps(doc))


def _db() -> MagicMock:
    return MagicMock()


def test_append_last_turn_flag_merges_into_newest_turn():
    doc = empty_ledger(7)
    doc["turns"] = [
        {"turn_id": "t-0001", "phase": "p", "assistant": {"text": "Q1"}, "flags": {"keep": 1}},
        {"turn_id": "t-0002", "phase": "p", "assistant": {"text": "Q2"}},
    ]
    session = _session(doc)

    append_last_turn_flag(_db(), session, "silence_probe", {"seq": 1, "text": "still there?"})

    turns = json.loads(session.ledger)["turns"]
    assert turns[0]["flags"] == {"keep": 1}  # older turns untouched
    assert turns[1]["flags"]["silence_probe"]["seq"] == 1


def test_append_last_turn_flag_noop_when_frozen():
    doc = empty_ledger(7)
    doc["frozen"] = True
    doc["turns"] = [{"turn_id": "t-0001", "assistant": {"text": "Q"}}]
    session = _session(doc)

    append_last_turn_flag(_db(), session, "silence_probe", {"seq": 9})

    assert "silence_probe" not in json.loads(session.ledger)["turns"][-1]


def test_append_last_turn_flag_noop_without_turns():
    session = _session(empty_ledger(7))
    append_last_turn_flag(_db(), session, "k", "v")
    assert json.loads(session.ledger)["turns"] == []


def test_freeze_still_works_after_flag_writes():
    doc = empty_ledger(7)
    doc["turns"] = [{"turn_id": "t-0001", "assistant": {"text": "Q"}}]
    session = _session(doc)
    db = _db()

    append_last_turn_flag(db, session, "silence_probe", {"seq": 1})
    frozen = freeze_ledger(db, session)
    assert frozen["frozen"] is True
