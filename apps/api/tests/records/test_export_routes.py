"""Export route/service tests: report + record exports in md and json.

Covers: happy paths, capability-token enforcement, missing session/report
errors, and the transcript rendering rules (interviewer/candidate split,
invisible assistant lines dropped).
Conventions: session catalog faked; report rows written into the temp
sessions DB; TestClient for HTTP.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.records.models.report import InterviewReportRow
from realmock.domains.records.schemas.report import DebriefReport
from realmock.domains.records.services import export as export_service
from realmock.domains.records.services.report_store import persist_ready
from realmock.platform.core.ratelimit import reset_rate_limit
from realmock.platform.database import get_sessions_db


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


@pytest.fixture(autouse=True)
def _clean_report_rows(db):
    """The conftest DB files live for the whole pytest session; drop report
    rows between tests so report-presence assertions stay order-independent."""
    yield
    db.query(InterviewReportRow).delete()
    db.commit()


def _snapshot(**over) -> dict:
    base = {
        "id": 1,
        "role": "AI Engineer",
        "level": "Intern",
        "company": "mihoyo",
        "status": "completed",
        "current_phase": "summary",
        "overall_score": 72,
        "access_token": None,  # nosec B105 - tokenless test snapshot
        "messages": "[]",
        "ledger": {"frozen": True, "turns": []},
    }
    base.update(over)
    return base


def _catalog(snap: dict, ledger: dict | None = None) -> MagicMock:
    cat = MagicMock()
    cat.get_session_snapshot.return_value = snap
    cat.get_ledger.return_value = ledger if ledger is not None else snap.get("ledger")
    return cat


def _override_sessions_db(db):
    app.dependency_overrides[get_sessions_db] = lambda: db


def _unoverride_sessions_db():
    app.dependency_overrides.pop(get_sessions_db, None)


@contextmanager
def export_client(catalog: MagicMock, *, lift_token: bool = True) -> Iterator[TestClient]:
    """TestClient with the session catalog faked; the capability-token check
    is lifted unless the test exercises the mismatch path itself."""
    with (
        patch.object(export_service, "get_session_catalog", return_value=catalog),
        patch.object(export_service, "assert_session_token", return_value=None)
        if lift_token
        else nullcontext(),
        TestClient(app) as client,
    ):
        yield client


def _ready_report(db, session_id: int = 1) -> None:
    report = DebriefReport(
        overall_score=72,
        verdict="failed",
        highlights=["good structure"],
        key_problems=["shallow follow-ups"],
        training_plan=["drill daily"],
        turn_notes=[],
    )
    persist_ready(
        db,
        session_id=session_id,
        report=report,
        model_meta={"model": "test"},
    )


# --- report exports -----------------------------------------------------------


def test_report_export_markdown(db) -> None:
    _ready_report(db)
    _override_sessions_db(db)
    try:
        with export_client(_catalog(_snapshot())) as client:
            resp = client.get("/api/v1/records/export/report/1?format=md")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "interview-report-1.md"
    assert body["mime"].startswith("text/markdown")
    assert "# AI Engineer — Interview Report" in body["content"]
    assert "**Overall score**: 72" in body["content"]
    assert "- good structure" in body["content"]


def test_report_export_json_carries_full_payload(db) -> None:
    _ready_report(db)
    _override_sessions_db(db)
    try:
        with export_client(_catalog(_snapshot())) as client:
            resp = client.get("/api/v1/records/export/report/1?format=json")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 200
    body = resp.json()
    payload = json.loads(body["content"])
    assert payload["session"]["company"] == "mihoyo"
    assert payload["report"]["overall_score"] == 72
    assert payload["report"]["verdict"] == "failed"


def test_report_export_without_report_is_404(db) -> None:
    _override_sessions_db(db)
    try:
        with export_client(_catalog(_snapshot())) as client:
            resp = client.get("/api/v1/records/export/report/1?format=md")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 404


def test_report_export_unfinished_session_is_400(db) -> None:
    snap = _snapshot(status="interviewing", ledger_frozen=False)
    _override_sessions_db(db)
    try:
        with export_client(_catalog(snap)) as client:
            resp = client.get("/api/v1/records/export/report/1?format=md")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 400


def test_report_export_pending_report_is_404(db) -> None:
    row = InterviewReportRow(session_id=1, status="pending", payload="{}")
    db.add(row)
    db.commit()
    _override_sessions_db(db)
    try:
        with export_client(_catalog(_snapshot())) as client:
            resp = client.get("/api/v1/records/export/report/1?format=md")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 404


def test_report_export_failed_report_is_409(db) -> None:
    row = InterviewReportRow(session_id=1, status="failed", payload="{}")
    db.add(row)
    db.commit()
    _override_sessions_db(db)
    try:
        with export_client(_catalog(_snapshot())) as client:
            resp = client.get("/api/v1/records/export/report/1?format=md")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 409


def test_export_token_mismatch_is_403(db) -> None:
    _override_sessions_db(db)
    try:
        with export_client(
            _catalog(_snapshot(access_token="secret")),  # nosec B106 - fake test token
            lift_token=False,
        ) as client:
            resp = client.get("/api/v1/records/export/record/1?format=md")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 403


def test_export_missing_session_is_404(db) -> None:
    _override_sessions_db(db)
    try:
        cat = MagicMock()
        cat.get_session_snapshot.return_value = None
        with export_client(cat) as client:
            resp = client.get("/api/v1/records/export/record/99?format=md")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 404


# --- record exports -----------------------------------------------------------


def _ledger() -> dict:
    return {
        "frozen": True,
        "turns": [
            {
                "turn_id": "t-0001",
                "assistant": {"text": "Introduce yourself.", "visible": True},
                "user": {"text": "Hi, I am the candidate.", "source": "stt"},
            },
            {
                "turn_id": "t-0002",
                "assistant": {"text": "(internal) hidden", "visible": False},
                "user": {"text": "Answer two.", "source": "stt"},
            },
        ],
    }


def test_record_export_markdown_splits_speakers(db) -> None:
    _override_sessions_db(db)
    try:
        with export_client(_catalog(_snapshot(), _ledger())) as client:
            resp = client.get("/api/v1/records/export/record/1?format=md")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "interview-record-1.md"
    assert "**Interviewer**:" in body["content"]
    assert "Introduce yourself." in body["content"]
    assert "**Candidate**:" in body["content"]
    # Invisible assistant lines are internal state and must not leak.
    assert "hidden" not in body["content"]
    assert "no AI evaluation" in body["content"]


def test_record_export_unfinished_session_is_400(db) -> None:
    snap = _snapshot(status="interviewing", ledger_frozen=False)
    _override_sessions_db(db)
    try:
        with export_client(_catalog(snap, {"turns": []})) as client:
            resp = client.get("/api/v1/records/export/record/1?format=md")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 400


def test_record_export_json_wraps_turns(db) -> None:
    _override_sessions_db(db)
    try:
        with export_client(_catalog(_snapshot(), _ledger())) as client:
            resp = client.get("/api/v1/records/export/record/1?format=json")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 200
    payload = json.loads(resp.json()["content"])
    assert len(payload["record"]["turns"]) == 2
    assert payload["record"]["turns"][0]["assistant"]["text"] == "Introduce yourself."
