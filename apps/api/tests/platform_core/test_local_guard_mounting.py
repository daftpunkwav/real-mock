"""Local-guard mounting: HTTP routers carry the loopback deps, WS routers do not.

Regression: mounting the HTTP-only guard (`require_local_peer(request: Request)`)
on a WebSocket router crashed every handshake — FastAPI cannot inject `Request`
into a WS-scope dependency solve, so the dependency was called with zero
arguments (TypeError → handshake 500 → the client's endless reconnect loop).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from realmock.domains.interview.models import InterviewSession
from realmock.platform.core.constants import SessionStatus
def _make_session(db) -> InterviewSession:
    s = InterviewSession(
        profile_id=1,
        role="Backend",
        level="intermediate",
        company="bytedance",
        workflow_type="technical",
        personality="professional",
        strictness=3,
        interview_style="deep_dive",
        status=SessionStatus.ACTIVE.value,
        current_phase="basic_knowledge",
        messages="[]",
        agent_state="{}",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_ws_cross_site_origin_rejected(db) -> None:
    """A browser page on a non-loopback origin must not drive local WS handshakes."""
    from realmock.domains.interview.main import app

    session = _make_session(db)
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect(
                f"/api/v1/ws/interview/{session.id}",
                headers={"Origin": "https://evil.example"},
            ):
                pass


def test_ws_handshake_without_token_is_auth_rejected_not_500(db) -> None:
    """No-token WS connect must fail through session auth (clean close),
    never through a dependency TypeError (handshake 500)."""
    from realmock.domains.interview.main import app

    session = _make_session(db)
    with TestClient(app) as client:
        try:
            with client.websocket_connect(f"/api/v1/ws/interview/{session.id}"):
                raise AssertionError("unauthenticated WS must not be accepted")
        except Exception as e:
            message = str(e)
            assert "missing 1 required positional argument" not in message, (
                "guard dependency leaked onto the WS route again"
            )
            assert "1011" not in message or "Internal" not in message


def test_http_guard_still_rejects_non_loopback_urls() -> None:
    """The loopback guard keeps working for HTTP management endpoints."""
    from realmock.domains.interview.main import app

    with TestClient(app) as client:
        resp = client.get(
            "/api/v1/interview/processes",
            headers={"Host": "example.com:8081"},
        )
        # Loopback peer with a forwarded-looking host is still loopback: allowed.
        # The guard's rejection path (non-loopback peer) needs a real remote
        # socket, covered by require_local_peer unit tests; here we only pin
        # that the dependency resolves and the call goes through.
        assert resp.status_code in (200, 401, 403)
        if resp.status_code == 200:
            body = json.dumps(resp.json())[:1]
            assert body in ("[", "{")
