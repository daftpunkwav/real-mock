"""HTTP contract for POST /resume/{id}/analyze body parsing and missing rows.

Empty / null JSON defaults locale to zh-CN so the frontend `request()` JSON
Content-Type does not 422. Invalid JSON and non-objects are A0001.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.platform.models import Resume


def _seed_resume(api_db) -> Resume:
    row = Resume(filename="a.pdf", file_type="pdf", raw_text="body", parsed_profile="{}")
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    return row


def _stub_analyze(monkeypatch, expected_locale: str):
    from realmock.domains.resume.routes import analyze as analyze_route
    from realmock.domains.resume.schemas.analysis import ResumeAnalysis

    async def fake_analyze(r, db, *, locale=None, on_event=None):
        assert locale == expected_locale
        if on_event is not None:
            maybe = on_event(
                {
                    "type": "plan",
                    "steps": [
                        {
                            "id": "1",
                            "title": "Generate evaluation JSON",
                            "status": "done",
                            "note": "",
                        }
                    ],
                }
            )
            if maybe is not None:
                await maybe
        return ResumeAnalysis(score=1, headline="h")

    monkeypatch.setattr(analyze_route, "analyze_resume_with_llm", fake_analyze)


def test_analyze_missing_row_is_a1005(api_db) -> None:
    with TestClient(app) as client:
        resp = client.post("/api/v1/resume/999003/analyze", json={"locale": "zh-CN"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "A1005"


def test_analyze_empty_json_body_defaults_locale(api_db, monkeypatch) -> None:
    """Empty body must not 422; locale defaults to zh-CN."""
    row = _seed_resume(api_db)
    _stub_analyze(monkeypatch, "zh-CN")
    with TestClient(app) as client:
        resp = client.post(
            f"/api/v1/resume/{row.id}/analyze",
            content=b"",
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert resp.json()["score"] == 1


def test_analyze_json_null_and_empty_object_default_locale(api_db, monkeypatch) -> None:
    """`null` and `{}` are treated as missing body, not 422."""
    row = _seed_resume(api_db)
    _stub_analyze(monkeypatch, "zh-CN")
    with TestClient(app) as client:
        null_resp = client.post(
            f"/api/v1/resume/{row.id}/analyze",
            content=b"null",
            headers={"Content-Type": "application/json"},
        )
        empty_resp = client.post(f"/api/v1/resume/{row.id}/analyze", json={})
    assert null_resp.status_code == 200
    assert empty_resp.status_code == 200
    assert empty_resp.json()["score"] == 1


def test_analyze_forwards_en_locale(api_db, monkeypatch) -> None:
    row = _seed_resume(api_db)
    _stub_analyze(monkeypatch, "en")
    with TestClient(app) as client:
        resp = client.post(f"/api/v1/resume/{row.id}/analyze", json={"locale": "en"})
    assert resp.status_code == 200
    assert resp.json()["score"] == 1


def test_analyze_invalid_json_is_a0001(api_db) -> None:
    row = _seed_resume(api_db)
    with TestClient(app) as client:
        resp = client.post(
            f"/api/v1/resume/{row.id}/analyze",
            content=b"{not-json",
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "A0001"


def test_analyze_non_object_body_is_a0001(api_db) -> None:
    row = _seed_resume(api_db)
    with TestClient(app) as client:
        resp = client.post(f"/api/v1/resume/{row.id}/analyze", json=["en"])
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "A0001"


def test_analyze_invalid_locale_is_a0001(api_db) -> None:
    row = _seed_resume(api_db)
    with TestClient(app) as client:
        resp = client.post(f"/api/v1/resume/{row.id}/analyze", json={"locale": "fr"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "A0001"


def test_analyze_stream_emits_plan_and_done(api_db, monkeypatch) -> None:
    row = _seed_resume(api_db)
    _stub_analyze(monkeypatch, "en")
    with TestClient(app) as client:
        with client.stream(
            "POST",
            f"/api/v1/resume/{row.id}/analyze/stream",
            json={"locale": "en"},
        ) as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())
    assert '"type": "plan"' in body
    assert '"type": "done"' in body
    assert '"score": 1' in body
