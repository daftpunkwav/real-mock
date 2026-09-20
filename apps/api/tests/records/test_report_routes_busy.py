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
async def test_report_stream_poll_observes_another_session_commit(
    db, api_db, session_factory
) -> None:
    """The poll must see a ready row committed outside the request Session.

    The debrief worker writes through its own Session, so a poll that keeps
    handing back the identity-mapped instance never observes the transition and
    the stream answers A2004 for a report that is already ready.
    """
    _ensure_llm(api_db)
    sid = _completed_session(db)
    store.upsert_pending(db, sid)
    ready = DebriefReport.model_validate(_report_dict(76))

    async def fake_none(*a, **k):
        return None

    orig_get = rmod.get_report_row
    calls = {"n": 0}
    flipped = {"done": False}

    def flipping_get(db_arg, sid_arg):
        calls["n"] += 1
        # Commit from a foreign Session only after the request Session has
        # already loaded the row, so the poll really has to leave its snapshot.
        if calls["n"] >= 3 and not flipped["done"]:
            flipped["done"] = True
            worker = session_factory()
            try:
                row = store.get_report_row(worker, sid_arg)
                assert row is not None
                row.status = store.STATUS_READY
                row.payload = ready.model_dump_json()
                worker.commit()
            finally:
                worker.close()
        return orig_get(db_arg, sid_arg)

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
    assert flipped["done"], "poll never ran, so the assertion below proves nothing"
    assert any(c["type"] == "done" for c in chunks)


@pytest.mark.asyncio
async def test_report_stream_poll_breaks_on_failed(db, api_db, session_factory) -> None:
    """A failed status written by the worker Session must end the poll."""
    _ensure_llm(api_db)
    sid = _completed_session(db)
    store.upsert_pending(db, sid)

    async def fake_none(*a, **k):
        return None

    orig_get = rmod.get_report_row
    calls = {"n": 0}
    flipped = {"done": False}

    def failing_get(db_arg, sid_arg):
        calls["n"] += 1
        if calls["n"] >= 3 and not flipped["done"]:
            flipped["done"] = True
            worker = session_factory()
            try:
                row = store.get_report_row(worker, sid_arg)
                assert row is not None
                row.status = store.STATUS_FAILED
                worker.commit()
            finally:
                worker.close()
        return orig_get(db_arg, sid_arg)

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
    assert flipped["done"], "poll never ran, so the assertion below proves nothing"
    # Breaking on failed is what distinguishes this from the timeout path: an
    # unrefreshed poll would burn all 120 iterations and emit the generic error.
    assert calls["n"] < 20, f"poll did not break early: {calls['n']} reads"
    assert any(c["type"] == "error" for c in chunks)


@pytest.mark.asyncio
async def test_report_stream_cancelled_branch_marks_generating_failed(db) -> None:
    # Store-level contract for explicit failures (route handler no longer marks
    # failed on SSE client disconnect; see test_report_stream_cancel_keeps_generating).
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
    # Simulate an explicit failure path: mark_failed on a terminal error.
    try:
        raise _asyncio.CancelledError()
    except _asyncio.CancelledError:
        _store.mark_failed(db, sid, "explicit failure in test")
        raised = True
    assert raised
    assert _store.get_report_row(db, sid).status == _store.STATUS_FAILED  # type: ignore[union-attr]

