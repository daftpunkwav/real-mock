"""Growth router tests for src/realmock/domains/growth/routes/router.py.

Covers: system-insights github flag, aggregated stats, _safe_json_list
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient
from realmock.asgi import app
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


@pytest.fixture(autouse=True)
def _growth_table(engine):
    from realmock.platform.database import SessionsBase
    import realmock.domains.growth.models.growth  # noqa: F401

    SessionsBase.metadata.create_all(bind=engine)
    yield


# ---- routes/router (59-67, 73-74) ----


def test_growth_system_insights_includes_github_flag(monkeypatch) -> None:
    import importlib

    mod = importlib.import_module("realmock.domains.growth.routes.router")

    monkeypatch.setattr(mod, "get_system_insights", lambda limit=15: {"a": 1})
    monkeypatch.setattr(
        "realmock.platform.capabilities.integrations.github.token_store.has_stored_token",
        lambda: False,
    )
    with TestClient(app) as client:
        resp = client.get("/api/growth/system-insights")
    assert resp.status_code == 200
    assert resp.json()["a"] == 1
    assert "github_token_configured" in resp.json()


def test_growth_aggregated_stats(db) -> None:
    from realmock.domains.growth.models.growth import GrowthRecord

    row = GrowthRecord(session_id=9001, weak_skills="[]", training_plan="[]")
    db.add(row)
    db.commit()
    with TestClient(app) as client:
        resp = client.get("/api/growth/aggregated")
    assert resp.status_code == 200


def test_safe_json_list_bad_payload() -> None:
    from realmock.domains.growth.routes.router import _safe_json_list

    assert _safe_json_list(None, field="weak_skills", record_id=1) == []
    assert _safe_json_list('{"a":1}', field="weak_skills", record_id=1) == []
    assert _safe_json_list("not-json", field="weak_skills", record_id=1) == []


# ---- ingest (29-31, 34-35, 50-51) ----










# ---- learning (73-75, 90, 96-97) ----


