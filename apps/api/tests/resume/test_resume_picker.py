"""Domain-local resume selection API: return only dropdown summaries, without parsed body text or in-depth assessments."""

from __future__ import annotations

from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.platform.models import Resume


def test_interview_resume_picker_omits_analysis(api_db) -> None:
    row = Resume(
        filename="cv.pdf",
        file_type="pdf",
        raw_text="SECRET_RAW",
        parsed_profile='{"name":"hidden"}',
        is_active=True,
        score=88,
        analysis='{"score":99,"overall_narrative":"secret"}',
    )
    api_db.add(row)
    api_db.commit()

    with TestClient(app) as client:
        resp = client.get("/api/v1/interview/resumes")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    item = next(x for x in body if x["filename"] == "cv.pdf")
    assert item["is_active"] is True
    assert item["score"] == 88
    assert "analysis" not in item
    assert "parsed_profile" not in item
    assert "raw_text" not in item


def test_prep_resume_picker_omits_analysis(api_db) -> None:
    row = Resume(
        filename="prep.docx",
        file_type="docx",
        raw_text="SECRET_RAW",
        parsed_profile='{"name":"hidden"}',
        is_active=False,
        score=None,
        analysis='{"score":12}',
    )
    api_db.add(row)
    api_db.commit()

    with TestClient(app) as client:
        resp = client.get("/api/v1/prep/resumes")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    item = next(x for x in body if x["filename"] == "prep.docx")
    assert item["is_active"] is False
    assert item["score"] is None
    assert "analysis" not in item
    assert "parsed_profile" not in item
    assert "raw_text" not in item
