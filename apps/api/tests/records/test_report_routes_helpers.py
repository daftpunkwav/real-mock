"""Report routes helpers tests for src/realmock/domains/records/routes/report.py.

Covers: _messages_count/_duration_minutes/_build_response helpers
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from realmock.domains.interview.models import InterviewSession
from realmock.domains.records.routes import report as rmod
from realmock.domains.records.schemas.report import DebriefReport
from realmock.platform.contracts.session_catalog import SessionSnapshot
from realmock.platform.core.ratelimit import reset_rate_limit
from realmock.platform.models import LLMSettings

_TOKEN = "cov-report-token-" + ("c" * 12)


def _headers(token: str = _TOKEN) -> dict[str, str]:
    return {"X-Interview-Token": token}


def _report_dict(score=80) -> dict:
    return {
        "overall_score": score,
        "score_breakdown": {"technical": score, "overall": score},
        "strengths": ["ok"],
        "weaknesses": ["x"],
        "improvement_suggestions": ["y"],
        "turn_notes": [],
    }


def _ensure_llm(api_db) -> None:
    row = api_db.query(LLMSettings).filter(LLMSettings.id == 1).first()
    if row is None:
        row = LLMSettings(id=1, api_key="x", api_base="http://x", model="m")
        api_db.add(row)
    else:
        row.api_key = "x"
        row.api_base = "http://x"
        row.model = "m"
    api_db.commit()


def _completed_session(db, *, status="completed", frozen=True, token=_TOKEN) -> int:
    ledger = {
        "schema": "realmock.ledger.v1", "session_id": 0, "frozen": frozen,
        "turns": [{"turn_id": "t-0001", "phase": "intro",
                   "assistant": {"text": "hi", "visible": True}, "tools": [],
                   "user": {"text": "hello", "source": "text"}, "flags": {}}],
    }
    s = InterviewSession(
        profile_id=1, role="Backend", level="Senior", company="bytedance",
        workflow_type="technical", status=status, current_phase="summary",
        access_token=token,
        messages=json.dumps([
            {"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
        ]),
        ledger=json.dumps(ledger),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s.id


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def _snap(**overrides) -> SessionSnapshot:
    base = {
        "id": 1, "role": "Backend", "level": "Senior", "company": "bytedance",
        "status": "completed", "messages": "[]", "ledger_frozen": True,
    }
    base.update(overrides)
    return SessionSnapshot.model_validate(base)


def test_messages_count_prefers_field() -> None:
    assert rmod._messages_count(_snap(messages_count=7)) == 7


def test_messages_count_parses_roles() -> None:
    snap = _snap(messages=json.dumps([
        {"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
        {"role": "system", "content": "s"}, "bad",
    ]))
    assert rmod._messages_count(snap) == 2


def test_messages_count_bad_json_and_non_list() -> None:
    assert rmod._messages_count(_snap(messages="not-json")) == 0
    assert rmod._messages_count(_snap(messages=json.dumps({"a": 1}))) == 0


def test_duration_minutes_variants() -> None:
    assert rmod._duration_minutes(_snap(duration_seconds=90)) == 1.5
    start = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=12)
    assert rmod._duration_minutes(_snap(started_at=start, ended_at=end)) == 12.0
    assert rmod._duration_minutes(_snap()) is None


def test_build_response_uses_catalog_ledger_when_missing(db) -> None:
    snap = _snap(id=5, ledger=None)
    report = DebriefReport.model_validate(_report_dict())
    with patch(
        "realmock.domains.records.routes.report.get_session_catalog"
    ) as mock_cat:
        mock_cat.return_value.get_ledger.return_value = {"frozen": True}
        resp = rmod._build_response(db, snap, report)
        assert resp.session_id == 5
        assert resp.ledger == {"frozen": True}
        assert resp.messages_count == 0

















































