"""Report routes retry tests for src/realmock/domains/records/routes/report.py.

Covers: POST retry ready/generating/debrief/none/bad-payload branches
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
async def test_retry_report_ready_returns_as_is(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    store.persist_ready(db, sid, DebriefReport.model_validate(_report_dict(82)))
    with TestClient(app) as client:
        resp = client.post(f"/api/reports/{sid}/retry", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["report"]["overall_score"] == 82


@pytest.mark.asyncio
async def test_retry_report_generating_is_404(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    row = store.upsert_pending(db, sid)
    row.status = store.STATUS_GENERATING
    from datetime import timezone as _tz

    row.updated_at = datetime.now(_tz.utc)
    db.commit()
    with TestClient(app) as client:
        resp = client.post(f"/api/reports/{sid}/retry", headers=_headers())
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_retry_report_generates_via_debrief(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    store.upsert_pending(db, sid)
    fake = DebriefReport.model_validate(_report_dict(77))

    async def fake_run(*a, **k):
        return fake

    with patch.object(rmod, "run_debrief_for_session", side_effect=fake_run):
        with patch.object(LLMClient, "from_db", classmethod(lambda cls, db: FakeLLMClient())):
            with TestClient(app) as client:
                resp = client.post(f"/api/reports/{sid}/retry", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["report"]["overall_score"] == 77


@pytest.mark.asyncio
async def test_retry_report_none_is_404(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    store.upsert_pending(db, sid)

    async def fake_none(*a, **k):
        return None

    with patch.object(rmod, "run_debrief_for_session", side_effect=fake_none):
        with patch.object(LLMClient, "from_db", classmethod(lambda cls, db: FakeLLMClient())):
            with TestClient(app) as client:
                resp = client.post(f"/api/reports/{sid}/retry", headers=_headers())
    assert resp.status_code == 404
















@pytest.mark.asyncio
async def test_retry_report_ready_bad_payload_is_404(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    row = store.upsert_pending(db, sid)
    row.status = store.STATUS_READY
    row.payload = "{}"
    db.commit()
    with TestClient(app) as client:
        resp = client.post(f"/api/reports/{sid}/retry", headers=_headers())
    assert resp.status_code == 404











