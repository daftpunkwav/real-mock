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
    """Reset the in-memory rate-limit buckets around each test."""
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
    """A completed session snapshot dict; keyword overrides adjust fields."""
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
    """A session-catalog double returning the given snapshot and ledger."""
    cat = MagicMock()
    cat.get_session_snapshot.return_value = snap
    cat.get_ledger.return_value = ledger if ledger is not None else snap.get("ledger")
    return cat


def _override_sessions_db(db):
    """Route the records routes' sessions-db dependency at the test DB."""
    app.dependency_overrides[get_sessions_db] = lambda: db


def _unoverride_sessions_db():
    """Drop the sessions-db dependency override."""
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
    """Persist one ready debrief report for the given session."""
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
    """The md export renders title, score, and bullet highlights."""
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
    """The json export wraps the full report payload with session meta."""
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
    """A session with no stored report exports nothing: 404."""
    _override_sessions_db(db)
    try:
        with export_client(_catalog(_snapshot())) as client:
            resp = client.get("/api/v1/records/export/report/1?format=md")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 404


def test_report_export_unfinished_session_is_400(db) -> None:
    """Exports require a completed (or ledger-frozen) session: 400."""
    snap = _snapshot(status="interviewing", ledger_frozen=False)
    _override_sessions_db(db)
    try:
        with export_client(_catalog(snap)) as client:
            resp = client.get("/api/v1/records/export/report/1?format=md")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 400


def test_report_export_pending_report_is_404(db) -> None:
    """A pending report row is not yet exportable: 404."""
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
    """A failed report generation surfaces as a conflict: 409."""
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
    """A wrong capability token is rejected: 403."""
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
    """An unknown session id exports nothing: 404."""
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
    """A frozen ledger with one visible and one hidden assistant turn."""
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
    """The md transcript labels speakers and drops invisible lines."""
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
    """The record export also requires a finished session: 400."""
    snap = _snapshot(status="interviewing", ledger_frozen=False)
    _override_sessions_db(db)
    try:
        with export_client(_catalog(snap, {"turns": []})) as client:
            resp = client.get("/api/v1/records/export/record/1?format=md")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 400


def test_record_export_json_projects_visible_turns(db) -> None:
    """The json record carries only the visible Q&A turns, like the md one."""
    _override_sessions_db(db)
    try:
        with export_client(_catalog(_snapshot(), _ledger())) as client:
            resp = client.get("/api/v1/records/export/record/1?format=json")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 200
    payload = json.loads(resp.json()["content"])
    assert len(payload["record"]["turns"]) == 2
    assert payload["record"]["turns"][0] == {
        "assistant": {"text": "Introduce yourself."},
        "user": {"text": "Hi, I am the candidate."},
    }
    # Invisible assistant text is internal state and must not leak into the
    # structured export either; the candidate reply still rides along.
    assert payload["record"]["turns"][1] == {"user": {"text": "Answer two."}}
    assert "hidden" not in resp.json()["content"]


@pytest.mark.parametrize("speaker", ["assistant", "user"])
@pytest.mark.parametrize(
    "text", [None, {}, {"internal": "notes"}, [], ["notes"], 0, 42, True, 1.5, "", " \n\t"]
)
def test_record_turn_json_omits_invalid_text(speaker, text) -> None:
    assert export_service._record_turn_json({speaker: {"text": text}}) == {}


@pytest.mark.parametrize("speaker", ["assistant", "user"])
def test_record_turn_json_preserves_valid_text(speaker) -> None:
    text = "  A valid question or reply.\n"
    assert export_service._record_turn_json({speaker: {"text": text}}) == {speaker: {"text": text}}


@pytest.mark.parametrize("include_visible_turns", [False, True])
def test_record_export_json_omits_empty_turns(db, include_visible_turns) -> None:
    turns = [
        {},
        {"assistant": {"text": "hidden", "visible": False}},
        {"assistant": {"text": " "}, "user": {"text": "\n"}},
        {"assistant": {"text": {"internal": "notes"}}, "user": {"text": ["notes"]}},
    ]
    expected = []
    if include_visible_turns:
        turns.insert(1, _ledger()["turns"][0])
        turns.append(_ledger()["turns"][1])
        turns.append({"assistant": {"text": "Next question."}, "user": {"text": 42}})
        expected = [
            {
                "assistant": {"text": "Introduce yourself."},
                "user": {"text": "Hi, I am the candidate."},
            },
            {"user": {"text": "Answer two."}},
            {"assistant": {"text": "Next question."}},
        ]
    _override_sessions_db(db)
    try:
        with export_client(_catalog(_snapshot(), {"turns": turns})) as client:
            resp = client.get("/api/v1/records/export/record/1?format=json")
    finally:
        _unoverride_sessions_db()
    assert resp.status_code == 200
    assert json.loads(resp.json()["content"])["record"]["turns"] == expected
