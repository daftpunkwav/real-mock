"""Deployment-exposure guard regressions.

Subjects:
- local-only peer check (ENV=prod must not honor TEST_MODE for non-loopback peers);
- SSRF URL safety (CGNAT / multicast blocks);
- production rejects query-string tokens on WS and HTTP (header token still works);
- mount-level cross-site guard covers every service router (A0403), /health exempt.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from realmock.platform.core.local_only import require_local_peer
from realmock.platform.core.security import is_safe_http_url
from realmock.platform.core.session_auth import extract_ws_token


def test_local_only_prod_ignores_test_mode(monkeypatch):
    """When env=prod, TEST_MODE must not allow non-loopback addresses."""
    from realmock.platform.config import get_settings

    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("ENV", "prod")
    get_settings.cache_clear()

    req = MagicMock()
    req.client.host = "192.168.1.10"
    with pytest.raises(HTTPException) as ei:
        require_local_peer(req)
    assert ei.value.status_code == 403

    monkeypatch.setenv("ENV", "dev")
    get_settings.cache_clear()


def test_local_only_testclient_always_ok(monkeypatch):
    from realmock.platform.config import get_settings

    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("TEST_MODE", "1")
    get_settings.cache_clear()
    req = MagicMock()
    req.client.host = "testclient"
    require_local_peer(req)  # Does not throw
    monkeypatch.setenv("ENV", "dev")
    get_settings.cache_clear()


def test_ssrf_blocks_cgnat():
    assert is_safe_http_url("http://100.64.1.1/") is False
    assert is_safe_http_url("http://100.64.0.1/v1") is False


def test_ssrf_blocks_multicast():
    assert is_safe_http_url("http://224.0.0.1/") is False


def test_prod_rejects_ws_query_token(monkeypatch):
    from realmock.platform.config import get_settings

    monkeypatch.setenv("ENV", "prod")
    get_settings.cache_clear()

    ws = MagicMock()
    ws.cookies = {}
    ws.headers = {}
    tok, sub = extract_ws_token(ws, session_id=1, query_token="secret-token-value")
    assert tok == ""
    assert sub is None

    monkeypatch.setenv("ENV", "dev")
    get_settings.cache_clear()
    tok2, _ = extract_ws_token(ws, session_id=1, query_token="secret-token-value")
    assert tok2 == "secret-token-value"


def test_prod_rejects_http_query_token(monkeypatch):
    """In production, HTTP extraction ignores the query token while the Header remains supported."""
    from realmock.platform.config import get_settings
    from realmock.platform.core import session_auth as sa

    monkeypatch.setenv("ENV", "prod")
    get_settings.cache_clear()

    req = MagicMock()
    req.cookies = {}
    req.method = "GET"
    req.url.path = "/api/v1/interview/sessions/1"
    req.headers = {}

    assert (
        sa._extract_from_request(
            req,
            scope="iv",
            session_id=1,
            x_interview_token=None,
            token="secret-query-token",
        )
        is None
    )
    assert (
        sa._extract_from_request(
            req,
            scope="iv",
            session_id=1,
            x_interview_token="header-token-value-ok",
            token="secret-query-token",
        )
        == "header-token-value-ok"
    )

    monkeypatch.setenv("ENV", "dev")
    get_settings.cache_clear()
    assert (
        sa._extract_from_request(
            req,
            scope="iv",
            session_id=1,
            x_interview_token=None,
            token="secret-query-token",
        )
        == "secret-query-token"
    )


def test_create_and_list_sessions_require_local_peer():
    """Session creation/listing depends on require_local_peer; overriding it should result in 403."""
    from realmock.asgi import app

    def _deny() -> None:
        raise HTTPException(status_code=403, detail="Allow management API access from localhost only")

    app.dependency_overrides[require_local_peer] = _deny
    try:
        client = TestClient(app)
        create = client.post(
            "/api/v1/interview/sessions",
            json={
                "role": "Backend engineer",
                "level": "intermediate",
                "company": "bytedance",
                "workflow_type": "technical",
                "personality": "professional",
                "strictness": 3,
                "interview_style": "deep_dive",
            },
        )
        assert create.status_code == 403, create.text
        listed = client.get("/api/v1/interview/sessions")
        assert listed.status_code == 403, listed.text
        prep = client.post(
            "/api/v1/prep/sessions",
            json={"target_role": "Backend", "target_company": "bytedance"},
        )
        assert prep.status_code == 403, prep.text
    finally:
        app.dependency_overrides.pop(require_local_peer, None)


def test_create_session_ok_via_testclient():
    """Session creation should succeed when TestClient peer=testclient."""
    from realmock.asgi import app

    client = TestClient(app)
    r = client.post(
        "/api/v1/interview/sessions",
        json={
            "role": "Backend engineer",
            "level": "intermediate",
            "company": "bytedance",
            "workflow_type": "technical",
            "personality": "professional",
            "strictness": 3,
            "interview_style": "deep_dive",
        },
    )
    assert r.status_code == 200, r.text
    assert "id" in r.json()
    listed = client.get("/api/v1/interview/sessions")
    assert listed.status_code == 200, listed.text


def test_cross_site_rejected_across_all_service_routers():
    """Cross-site protection applies uniformly at the mount layer: every service route returns A0403.

    Previously only the resume domain had this protection, so settings / interview / prep write endpoints
    (including provider deletion and connectivity tests that consume a key) could be blindly targeted by malicious pages through loopback authentication;
    moving the protection to the mount layer covers all five service routes.
    """
    from realmock.asgi import app

    client = TestClient(app)
    targets = [
        ("get", "/api/v1/profile"),
        ("get", "/api/v1/resume/list"),
        ("get", "/api/v1/settings/providers"),
        ("get", "/api/v1/interview/sessions"),
        ("get", "/api/v1/prep/sessions"),
        # The legacy compatibility alias prefix is protected as well
        ("get", "/api/resume/list"),
    ]
    for method, url in targets:
        resp = client.request(method, url, headers={"Sec-Fetch-Site": "cross-site"})
        assert resp.status_code == 403, (method, url, resp.status_code, resp.text[:200])
        assert resp.json()["error"]["code"] == "A0403", (method, url)


def test_health_and_same_site_unaffected_by_mount_level_guard():
    """/health is outside the mount scope; allow same-site requests and non-browser clients without Sec-Fetch-Site."""
    from realmock.asgi import app

    client = TestClient(app)
    health = client.get("/health", headers={"Sec-Fetch-Site": "cross-site"})
    assert health.status_code == 200
    ok = client.get("/api/v1/resume/list", headers={"Sec-Fetch-Site": "same-site"})
    assert ok.status_code == 200
    no_header = client.get("/api/v1/resume/list")
    assert no_header.status_code == 200
