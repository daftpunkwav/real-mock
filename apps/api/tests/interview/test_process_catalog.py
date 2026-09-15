"""Process catalog tests for src/realmock/domains/interview/process/catalog.py.

Covers: InterviewSessionCatalog list/get/snapshot/ledger/context/duration/item/projection/register
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from realmock.domains.interview.ledger.store import (
    empty_ledger,
)
from realmock.domains.interview.models import InterviewProcess, InterviewSession
from realmock.domains.interview.process.catalog import (
    InterviewSessionCatalog,
    InterviewSessionScoreProjection,
    register_interview_session_catalog,
)
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
































# ---- catalog ----


def test_list_sessions_newest_first(db) -> None:
    InterviewSessionCatalog().list_sessions(db)  # empty ok
    _db_session(db, role="A")
    _db_session(db, role="B")
    items = InterviewSessionCatalog().list_sessions(db)
    assert len(items) >= 2
    assert items[0].id >= items[-1].id


def test_get_session_none_and_ok(db) -> None:
    cat = InterviewSessionCatalog()
    assert cat.get_session(db, 999999) is None
    row = _db_session(db)
    snap = cat.get_session(db, row.id)
    assert snap is not None
    assert snap.id == row.id


def test_get_session_snapshot_none_and_ok(db) -> None:
    cat = InterviewSessionCatalog()
    assert cat.get_session_snapshot(db, 999999) is None
    row = _db_session(db)
    snap = cat.get_session_snapshot(db, row.id)
    assert snap is not None
    assert snap["id"] == row.id


def test_get_ledger_none_and_ok(db) -> None:
    cat = InterviewSessionCatalog()
    assert cat.get_ledger(db, 999999) is None
    row = _db_session(db)
    ledger = cat.get_ledger(db, row.id)
    assert ledger is not None
    assert "turns" in ledger


def test_get_process_context_missing_and_ok(db) -> None:
    cat = InterviewSessionCatalog()
    assert cat.get_process_context(db, 999999) == ""
    proc = InterviewProcess(role="r", level="l", company="c", memory="{}")
    db.add(proc)
    db.commit()
    db.refresh(proc)
    text = cat.get_process_context(db, proc.id)
    assert isinstance(text, str)


def test_messages_and_duration_corrupt_and_types() -> None:
    cat = InterviewSessionCatalog()
    bad = SimpleNamespace(id=1, messages="{bad", started_at=None, ended_at=None)
    count, dur = cat._messages_and_duration(bad)  # type: ignore[arg-type]
    assert (count, dur) == (0, None)
    non_list = SimpleNamespace(id=1, messages='{"a":1}', started_at=None, ended_at=None)
    count2, _ = cat._messages_and_duration(non_list)  # type: ignore[arg-type]
    assert count2 == 0
    ok = SimpleNamespace(
        id=1,
        messages=json.dumps([{"a": 1}]),
        started_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ended_at=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=90),
    )
    count3, dur3 = cat._messages_and_duration(ok)  # type: ignore[arg-type]
    assert count3 == 1
    assert dur3 == 90.0
    # Non-datetime bounds degrade to None duration.
    weird = SimpleNamespace(
        id=1,
        messages="[]",
        started_at="x",
        ended_at="y",
    )
    _, dur4 = cat._messages_and_duration(weird)  # type: ignore[arg-type]
    assert dur4 is None


def test_to_item_defaults_avatar_scene(db) -> None:
    row = _db_session(db)
    row.avatar_id = ""
    row.scene_id = ""
    item = InterviewSessionCatalog._to_item(row)
    assert item.avatar_id == "professional_male"
    assert item.scene_id == "meeting_room"


def test_to_snapshot_defaults_and_frozen(db) -> None:
    row = _db_session(db)
    row.role = ""
    row.messages = "{bad"
    snap = InterviewSessionCatalog._to_snapshot(row)
    assert snap.role == ""
    assert snap.messages_count == 0
    assert snap.ledger_frozen is False


def test_apply_overall_score_missing_no_crash(db) -> None:
    InterviewSessionScoreProjection().apply_overall_score(db, 999999, 80)


def test_apply_overall_score_ok_and_rollback(db) -> None:
    row = _db_session(db)
    InterviewSessionScoreProjection().apply_overall_score(db, row.id, 77)
    db.expire_all()
    assert db.get(InterviewSession, row.id).overall_score == 77
    # Commit failure rolls back and re-raises.
    with patch.object(db, "commit", side_effect=RuntimeError("db down")):
        with pytest.raises(RuntimeError):
            InterviewSessionScoreProjection().apply_overall_score(db, row.id, 80)


def test_register_interview_session_catalog_registers_both() -> None:
    with (
        patch("realmock.domains.interview.process.catalog.register_session_catalog") as reg_cat,
        patch(
            "realmock.domains.interview.process.catalog.register_session_score_projection"
        ) as reg_score,
    ):
        cat = register_interview_session_catalog()
        assert isinstance(cat, InterviewSessionCatalog)
        reg_cat.assert_called_once_with(cat)
        reg_score.assert_called_once()
