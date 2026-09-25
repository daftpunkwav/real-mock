"""Growth insight HTTP route tests (GET read shape / POST refresh)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _fake_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    return db


async def _stub_regen(*, locale: str = "zh-CN"):
    return None


def test_routes_insight_endpoints(insight_table) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from realmock.domains.growth.routes import router as growth_router
    from realmock.platform.database import get_sessions_db

    app = FastAPI()
    app.include_router(growth_router, prefix="/growth")
    app.dependency_overrides[get_sessions_db] = _fake_db
    client = TestClient(app)

    body = client.get("/growth/insight").json()
    assert body["insight"] is None and body["status"] == "empty"

    with patch(
        "realmock.domains.growth.routes.router.schedule_growth_insight_regen",
        return_value=True,
    ) as sched:
        resp = client.post("/growth/insight/refresh", params={"locale": "en"})
    assert resp.status_code == 200
    assert resp.json() == {"scheduled": True, "status": "ready"}
    sched.assert_called_once_with(locale="en")


def test_routes_refresh_schedules_on_event_loop(insight_table) -> None:
    """Regression: the real scheduler needs the serving event loop.

    A sync route runs in the threadpool where no loop exists, so the refresh
    endpoint always returned ``scheduled: false`` and never spawned a regen.
    The route must stay async; only the regen coroutine itself is stubbed.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from realmock.domains.growth.routes import router as growth_router
    from realmock.domains.growth.services import insight_scheduler as sched

    app = FastAPI()
    app.include_router(growth_router, prefix="/growth")
    client = TestClient(app)

    with patch.object(sched, "regenerate_growth_insight", _stub_regen):
        resp = client.post("/growth/insight/refresh", params={"locale": "en"})
    assert resp.status_code == 200
    assert resp.json()["scheduled"] is True
