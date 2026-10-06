"""Deep-review analysis export tests (md / json).

Covers: happy paths with and without the folded resume, missing analysis
(A1010), missing resume (A1005), and the score/section rendering.
Conventions: real store seeding against the temp api DB; TestClient for HTTP.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.resume.services import store
from realmock.platform.database import get_db
from realmock.platform.schemas import CandidateProfile


def _seed(api_db, *, with_analysis: bool = True) -> int:
    row = store.insert_upload(
        api_db,
        filename="cv.txt",
        file_type="txt",
        raw_text="body",
        parsed=CandidateProfile(name="Ada", summary="Summary text", skills=["Python", "FastAPI"]),
    )
    if with_analysis:
        row.analysis = json.dumps(
            {
                "score": 70,
                "strengths": ["clear structure"],
                "weaknesses": ["thin metrics"],
                "interview_qa": [
                    {
                        "question": "Explain the Agent Loop.",
                        "intent": "Depth check",
                        "answer_points": ["ReAct cycle"],
                        "follow_ups": ["How do you recover state?"],
                    }
                ],
                "project_deep_dive": ["Why hand-rolled instead of LangGraph?"],
                "dimension_scores": {f"d{i}": {"score": 70, "comment": ""} for i in range(5)},
            }
        )
        row.score = 70
    api_db.commit()
    return row.id


def _override_api_db(db):
    app.dependency_overrides[get_db] = lambda: db


def _unoverride_api_db():
    app.dependency_overrides.pop(get_db, None)


def test_analysis_export_markdown(api_db) -> None:
    resume_id = _seed(api_db)
    _override_api_db(api_db)
    try:
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/resume/{resume_id}/analysis-export?format=md")
    finally:
        _unoverride_api_db()
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == f"resume-analysis-{resume_id}.md"
    assert "# Resume Deep Review — cv.txt" in body["content"]
    assert "**Overall score**: 70" in body["content"]
    assert "### Q1. Explain the Agent Loop." in body["content"]
    assert "Why hand-rolled instead of LangGraph?" in body["content"]
    # The parsed resume body is only folded in on request.
    assert "Ada" not in body["content"]


def test_analysis_export_markdown_with_resume(api_db) -> None:
    resume_id = _seed(api_db)
    _override_api_db(api_db)
    try:
        with TestClient(app) as client:
            resp = client.get(
                f"/api/v1/resume/{resume_id}/analysis-export?format=md&include_resume=true"
            )
    finally:
        _unoverride_api_db()
    assert resp.status_code == 200
    content = resp.json()["content"]
    assert "## Resume" in content
    assert "Ada" in content
    assert "Python, FastAPI" in content


def test_analysis_export_json_wraps_payload(api_db) -> None:
    resume_id = _seed(api_db)
    _override_api_db(api_db)
    try:
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/resume/{resume_id}/analysis-export?format=json")
    finally:
        _unoverride_api_db()
    assert resp.status_code == 200
    payload = json.loads(resp.json()["content"])
    assert payload["resume"]["filename"] == "cv.txt"
    assert payload["analysis"]["score"] == 70
    assert payload["analysis"]["interview_qa"][0]["question"] == "Explain the Agent Loop."


def test_analysis_export_without_review_is_404(api_db) -> None:
    resume_id = _seed(api_db, with_analysis=False)
    _override_api_db(api_db)
    try:
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/resume/{resume_id}/analysis-export?format=md")
    finally:
        _unoverride_api_db()
    assert resp.status_code == 404


def test_analysis_export_missing_resume_is_404(api_db) -> None:
    _override_api_db(api_db)
    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/resume/999/analysis-export?format=md")
    finally:
        _unoverride_api_db()
    assert resp.status_code == 404


def test_analysis_export_validation_error_uses_catalog(api_db, monkeypatch) -> None:
    from pydantic import ValidationError

    from realmock.domains.resume.schemas.analysis import ResumeAnalysis

    resume_id = _seed(api_db)

    # Exercise the validation boundary even when today's tolerant normalizer
    # can repair the stored payload.
    def reject(_payload):
        raise ValidationError.from_exception_data(
            "ResumeAnalysis", [{"type": "int_parsing", "loc": ("score",), "input": "bad"}]
        )

    monkeypatch.setattr(ResumeAnalysis, "model_validate", reject)
    _override_api_db(api_db)
    try:
        with TestClient(app) as client:
            for fmt in ("md", "json"):
                resp = client.get(f"/api/v1/resume/{resume_id}/analysis-export?format={fmt}")
                assert resp.status_code == 404
                assert resp.json()["error"]["code"] == "A1010"
    finally:
        _unoverride_api_db()
