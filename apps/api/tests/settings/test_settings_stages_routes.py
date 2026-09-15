"""Stages-route tests for realmock.domains.settings.routes.stages.

Covers: catalog retrieval, stage updates, and timed pipeline tests
  for recognize/reason/speak aliases plus invalid-stage handling.
Conventions: stage services faked; HTTP via TestClient; no network.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import realmock.domains.settings.routes.stages as stages_mod
from realmock.asgi import app
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def _stage_response() -> dict:
    return {
        "stage": "reason",
        "provider": "custom",
        "api_base": "",
        "protocol": "openai_chat",
        "model": "m",
        "max_tokens": 100,
        "context_window": 1000,
        "capabilities": {},
        "fallback": {},
        "extras": {},
        "has_api_key": False,
    }


def test_get_catalog() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/v1/settings/catalog")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


def test_update_stage_invalid() -> None:
    with TestClient(app) as client:
        resp = client.put("/api/v1/settings/stages/bogus", json={"provider": "local"})
    assert resp.status_code == 400


def test_update_stage_ok(monkeypatch) -> None:
    row = MagicMock()
    monkeypatch.setattr(stages_mod, "safe_base", lambda *a, **k: None)
    monkeypatch.setattr(stages_mod, "validate_stage_config", lambda *a, **k: None)
    monkeypatch.setattr(stages_mod, "update_stage_config", lambda db, stage, body: row)
    monkeypatch.setattr(stages_mod, "stage_to_response", lambda r: _stage_response())
    with TestClient(app) as client:
        resp = client.put("/api/v1/settings/stages/reason", json={"provider": "custom"})
    assert resp.status_code == 200
    assert resp.json()["provider"] == "custom"


@pytest.mark.asyncio
async def test_pipeline_stage_recognize(monkeypatch) -> None:
    fake = {
        "success": True, "message": "ok", "model": "m", "transcript": "hi",
        "audio_base64": None, "fallback": None, "latency_ms": 5,
    }

    def _inner(db):
        return {"ignored": True}

    monkeypatch.setattr(stages_mod, "test_recognize", _inner)
    monkeypatch.setattr(stages_mod, "run_timed_stage_test", AsyncMock(return_value=fake))
    with TestClient(app) as client:
        resp = client.post("/api/v1/settings/test/recognize")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_pipeline_stage_reason_aliases(monkeypatch) -> None:
    fake = {"success": True, "message": "ok", "model": "m"}

    def _inner(db):
        return {"ignored": True}

    monkeypatch.setattr(stages_mod, "test_reason", _inner)
    monkeypatch.setattr(stages_mod, "run_timed_stage_test", AsyncMock(return_value=fake))
    for stage in ("reason", "reasoning", "llm"):
        with TestClient(app) as client:
            resp = client.post(f"/api/v1/settings/test/{stage}")
        assert resp.status_code == 200, stage


@pytest.mark.asyncio
async def test_pipeline_stage_speak_aliases(monkeypatch) -> None:
    fake = {"success": True, "message": "ok"}

    def _inner(db):
        return {"ignored": True}

    monkeypatch.setattr(stages_mod, "test_speak", _inner)
    monkeypatch.setattr(stages_mod, "run_timed_stage_test", AsyncMock(return_value=fake))
    for stage in ("speak", "tts"):
        with TestClient(app) as client:
            resp = client.post(f"/api/v1/settings/test/{stage}")
        assert resp.status_code == 200, stage


@pytest.mark.asyncio
async def test_pipeline_stage_invalid() -> None:
    with TestClient(app) as client:
        resp = client.post("/api/v1/settings/test/bogus")
    assert resp.status_code == 400
