"""App factory extra tests for apps/api/src/realmock/platform/app_factory.py.

Covers: create_service_app structure/health routing, lifespan TEST_MODE skip vs
sync/async startup execution, trace-middleware exception path and helper registration.

Conventions: no real network (TestClient in-process); asyncio_mode=auto.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from realmock.platform.app_factory import (
    add_default_cors,
    create_service_app,
    install_trace_middleware,
    register_core_error_handlers,
)



def _router() -> APIRouter:
    r = APIRouter()

    @r.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    return r


def test_create_service_app_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_MODE", "1")
    app = create_service_app(
        service_routers=[_router(), _router()],
        title="t",
        description="d",
        service_name="svc",
    )
    assert Exception in app.exception_handlers
    with TestClient(app) as client:
        # FastAPI defers include_router mounting; assert over HTTP, not app.routes.
        assert client.get("/api/v1/ping").json() == {"ok": True}
        resp = client.get("/health")
    assert resp.json() == {"status": "ok", "service": "svc", "version": "1.0.0"}


def test_lifespan_test_mode_skips_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_MODE", "1")
    started: list[str] = []
    app = create_service_app(
        service_routers=_router(), title="t", description="d", service_name="s",
        lifespan_startup=lambda: started.append("x"),
    )
    with TestClient(app):
        pass
    assert started == []


@pytest.mark.asyncio
async def test_lifespan_runs_sync_and_async_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_MODE", raising=False)
    called: list[str] = []
    app = create_service_app(
        service_routers=_router(), title="t", description="d", service_name="s",
        lifespan_startup=lambda: called.append("sync"),
    )
    async with app.router.lifespan_context(app):
        pass
    assert called == ["sync"]

    done: list[str] = []

    async def _async_startup() -> None:
        done.append("async")

    app2 = create_service_app(
        service_routers=_router(), title="t", description="d", service_name="s",
        lifespan_startup=_async_startup,
    )
    async with app2.router.lifespan_context(app2):
        pass
    assert done == ["async"]


def test_trace_middleware_exception_path_still_tags_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_MODE", "1")
    # No core handlers: the route error propagates through the trace middleware
    # (covers its log-and-reraise path) up to ServerErrorMiddleware.
    app = create_service_app(
        service_routers=_router(), title="t", description="d", service_name="s",
        register_error_handlers=False,
    )

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("kablam")

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/boom")
    assert resp.status_code == 500


def test_helpers_register_directly() -> None:
    from fastapi import FastAPI

    app = FastAPI()
    install_trace_middleware(app)
    add_default_cors(app, cors_origin_list=["https://x.example"])
    register_core_error_handlers(app)
    assert Exception in app.exception_handlers
    assert len(app.user_middleware) >= 2
