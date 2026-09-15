"""Report routes stream tests for src/realmock/domains/records/routes/report.py.

Covers: SSE stream ready/pending/none/exception/legacy/live-events relay
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
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
async def test_generate_with_live_events_relays_and_returns() -> None:
    from realmock.domains.records.services import report_events

    sid = 424242
    fake = DebriefReport.model_validate(_report_dict(75))

    async def fake_run(*a, **k):
        on_event = k.get("on_event")
        if on_event is not None:
            await on_event({"type": "stage", "stage": "notes"})
        return fake

    with patch.object(rmod, "run_debrief_for_session", side_effect=fake_run):
        snap = _snap(id=sid)
        out: list = []
        lines = []
        async for line in rmod._generate_with_live_events(
            sid, snap=snap, llm=FakeLLMClient(), report_out=out
        ):
            lines.append(line)
        assert out and out[0].overall_score == 75
        assert any("stage" in line for line in lines)
    # subscribers cleaned
    assert report_events._subscribers.get(f"report:{sid}") in (None, set())


@pytest.mark.asyncio
async def test_report_stream_ready_pseudo_streams(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    store.persist_ready(db, sid, DebriefReport.model_validate(_report_dict(80)))
    with patch.object(LLMClient, "from_db", classmethod(lambda cls, db: FakeLLMClient())):
        with TestClient(app) as client:
            with client.stream("GET", f"/api/reports/{sid}/stream", headers=_headers()) as resp:
                assert resp.status_code == 200
                chunks = [
                    json.loads(line[6:]) for line in resp.iter_lines()
                    if line.startswith("data: ")
                ]
    assert "token" in [c["type"] for c in chunks]
    assert "done" in [c["type"] for c in chunks]


@pytest.mark.asyncio
async def test_report_stream_generates_when_pending(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    store.upsert_pending(db, sid)
    fake = DebriefReport.model_validate(_report_dict(79))

    async def fake_run(*a, **k):
        return fake

    with patch.object(rmod, "run_debrief_for_session", side_effect=fake_run):
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
async def test_report_stream_none_reports_error_event(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    store.upsert_pending(db, sid)

    async def fake_none(*a, **k):
        return None

    async def no_poll(*a, **k):
        return None

    with patch.object(rmod, "run_debrief_for_session", side_effect=fake_none):
        with patch.object(LLMClient, "from_db", classmethod(lambda cls, db: FakeLLMClient())):
            with patch.object(rmod.asyncio, "sleep", side_effect=no_poll):
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
async def test_report_stream_exception_yields_sse_error(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    with patch.object(rmod, "get_report_row", side_effect=RuntimeError("db down")):
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
async def test_report_stream_legacy_path(db, api_db) -> None:
    _ensure_llm(api_db)
    sid = _completed_session(db)
    db.query(InterviewSession).filter(InterviewSession.id == sid).first().report = json.dumps(
        _report_dict(74)
    )
    db.commit()
    with patch.object(LLMClient, "from_db", classmethod(lambda cls, db: FakeLLMClient())):
        with patch.object(rmod, "run_debrief_for_session") as mock_run:
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
    mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_generate_with_live_events_drains_leftover_queue() -> None:
    from realmock.domains.records.services import report_events

    sid = 777001
    fake = DebriefReport.model_validate(_report_dict(75))
    q_holder: dict = {}

    orig_subscribe = report_events.subscribe

    def fake_subscribe(sid_arg):
        q = orig_subscribe(sid_arg)
        q.put_nowait({"type": "stage", "stage": "leftover"})
        q_holder["q"] = q
        return q

    async def fake_run(*a, **k):
        return fake

    with patch.object(report_events, "subscribe", side_effect=fake_subscribe):
        with patch.object(rmod, "run_debrief_for_session", side_effect=fake_run):
            snap = _snap(id=sid)
            out: list = []
            lines = []
            async for line in rmod._generate_with_live_events(
                sid, snap=snap, llm=FakeLLMClient(), report_out=out
            ):
                lines.append(line)
                if len(lines) > 5:
                    break
            assert out and out[0].overall_score == 75
            assert any("leftover" in line for line in lines)







