"""Smoke test: the FastAPI application starts and its core routes are accessible."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok() -> None:
    """The health check endpoint should return ok."""
    from realmock.asgi import app

    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "service": "realmock",
            "version": "1.0.0",
        }


def test_options_endpoint_returns_companies() -> None:
    """/api/options should return role/level/company dropdown options."""
    from realmock.asgi import app

    with TestClient(app) as client:
        resp = client.get("/api/options")
        assert resp.status_code == 200
        data = resp.json()
        assert "roles" in data and len(data["roles"]) > 0
        assert "companies" in data and len(data["companies"]) > 0
        company_ids = {c["id"] for c in data["companies"]}
        assert "bytedance" in company_ids


def test_stage_settings_readable() -> None:
    """The three-stage settings endpoints should be readable (single settings path)."""
    from realmock.asgi import app

    # TestClient(app) triggers the lifespan hook, including init_db, only when entering the with block.
    with TestClient(app) as client:
        resp = client.get("/api/settings/stages")
        assert resp.status_code == 200
        body = resp.json()
        assert "recognize" in body and "reason" in body and "speak" in body