"""Session fix: report SSE pseudo-streams JSON and never uses the legacy token chat_stream."""

from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.platform.models import LLMSettings
from realmock.domains.interview.models import InterviewSession
from realmock.platform.capabilities.ai.llm.client import LLMClient
from tests.fakes import FakeLLMClient


def _completed_session(db, api_db) -> tuple[int, str]:
    settings = api_db.query(LLMSettings).filter(LLMSettings.id == 1).first()
    if settings is None:
        settings = LLMSettings(id=1, api_key="x", api_base="http://x", model="m")
        api_db.add(settings)
    else:
        settings.api_base = "http://x"
        settings.api_key = "x"
        settings.model = "m"
    api_db.commit()
    token = "report-test-token-" + ("a" * 16)
    s = InterviewSession(
        profile_id=1,
        role="Backend engineer",
        level="intermediate",
        company="bytedance",
        workflow_type="technical",
        status="completed",
        current_phase="summary",
        access_token=token,
        messages=json.dumps(
            [
                {"role": "user", "content": "I optimized the API"},
                {"role": "assistant", "content": "Specific metrics?"},
            ],
            ensure_ascii=False,
        ),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s.id, token


def test_report_stream_single_llm_no_stream_calls(db, api_db) -> None:
    sid, token = _completed_session(db, api_db)
    fake = FakeLLMClient(
        tokens=["MUST_NOT_APPEAR"],
        json_payload={
            "overall_score": 88,
            "score_breakdown": {
                "technical": 88,
                "communication": 80,
                "project_depth": 85,
                "problem_solving": 90,
                "presence": 80,
                "overall": 88,
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
        },
    )

    async def _no_legacy_chat_stream(*args, **kwargs):
        raise AssertionError("legacy chat_stream must not be used by the report pipeline")

    fake.chat_stream = _no_legacy_chat_stream
    with patch.object(LLMClient, "from_db", classmethod(lambda cls, db: fake)):
        with TestClient(app) as client:
            with client.stream(
                "GET",
                f"/api/reports/{sid}/stream",
                headers={"X-Interview-Token": token},
            ) as resp:
                assert resp.status_code == 200
                chunks = []
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        chunks.append(json.loads(line[6:]))

    types = [c["type"] for c in chunks]
    assert "token" in types
    assert "done" in types
    done = next(c for c in chunks if c["type"] == "done")
    assert done["report"]["overall_score"] == 88
