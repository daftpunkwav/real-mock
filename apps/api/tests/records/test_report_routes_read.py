"""Report routes read tests for src/realmock/domains/records/routes/report.py.

Covers: GET report ready/pending/failed/bad-payload/unfinished/missing/forbidden/legacy
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.interview.models import InterviewSession
from realmock.domains.records.schemas.report import DebriefReport
from realmock.domains.records.services import report_store as store
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












def test_get_report_ready(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    store.persist_ready(db, sid, DebriefReport.model_validate(_report_dict(81)))
    with TestClient(app) as client:
        resp = client.get(f"/api/reports/{sid}", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["report"]["overall_score"] == 81


def test_get_report_pending_is_404(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    store.upsert_pending(db, sid)
    with TestClient(app) as client:
        resp = client.get(f"/api/reports/{sid}", headers=_headers())
    assert resp.status_code == 404


def test_get_report_failed_is_409(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    store.upsert_pending(db, sid)
    store.mark_failed(db, sid, "boom")
    with TestClient(app) as client:
        resp = client.get(f"/api/reports/{sid}", headers=_headers())
    assert resp.status_code == 409


def test_get_report_ready_bad_payload_falls_to_404(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    row = store.upsert_pending(db, sid)
    row.status = store.STATUS_READY
    row.payload = "{}"
    db.commit()
    with TestClient(app) as client:
        resp = client.get(f"/api/reports/{sid}", headers=_headers())
    assert resp.status_code == 404


def test_get_report_requires_finished(db) -> None:
    sid = _completed_session(db, status="active", frozen=False)
    with TestClient(app) as client:
        resp = client.get(f"/api/reports/{sid}", headers=_headers())
    assert resp.status_code == 400


def test_get_report_404_missing() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/reports/999999", headers=_headers())
    assert resp.status_code == 404


def test_get_report_403_without_token(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    with TestClient(app) as client:
        resp = client.get(f"/api/reports/{sid}")
    assert resp.status_code == 403




















def test_get_report_no_row_is_404(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    # No interview_reports row and no legacy report -> A2004 (404).
    with TestClient(app) as client:
        resp = client.get(f"/api/reports/{sid}", headers=_headers())
    assert resp.status_code == 404


def test_get_report_legacy_fallback(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    db.query(InterviewSession).filter(InterviewSession.id == sid).first().report = json.dumps(
        _report_dict(73)
    )
    db.commit()
    with TestClient(app) as client:
        resp = client.get(f"/api/reports/{sid}", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["report"]["overall_score"] == 73













