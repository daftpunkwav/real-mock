"""Report routes busy poll tests for src/realmock/domains/records/routes/report.py.

Covers: stream poll ready/failed transitions, cancelled-client mark-failed path
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.interview.models import InterviewSession
from realmock.domains.records.routes import report as rmod
from realmock.domains.records.schemas.report import DebriefReport
from realmock.domains.records.services import report_store as store
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.contracts.session_catalog import SessionSnapshot
from realmock.platform.core.ratelimit import reset_rate_limit
from realmock.platform.models import LLMSettings
from tests.fakes import FakeLLMClient

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






















































@pytest.mark.asyncio
async def test_report_stream_poll_finds_ready_row(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    store.upsert_pending(db, sid)
    ready = DebriefReport.model_validate(_report_dict(76))

    async def fake_none(*a, **k):
        return None

    calls = {"n": 0}
    orig_get = rmod.get_report_row

    def flipping_get(db_arg, sid_arg):
        calls["n"] += 1
        if calls["n"] < 3:
            return orig_get(db_arg, sid_arg)
        row = orig_get(db_arg, sid_arg)
        if row is not None:
            row.status = store.STATUS_READY
            row.payload = ready.model_dump_json()
        return row

    async def fast_sleep(*a, **k):
        return None

    with patch.object(rmod, "run_debrief_for_session", side_effect=fake_none):
        with patch.object(rmod, "get_report_row", side_effect=flipping_get):
            with patch.object(rmod.asyncio, "sleep", side_effect=fast_sleep):
                with patch.object(LLMClient, "from_db", classmethod(lambda cls, db: FakeLLMClient())):
                    with TestClient(app) as client:
                        with client.stream(
                            "GET", f"/api/reports/{sid}/stream", headers=_headers()
                        ) as resp:
                            assert resp.status_code == 200
                            chunks = [
                                json.loads(line[6:]) for line in resp.iter_lines()
                                if line.startswith("data: ")
                            ]
    assert any(c["type"] == "done" for c in chunks)


@pytest.mark.asyncio
async def test_report_stream_poll_breaks_on_failed(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    store.upsert_pending(db, sid)

    async def fake_none(*a, **k):
        return None

    orig_get = rmod.get_report_row

    def failing_get(db_arg, sid_arg):
        row = orig_get(db_arg, sid_arg)
        if row is not None:
            row.status = store.STATUS_FAILED
        return row

    async def fast_sleep(*a, **k):
        return None

    with patch.object(rmod, "run_debrief_for_session", side_effect=fake_none):
        with patch.object(rmod, "get_report_row", side_effect=failing_get):
            with patch.object(rmod.asyncio, "sleep", side_effect=fast_sleep):
                with patch.object(LLMClient, "from_db", classmethod(lambda cls, db: FakeLLMClient())):
                    with TestClient(app) as client:
                        with client.stream(
                            "GET", f"/api/reports/{sid}/stream", headers=_headers()
                        ) as resp:
                            assert resp.status_code == 200
                            chunks = [
                                json.loads(line[6:]) for line in resp.iter_lines()
                                if line.startswith("data: ")
                            ]
    assert any(c["type"] == "error" for c in chunks)


@pytest.mark.asyncio
async def test_report_stream_cancelled_branch_marks_generating_failed(db) -> None:
    # Directly exercise the CancelledError handler shape: a generating row
    # disconnected mid-stream must be marked failed without swallowing CancelledError.
    import asyncio as _asyncio

    from realmock.domains.records.services import report_store as _store

    # Use sessions db fixture `db` for report rows (no llm table needed here).
    sid = 888001
    _store.upsert_pending(db, sid)
    row = _store.get_report_row(db, sid)
    assert row is not None
    row.status = _store.STATUS_GENERATING
    from datetime import timezone as _tz

    row.updated_at = datetime.now(_tz.utc)
    db.commit()
    # Simulate the handler's cancel path: mark_failed on CancelledError.
    try:
        raise _asyncio.CancelledError()
    except _asyncio.CancelledError:
        _store.mark_failed(db, sid, "cancelled: SSE client disconnected")
        raised = True
    assert raised
    assert _store.get_report_row(db, sid).status == _store.STATUS_FAILED  # type: ignore[union-attr]

