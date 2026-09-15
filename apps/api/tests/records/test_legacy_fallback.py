"""Legacy fallback tests for src/realmock/domains/records/services/legacy_fallback.py.

Covers: no-catalog/empty/generating/bad-json/ok/catalog-fallback/count branches
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from realmock.domains.interview.models import InterviewSession
from realmock.domains.records.services import report_events
from realmock.domains.records.services.legacy_fallback import try_legacy_report
from realmock.platform.contracts.session_catalog import SessionSnapshot
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()
    for key in list(report_events._subscribers.keys()):
        for queue in list(report_events._subscribers.get(key, ())):
            report_events.unsubscribe(int(key.split(":")[1]), queue)


def _report_dict(score=80) -> dict:
    return {
        "overall_score": score,
        "score_breakdown": {"technical": score, "overall": score},
        "strengths": ["ok"],
        "weaknesses": ["x"],
        "improvement_suggestions": ["y"],
        "turn_notes": [],
    }


def _completed_session(db, token="cov-rep2-token-abc123") -> int:
    ledger = {
        "schema": "realmock.ledger.v1",
        "session_id": 0,
        "frozen": True,
        "turns": [
            {
                "turn_id": "t-0001",
                "phase": "intro",
                "assistant": {"text": "hi", "visible": True},
                "tools": [],
                "user": {"text": "hello", "source": "text"},
                "flags": {},
            }
        ],
    }
    row = InterviewSession(
        profile_id=1,
        role="Backend",
        level="Senior",
        company="bytedance",
        workflow_type="technical",
        status="completed",
        current_phase="summary",
        access_token=token,
        messages=json.dumps([{"role": "user", "content": "a"}]),
        ledger=json.dumps(ledger),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


def _snap_dict(**overrides) -> dict:
    base = SessionSnapshot.model_validate(
        {
            "id": 1,
            "role": "Backend",
            "level": "Senior",
            "company": "bytedance",
            "status": "completed",
            "messages": "[]",
            "report": "{}",
            "ledger_frozen": True,
        }
    ).model_dump(mode="json")
    base.update(overrides)
    return base


# ---- legacy fallback ----


def test_legacy_no_catalog_returns_none(db) -> None:
    with patch("realmock.domains.records.services.legacy_fallback.get_session_catalog") as cat:
        cat.return_value.get_session_snapshot.return_value = None
        assert try_legacy_report(db, 1) is None


def test_legacy_empty_and_generating_markers_return_none(db) -> None:
    for report in ("", "{}", '{"_generating":true}'):
        with patch("realmock.domains.records.services.legacy_fallback.get_session_catalog") as cat:
            cat.return_value.get_session_snapshot.return_value = _snap_dict(report=report)
            assert try_legacy_report(db, 1) is None


def test_legacy_bad_json_returns_none(db) -> None:
    with patch("realmock.domains.records.services.legacy_fallback.get_session_catalog") as cat:
        cat.return_value.get_session_snapshot.return_value = _snap_dict(report="{bad")
        assert try_legacy_report(db, 1) is None


def test_legacy_ok_with_ledger_present(db) -> None:
    payload = _report_dict(74)
    snap = _snap_dict(
        report=json.dumps(payload),
        ledger={"frozen": True},
        messages_count=3,
        duration_seconds=120.0,
    )
    with patch("realmock.domains.records.services.legacy_fallback.get_session_catalog") as cat:
        cat.return_value.get_session_snapshot.return_value = snap
        out = try_legacy_report(db, 5)
    assert out is not None
    assert out.report.overall_score == 74
    assert out.messages_count == 3
    assert out.duration_minutes == 2.0


def test_legacy_falls_back_to_catalog_ledger_and_counts(db) -> None:
    payload = _report_dict(71)
    snap = _snap_dict(
        report=json.dumps(payload),
        ledger=None,
        messages=json.dumps(
            [
                {"role": "user", "content": "a"},
                {"role": "assistant", "content": "b"},
                {"role": "system", "content": "s"},
            ]
        ),
        started_at=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc).isoformat(),
        ended_at=datetime(2024, 1, 1, 10, 6, tzinfo=timezone.utc).isoformat(),
    )
    with patch("realmock.domains.records.services.legacy_fallback.get_session_catalog") as cat:
        cat.return_value.get_session_snapshot.return_value = snap
        cat.return_value.get_ledger.return_value = {"frozen": True}
        out = try_legacy_report(db, 6)
    assert out is not None
    assert out.messages_count == 2
    assert out.duration_minutes == 6.0


def test_legacy_bad_messages_counts_zero(db) -> None:
    payload = _report_dict(70)
    snap = _snap_dict(report=json.dumps(payload), ledger={}, messages="bad")
    with patch("realmock.domains.records.services.legacy_fallback.get_session_catalog") as cat:
        cat.return_value.get_session_snapshot.return_value = snap
        out = try_legacy_report(db, 7)
    assert out is not None
    assert out.messages_count == 0
    assert out.duration_minutes is None


# ---- debrief runner ----










@contextmanager
def _session_ctx(db):
    yield db














# ---- history routes ----








