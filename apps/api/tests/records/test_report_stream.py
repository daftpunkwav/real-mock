"""Report stream API tests (records domain debrief path)."""

from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.interview.models import InterviewSession
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.models import LLMSettings
from tests.fakes import FakeLLMClient

_TOKEN = "report-stream-token-" + ("b" * 12)


def _auth_headers(token: str = _TOKEN) -> dict[str, str]:
    return {"X-Interview-Token": token}


def _fake_report_payload() -> dict:
    return {
        "overall_score": 80,
        "score_breakdown": {
            "technical": 80,
            "communication": 80,
            "project_depth": 80,
            "problem_solving": 80,
            "presence": 80,
            "politeness": 80,
            "overall": 80,
        },
        "strengths": ["ok"],
        "weaknesses": ["x"],
        "improvement_suggestions": ["y"],
        "resume_suggestions": [],
        "interview_suggestions": [],
        "training_plan": [],
        "phase_summary": {},
        "face_analysis_summary": "",
        "presence_moments": [],
        "turn_notes": [],
    }


def _make_completed_session(db, api_db) -> int:
    settings = api_db.query(LLMSettings).filter(LLMSettings.id == 1).first()
    if settings is None:
        settings = LLMSettings(id=1, api_key="x", api_base="http://x", model="m")
        api_db.add(settings)
    else:
        settings.api_base = "http://x"
        settings.api_key = "x"
        settings.model = "m"
    api_db.commit()
    ledger = {
        "schema": "realmock.ledger.v1",
        "session_id": 0,
        "frozen": True,
        "turns": [
            {
                "turn_id": "t-0001",
                "phase": "intro",
                "assistant": {"text": "Please introduce yourself", "visible": True},
                "tools": [],
                "user": {"text": "I optimized the API", "source": "text"},
                "flags": {},
            }
        ],
    }
    s = InterviewSession(
        profile_id=1,
        role="Backend engineer",
        level="intermediate",
        company="bytedance",
        workflow_type="technical",
        status="completed",
        current_phase="summary",
        access_token=_TOKEN,
        messages=json.dumps(
            [
                {"role": "user", "content": "I optimized the API"},
                {"role": "assistant", "content": "Please share specific metrics"},
                {"role": "user", "content": "QPS increased from 1k to 8k"},
            ],
            ensure_ascii=False,
        ),
        ledger=json.dumps(ledger, ensure_ascii=False),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s.id


def test_report_stream_emits_token_and_done(db, api_db) -> None:
    """Report SSE pseudo-streams the ready payload; done matches persisted JSON."""
    sid = _make_completed_session(db, api_db)
    fake = FakeLLMClient(
        tokens=["should-not-be-used"],
        json_payload=_fake_report_payload(),
    )

    async def _no_legacy_chat_stream(*args, **kwargs):
        raise AssertionError("legacy chat_stream must not be used by the report pipeline")

    fake.chat_stream = _no_legacy_chat_stream
    with patch.object(LLMClient, "from_db", classmethod(lambda cls, db: fake)):
        with TestClient(app) as client:
            with client.stream(
                "GET",
                f"/api/reports/{sid}/stream",
                headers=_auth_headers(),
            ) as resp:
                assert resp.status_code == 200
                chunks = []
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunks.append(json.loads(line[6:]))

    types = [c["type"] for c in chunks]
    assert "token" in types
    assert "done" in types

    token_text = "".join(c["content"] for c in chunks if c["type"] == "token")
    assert '"overall_score": 80' in token_text or '"overall_score":80' in token_text

    done = next(c for c in chunks if c["type"] == "done")
    assert "report" in done
    assert done["report"]["overall_score"] == 80


def test_report_stream_404_when_session_missing(db) -> None:
    with TestClient(app) as client:
        resp = client.get(
            "/api/reports/9999/stream",
            headers=_auth_headers(),
        )
        assert resp.status_code == 404


def test_report_stream_403_without_token(db, api_db) -> None:
    sid = _make_completed_session(db, api_db)
    with TestClient(app) as client:
        resp = client.get(f"/api/reports/{sid}/stream")
        assert resp.status_code == 403


def test_report_stream_400_when_session_not_completed(db) -> None:
    s = InterviewSession(
        profile_id=1,
        role="Backend engineer",
        level="intermediate",
        company="bytedance",
        workflow_type="technical",
        status="active",
        access_token=_TOKEN,
        ledger=json.dumps(
            {
                "schema": "realmock.ledger.v1",
                "session_id": 0,
                "frozen": False,
                "turns": [],
            },
            ensure_ascii=False,
        ),
    )
    db.add(s)
    db.commit()
    db.refresh(s)

    with TestClient(app) as client:
        resp = client.get(
            f"/api/reports/{s.id}/stream",
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
