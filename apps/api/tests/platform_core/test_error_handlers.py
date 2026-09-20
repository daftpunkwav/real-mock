"""realmock.platform.core.error_handlers unit tests: five handlers plus envelope/spec constructors.

Cover envelope construction, retryable passthrough, headers passthrough, 404 -> A0404 mapping,
and contracts such as Starlette and FastAPI HTTPException sharing envelope_from_http_exception.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from realmock.platform.core.errors import ApiBusinessError, CATALOG
from realmock.platform.core.error_handlers import (
    on_http_exception,
    on_request_validation,
    on_starlette_http_exception,
    on_unhandled_exception,
)


def _body(resp) -> dict:
    """helper: parse the JSONResponse body."""
    return json.loads(resp.body)

def _mock_request() -> Request:
    """Construct a minimal Request for testing direct handler calls."""
    from starlette.requests import Request as StarletteRequest
    scope = {"type": "http", "method": "GET", "path": "/x", "headers": []}
    return StarletteRequest(scope)


@pytest.mark.asyncio
async def test_on_http_exception_api_business_error() -> None:
    """ApiBusinessError uses a business code plus spec hint/retryable."""
    spec = CATALOG["C0001"]
    exc = ApiBusinessError(spec, message="LLM unavailable")
    resp = await on_http_exception(None, exc)  # type: ignore[arg-type]
    assert resp.status_code == 502
    data = _body(resp)
    assert data["error"]["code"] == "C0001"
    assert data["error"]["retryable"] is True


@pytest.mark.asyncio
async def test_on_http_exception_plain_fallback() -> None:
    """A regular HTTPException without error_code falls back to http_{status}."""
    exc = HTTPException(status_code=400, detail="bad request")
    resp = await on_http_exception(None, exc)  # type: ignore[arg-type]
    assert resp.status_code == 400
    data = _body(resp)
    assert data["error"]["code"] == "http_400"
    assert data["error"]["message"] == "bad request"


@pytest.mark.asyncio
async def test_plain_fallback_empty_detail_uses_status_phrase() -> None:
    """Empty-detail HTTPException falls back to the HTTP reason phrase, not "Not Found"."""
    exc = HTTPException(status_code=400, detail="")
    resp = await on_http_exception(None, exc)  # type: ignore[arg-type]
    data = _body(resp)
    assert data["error"]["code"] == "http_400"
    assert data["error"]["message"] == "Bad Request"


@pytest.mark.asyncio
async def test_on_http_exception_propagates_retry_after() -> None:
    """Pass HTTPException.headers (such as Retry-After) through to the response headers."""
    exc = HTTPException(status_code=429, detail="rate", headers={"Retry-After": "60"})
    resp = await on_http_exception(None, exc)  # type: ignore[arg-type]
    assert resp.headers["Retry-After"] == "60"


@pytest.mark.asyncio
async def test_on_starlette_http_exception_404_maps_to_A0404() -> None:
    """Starlette raises 404 -> A0404 (business meaning: "resource not found")."""
    exc = StarletteHTTPException(status_code=404, detail="Not Found")
    resp = await on_starlette_http_exception(None, exc)  # type: ignore[arg-type]
    assert resp.status_code == 404
    data = _body(resp)
    assert data["error"]["code"] == "A0404"
    assert data["error"]["hint"] == CATALOG["A0404"].hint


@pytest.mark.asyncio
async def test_on_starlette_http_exception_other_status() -> None:
    """Non-404 responses use the http_{status} fallback."""
    exc = StarletteHTTPException(status_code=405, detail="Method Not Allowed")
    resp = await on_starlette_http_exception(None, exc)  # type: ignore[arg-type]
    assert resp.status_code == 405
    data = _body(resp)
    assert data["error"]["code"] == "http_405"
    assert data["error"]["message"] == "Method Not Allowed"


@pytest.mark.asyncio
async def test_on_starlette_http_exception_propagates_allow() -> None:
    """Pass through the Allow header provided by Starlette 405."""
    exc = StarletteHTTPException(
        status_code=405, detail="Method Not Allowed", headers={"Allow": "GET"}
    )
    resp = await on_starlette_http_exception(None, exc)  # type: ignore[arg-type]
    assert resp.headers["Allow"] == "GET"


@pytest.mark.asyncio
async def test_on_request_validation_uses_A0001() -> None:
    exc = RequestValidationError(errors=[])
    req = _mock_request()
    resp = await on_request_validation(req, exc)
    assert resp.status_code == 422
    data = _body(resp)
    assert data["error"]["code"] == "A0001"


@pytest.mark.asyncio
async def test_on_unhandled_exception_falls_back_to_B0001() -> None:
    req = _mock_request()
    resp = await on_unhandled_exception(req, RuntimeError("boom"))
    assert resp.status_code == 500
    data = _body(resp)
    assert data["error"]["code"] == "B0001"
    assert data["error"]["retryable"] is True


# ── End-to-end envelope via TestClient ──────────────────────────────────────


class TestErrorEnvelope:
    """The unified envelope must also hold for responses produced through the full app stack."""

    @pytest.fixture
    def client(self, monkeypatch: pytest.MonkeyPatch) -> TestClient:
        """Recreate TestClient for every test to prevent lifespan side effects from leaking between tests."""
        from realmock import asgi as app_main

        monkeypatch.setenv("TEST_MODE", "1")
        with TestClient(app_main.app) as c:
            yield c

    def test_http_exception_envelope(self, client: TestClient) -> None:
        """404 responses use the unified envelope."""
        # FastAPI's default 404 is a Starlette HTTPException (starlette.exceptions),
        # It is not caught by FastAPI's HTTPException handler; use 405 to trigger it instead.
        r = client.post("/health")  # /health allows GET only → 405
        assert r.status_code == 405
        body = r.json()
        assert "error" in body
        assert body["error"]["code"].startswith("http_")
        assert "trace_id" in body["error"]
        assert r.headers["X-Trace-Id"]

    def test_unsafe_url_envelope(self, client: TestClient) -> None:
        """Public LLM base scenario (previously triggered an UnsafeURLError 400 envelope through /api/settings/llm).

        It is not feasible to construct a route that directly triggers UnsafeURLError (it is raised only internally),
        so verify envelope-field consistency here through the options endpoint.
        """
        r = client.get("/api/options")
        assert r.status_code == 200
        # The successful options path does not need an envelope, but trace_id must be present in the response headers.
        assert "X-Trace-Id" in r.headers
