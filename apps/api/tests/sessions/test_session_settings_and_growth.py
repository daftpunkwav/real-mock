"""Session fix: saving settings uses unified format validation; corrupted growth JSON degrades gracefully."""

from __future__ import annotations

import inspect

from fastapi.testclient import TestClient

from realmock.domains.growth.models import GrowthRecord
from realmock.domains.growth.routes.router import _safe_json_list
from realmock.domains.settings.routes.stages import (
    test_pipeline_stage as stage_test_endpoint,
    update_stage,
)
from realmock.asgi import app


def test_update_stage_uses_safe_base_not_env_flag() -> None:
    """Route all save paths through safe_base (format validation only); do not relax validation based on the development-environment string."""
    src = inspect.getsource(update_stage)
    assert "safe_base" in src
    assert "_is_dev()" not in src


def test_stage_test_entry_routes_to_reason() -> None:
    """The connectivity-test entry point for the reason stage exists and is dispatched by test/{stage}."""
    src = inspect.getsource(stage_test_endpoint)
    assert "test_reason" in src


def test_growth_history_tolerates_bad_json(db) -> None:
    rec = GrowthRecord(
        profile_id=1,
        session_id=9_001_001,  # unique; avoid clashing with other tests
        weak_skills="NOT-JSON{{{",
        common_mistakes="[]",
        training_plan='{"oops": true}',  # object not list
    )
    db.add(rec)
    db.commit()

    with TestClient(app) as client:
        resp = client.get("/api/v1/growth/history")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    # Must include at least our invalid record, with its fields degraded
    hit = [r for r in body if r.get("id") == rec.id]
    assert hit
    assert hit[0]["weak_skills"] == []
    assert hit[0]["training_plan"] == []


def test_safe_json_list_helper() -> None:
    assert _safe_json_list(None, field="x", record_id=1) == []
    assert _safe_json_list("[]", field="x", record_id=1) == []
    assert _safe_json_list('["a"]', field="x", record_id=1) == ["a"]
    assert _safe_json_list("{bad", field="x", record_id=1) == []
