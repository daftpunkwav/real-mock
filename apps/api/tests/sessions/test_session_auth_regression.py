"""Authentication regression: reports / prep require a capability token; an invalid token must not evict the WS lease."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from realmock.platform.core.session_auth import new_access_token
from realmock.asgi import app
from realmock.domains.prep.models import PrepSession
from realmock.domains.interview.models import InterviewSession


def test_report_get_requires_token(db) -> None:
    token = new_access_token()
    s = InterviewSession(
        profile_id=1,
        role="Backend engineer",
        level="intermediate",
        company="bytedance",
        workflow_type="technical",
        status="completed",
        access_token=token,
        report=json.dumps(
            {
                "overall_score": 70,
                "score_breakdown": {
                    "technical": 70,
                    "communication": 70,
                    "project_depth": 70,
                    "problem_solving": 70,
                    "presence": 70,
                    "overall": 70,
                },
                "strengths": [],
                "weaknesses": [],
                "improvement_suggestions": [],
                "resume_suggestions": [],
                "interview_suggestions": [],
                "training_plan": [],
                "phase_summary": {},
                "face_analysis_summary": "",
                "presence_moments": [],
            }
        ),
        messages="[]",
    )
    db.add(s)
    db.commit()
    db.refresh(s)

    with TestClient(app) as client:
        assert client.get(f"/api/reports/{s.id}").status_code == 403
        ok = client.get(
            f"/api/reports/{s.id}",
            headers={"X-Interview-Token": token},
        )
        assert ok.status_code == 200


def test_prep_message_requires_token(db) -> None:
    token = new_access_token()
    p = PrepSession(access_token=token, status="active", messages="[]")
    db.add(p)
    db.commit()
    db.refresh(p)

    with TestClient(app) as client:
        assert (
            client.post(
                f"/api/v1/prep/sessions/{p.id}/message",
                json={"content": "hi"},
            ).status_code
            == 403
        )
        # With a token but no LLM, the response may be 502/500; the key requirement is that it is no longer 403.
        resp = client.post(
            f"/api/v1/prep/sessions/{p.id}/message",
            json={"content": "hi"},
            headers={"X-Interview-Token": token},
        )
        assert resp.status_code != 403


@pytest.mark.asyncio
async def test_ws_bad_token_does_not_claim_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject an invalid token before claim; it must not displace a legitimate connection."""
    from realmock.domains.interview.realtime import ws_handler as ws_mod

    ws_mod.reset_session_registry_for_tests()

    class _StubSession:
        id = 7
        status = "active"
        access_token = "good-token-" + ("c" * 20)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = _StubSession()
    # handle() is defined in the connection_lifecycle module, so patch SessionLocal in that module.
    monkeypatch.setattr("realmock.domains.interview.realtime.connection.lifecycle.SessionLocal", lambda: mock_db)

    good_ws = MagicMock()
    good_ws.accept = AsyncMock()
    good_ws.send_json = AsyncMock()
    good_ws.close = AsyncMock()
    good_ws.receive_json = AsyncMock(side_effect=Exception("stop"))

    bad_ws = MagicMock()
    bad_ws.accept = AsyncMock()
    bad_ws.send_json = AsyncMock()
    bad_ws.close = AsyncMock()

    good = ws_mod.InterviewWSHandler(
        good_ws, session_id=7, access_token=_StubSession.access_token
    )
    # Manually acquire the lease to simulate an authenticated legitimate user
    await ws_mod.claim_session_connection(good)
    assert ws_mod.active_handlers_for_tests()[7] is good

    attacker = ws_mod.InterviewWSHandler(bad_ws, session_id=7, access_token="wrong")
    await attacker.handle()

    assert ws_mod.active_handlers_for_tests()[7] is good
    assert good._superseded is False
    sent = [c.args[0] for c in bad_ws.send_json.call_args_list]
    assert any(e.get("type") == "error" for e in sent)

    await ws_mod.release_session_connection(good)
