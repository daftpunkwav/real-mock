"""Recommended-vendors route tests (GET /api/v1/settings/vendors).

The registry (platform/vendors) has its own unit tests; this file guards the
route layer: the endpoint is mounted, returns the two-level tree, and the
settings-page contract (vendor ids, capability keys, adapted flags) survives
refactors. Conventions: TestClient + reset_rate_limit, no DB rows needed
(the payload is derived from static catalogs/defs).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture()
def client():
    reset_rate_limit()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        reset_rate_limit()


def test_vendors_endpoint_returns_tree(client) -> None:
    res = client.get("/api/v1/settings/vendors")
    assert res.status_code == 200, res.text
    payload = res.json()
    vendors = payload["vendors"]
    assert isinstance(vendors, list) and vendors
    ids = [v["id"] for v in vendors]
    assert "minimax" in ids
    # Placeholders are never recommended to the settings page.
    assert "custom" not in ids and "local" not in ids


def test_vendors_endpoint_capability_contract(client) -> None:
    res = client.get("/api/v1/settings/vendors")
    assert res.status_code == 200, res.text
    minimax = next(v for v in res.json()["vendors"] if v["id"] == "minimax")
    assert minimax["label"] == "MiniMax"
    for cap_id, cap in minimax["capabilities"].items():
        assert cap_id in ("reasoning", "recognize", "speak")
        # The "add provider" cascade prefills from these fields.
        assert cap["provider_id"], cap_id
        assert cap["default_model"], cap_id
        assert cap["adapted"] is True
        assert isinstance(cap["def"]["request"], dict)
