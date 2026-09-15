"""History routes tests for src/realmock/domains/records/routes/history.py.

Covers: list sessions, ledger ok/missing/forbidden/none branches
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from realmock.asgi import app
from realmock.domains.interview.models import InterviewSession
from realmock.domains.records.routes import history as hmod
from realmock.domains.records.services import report_events
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














# ---- debrief runner ----










@contextmanager
def _session_ctx(db):
    yield db














# ---- history routes ----


def test_history_list_sessions(db) -> None:
    _completed_session(db)
    with TestClient(app) as client:
        resp = client.get("/api/v1/records/sessions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_history_ledger_ok_and_missing(db) -> None:
    token = "cov-rep2-ledger-token-xyz1"
    sid = _completed_session(db, token=token)
    with TestClient(app) as client:
        ok = client.get(
            f"/api/v1/records/sessions/{sid}/ledger",
            headers={"X-Interview-Token": token},
        )
        assert ok.status_code == 200
        assert "turns" in ok.json()
        missing = client.get(
            "/api/v1/records/sessions/999999/ledger",
            headers={"X-Interview-Token": token},
        )
        assert missing.status_code == 404


def test_history_ledger_forbidden_without_token(db) -> None:
    sid = _completed_session(db)
    with TestClient(app) as client:
        resp = client.get(f"/api/v1/records/sessions/{sid}/ledger")
    assert resp.status_code == 403


def test_history_ledger_none_from_catalog_is_404(db) -> None:
    sid = _completed_session(db)
    with patch.object(hmod, "get_session_catalog") as cat:
        cat.return_value.get_session_snapshot.return_value = _snap_dict(id=sid)
        cat.return_value.get_ledger.return_value = None
        with TestClient(app) as client:
            # Bypass token check by matching access token to snapshot.
            snap_token = "cov-rep2-none-ledger12"
            cat.return_value.get_session_snapshot.return_value = _snap_dict(
                id=sid, access_token=snap_token
            )
            resp = client.get(
                f"/api/v1/records/sessions/{sid}/ledger",
                headers={"X-Interview-Token": snap_token},
            )
    assert resp.status_code == 404
