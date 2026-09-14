"""``app_factory``/``asgi`` entry-point and middleware behavior tests.

Coverage:

- trace_middleware: preserve a valid X-Request-Id, regenerate an invalid value, and return it in the response headers;
- Strict CORS policy: prod + wildcard origins should fail at startup (monkeypatch settings);
- X-Request-Id sanitization rules.
"""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Recreate TestClient for every test to prevent lifespan side effects from leaking between tests.

    Reuse the module-level ``app_main.app`` directly; TestClient.__enter__ triggers lifespan.
    """
    from realmock import asgi as app_main

    # Disable lifespan engine disposal during tests.
    monkeypatch.setenv("TEST_MODE", "1")
    with TestClient(app_main.app) as c:
        yield c


# ── trace_middleware ────────────────────────────────────────


class TestTraceMiddleware:
    def test_generates_trace_id_when_missing(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        assert "X-Trace-Id" in r.headers
        # uuid4 hex (32); test only pins >=16
        tid = r.headers["X-Trace-Id"]
        assert len(tid) >= 16

    def test_propagates_valid_request_id(self, client: TestClient) -> None:
        rid = "abc123XYZ_-rest"  # 15 characters, including _-
        r = client.get("/health", headers={"X-Request-Id": rid})
        assert r.headers["X-Trace-Id"] == rid

    def test_rejects_invalid_request_id(self, client: TestClient) -> None:
        """An X-Request-Id containing spaces or control characters, or one that is too short or too long (>64), should be discarded and regenerated."""
        for bad in ["bad value", "short", "a" * 200, "x" * 5, "has\nnewline"]:
            r = client.get("/health", headers={"X-Request-Id": bad})
            tid = r.headers["X-Trace-Id"]
            assert tid != bad, f"An invalid request_id should not be echoed: {bad!r}"
            assert len(tid) >= 16

    def test_response_trace_id_consistent_across_request(self, client: TestClient) -> None:
        r1 = client.get("/health")
        r2 = client.get("/health")
        # Different requests should use different trace_id values (independent contexts)
        assert r1.headers["X-Trace-Id"] != r2.headers["X-Trace-Id"]


# ── Strict CORS policy ────────────────────────────────────────


class TestCORSStrictness:
    def test_prod_wildcard_origins_fails_to_start(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Production mode (env=prod) with wildcard origins must fail at startup."""
        from realmock.platform.config import Settings
        from realmock import asgi as app_main

        s = Settings(env="prod", cors_origins="*")
        with pytest.raises(RuntimeError, match="does not allow allow_origins"):
            app_main._check_cors_policy(s)

    def test_prod_explicit_origins_ok(self) -> None:
        from realmock.platform.config import Settings
        from realmock import asgi as app_main

        s = Settings(env="prod", cors_origins="https://app.example.com")
        # Should not throw
        assert app_main._check_cors_policy(s) is None

    def test_dev_wildcard_only_warns(self) -> None:
        from realmock.platform.config import Settings
        from realmock import asgi as app_main

        s = Settings(env="dev", cors_origins="*")
        # Should not throw
        assert app_main._check_cors_policy(s) is None


# ── X-Request-Id validation function ────────────────────────────────────────


class TestSanitizeRequestId:
    def test_accepts_valid(self) -> None:
        from realmock.platform.app_factory import _sanitize_request_id

        assert _sanitize_request_id("abcdef123456") == "abcdef123456"
        assert _sanitize_request_id("a-b_c-12345678") == "a-b_c-12345678"

    def test_rejects_invalid(self) -> None:
        from realmock.platform.app_factory import _sanitize_request_id

        for bad in ["", "short", "has space", "has/slash", "a" * 200, None]:
            assert _sanitize_request_id(bad) is None, f"Should be rejected: {bad!r}"
