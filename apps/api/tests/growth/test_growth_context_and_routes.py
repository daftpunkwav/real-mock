"""Growth context builder + insight routes + ingest trigger tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


def _report(sid: int, score: int) -> dict:
    return {
        "overall_score": score,
        "verdict": "passed" if score >= 60 else "failed",
        "score_breakdown": {"technical": score},
        "weaknesses": ["sql optimization", "system design"],
        "strengths": ["testing"],
        "training_plan": ["practice medium problems"],
        "key_problems": ["ran out of time"],
    }


def _snapshot(sid: int, score: int, *, report: dict | None = None, created: datetime | None = None):
    """Minimal snapshot stand-in (only fields the builder touches)."""
    snap = MagicMock()
    snap.id = sid
    snap.role = "后端"
    snap.company = "ACME"
    snap.level = "mid"
    snap.overall_score = score
    when = created or datetime(2026, 9, 1, tzinfo=timezone.utc)
    snap.ended_at = when
    snap.created_at = when
    snap.report = json.dumps(report if report is not None else _report(sid, score))
    return snap


# ---- context builder ----


def test_builder_aggregates_scored_sessions_only() -> None:
    from realmock.domains.growth.services.context_builder import build_growth_context

    catalog = MagicMock()
    catalog.list_sessions.return_value = [MagicMock(id=2, overall_score=70), MagicMock(id=1, overall_score=55), MagicMock(id=3, overall_score=None)]
    catalog.get_session.side_effect = lambda db, sid: {
        2: _snapshot(2, 70),
        1: _snapshot(1, 55),
    }[sid]

    with (
        patch("realmock.domains.growth.services.context_builder.get_session_catalog", return_value=catalog),
        patch(
            "realmock.domains.growth.services.context_builder.format_resume_analysis_summary",
            return_value="RESUME",
        ),
        patch(
            "realmock.domains.growth.services.context_builder.format_profile_summary",
            return_value="PROFILE",
        ),
    ):
        context = build_growth_context(MagicMock(), MagicMock())

    assert [s["session_id"] for s in context["sessions"]] == [2, 1]
    assert context["sessions"][0]["weaknesses"][0] == "sql optimization"
    assert context["resume_summary"] == "RESUME"
    assert context["profile_summary"] == "PROFILE"


def test_builder_skips_bad_report_json() -> None:
    from realmock.domains.growth.services.context_builder import build_growth_context

    catalog = MagicMock()
    catalog.list_sessions.return_value = [MagicMock(id=7, overall_score=40)]
    broken = _snapshot(7, 40, report=None)
    broken.report = "{not json"
    catalog.get_session.return_value = broken

    with (
        patch("realmock.domains.growth.services.context_builder.get_session_catalog", return_value=catalog),
        patch("realmock.domains.growth.services.context_builder.format_resume_analysis_summary", return_value=""),
        patch("realmock.domains.growth.services.context_builder.format_profile_summary", return_value=""),
    ):
        context = build_growth_context(MagicMock(), MagicMock())
    assert context["sessions"] == []


# ---- insight store + routes ----


@pytest.fixture
def _insight_table(engine):
    from realmock.platform.database import SessionsBase
    import realmock.domains.growth.models.insight  # noqa: F401

    SessionsBase.metadata.create_all(bind=engine)
    yield


def test_store_upsert_and_get(_insight_table) -> None:
    from realmock.domains.growth.services.insight_store import (
        upsert_insight,
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    first = upsert_insight(db, {"headline": "v1"}, locale="zh-CN", session_count=3)
    assert first is not None
    db.add.assert_called_once()


def test_insight_response_null_and_payload() -> None:
    from realmock.domains.growth.services.insight_store import insight_response

    assert insight_response(None) == {"insight": None}
    row = MagicMock()
    row.payload = json.dumps({"headline": "h"})
    row.updated_at = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
    row.session_count = 5
    row.locale = "zh-CN"
    body = insight_response(row)
    assert body["insight"]["headline"] == "h"
    assert body["insight"]["session_count"] == 5


def test_routes_insight_endpoints(_insight_table) -> None:
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


def _fake_db():

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    return db


# ---- ingest trigger ----


def test_ingest_schedules_regen_on_create() -> None:
    from realmock.domains.growth.services import ingest as mod
    from realmock.platform.contracts.report_summary import ReportSummaryPayload

    payload = ReportSummaryPayload(session_id=9201, overall_score=80)
    with (
        patch.object(mod, "persist_growth_from_summary", return_value=(MagicMock(), True)),
        patch.object(mod, "record_interview_learning"),
        patch.object(mod, "schedule_growth_insight_regen") as sched,
    ):
        mod.handle_report_summary(payload)
        sched.assert_called_once()


def test_ingest_no_regen_when_not_created() -> None:
    from realmock.domains.growth.services import ingest as mod
    from realmock.platform.contracts.report_summary import ReportSummaryPayload

    payload = ReportSummaryPayload(session_id=9202, overall_score=80)
    with (
        patch.object(mod, "persist_growth_from_summary", return_value=(MagicMock(), False)),
        patch.object(mod, "schedule_growth_insight_regen") as sched,
    ):
        mod.handle_report_summary(payload)
        sched.assert_not_called()


def test_ingest_regen_schedule_failure_swallowed() -> None:
    from realmock.domains.growth.services import ingest as mod
    from realmock.platform.contracts.report_summary import ReportSummaryPayload

    payload = ReportSummaryPayload(session_id=9203, overall_score=80)
    with (
        patch.object(mod, "persist_growth_from_summary", return_value=(MagicMock(), True)),
        patch.object(mod, "record_interview_learning"),
        patch.object(mod, "schedule_growth_insight_regen", side_effect=RuntimeError("no loop")),
    ):
        mod.handle_report_summary(payload)  # must not raise
