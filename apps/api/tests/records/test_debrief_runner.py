"""Debrief runner tests for src/realmock/domains/records/services/debrief_runner.py.

Covers: try_claim_generation, summary digest caps, run_debrief ready/generating/success/projection/agent-failure
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realmock.domains.interview.models import InterviewSession
from realmock.domains.records.schemas.report import DebriefReport
from realmock.domains.records.services import debrief_runner as drmod
from realmock.domains.records.services import report_events, report_store as store
from realmock.platform.contracts.session_catalog import SessionSnapshot
from realmock.platform.core.ratelimit import reset_rate_limit
from tests.fakes import FakeLLMClient


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()
    for key in list(report_events._subscribers.keys()):
        for queue in list(report_events._subscribers.get(key, ())):
            report_events.unsubscribe(int(key.split(":")[1]), queue)


def _report_dict(score=80) -> dict:
    return {
        "overall_score": score,
        "score_breakdown": {"technical": score, "overall": score},
        "strengths": ["ok"],
        "weaknesses": ["x"],
        "improvement_suggestions": ["y"],
        "turn_notes": [],
    }


def _completed_session(db, token="cov-rep2-token-abc123") -> int:
    ledger = {
        "schema": "realmock.ledger.v1",
        "session_id": 0,
        "frozen": True,
        "turns": [
            {
                "turn_id": "t-0001",
                "phase": "intro",
                "assistant": {"text": "hi", "visible": True},
                "tools": [],
                "user": {"text": "hello", "source": "text"},
                "flags": {},
            }
        ],
    }
    row = InterviewSession(
        profile_id=1,
        role="Backend",
        level="Senior",
        company="bytedance",
        workflow_type="technical",
        status="completed",
        current_phase="summary",
        access_token=token,
        messages=json.dumps([{"role": "user", "content": "a"}]),
        ledger=json.dumps(ledger),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


def _snap_dict(**overrides) -> dict:
    base = SessionSnapshot.model_validate(
        {
            "id": 1,
            "role": "Backend",
            "level": "Senior",
            "company": "bytedance",
            "status": "completed",
            "messages": "[]",
            "report": "{}",
            "ledger_frozen": True,
        }
    ).model_dump(mode="json")
    base.update(overrides)
    return base


# ---- legacy fallback ----














# ---- debrief runner ----


def test_try_claim_generation_reclaims_stale(db) -> None:
    row = store.upsert_pending(db, 501)
    row.status = store.STATUS_GENERATING
    row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    db.commit()
    # Stale generating is reclaimed to pending, then claimed -> True.
    assert drmod.try_claim_generation(db, 501) is True


def test_try_claim_generation_pending_ok(db) -> None:
    store.upsert_pending(db, 502)
    assert drmod.try_claim_generation(db, 502) is True


def test_try_claim_generation_exception_returns_false() -> None:
    db = MagicMock()
    db.execute.side_effect = RuntimeError("db down")
    assert drmod.try_claim_generation(db, 503) is False


def test_build_summary_digest_caps_turns() -> None:
    report = DebriefReport.model_validate(
        {
            **_report_dict(80),
            "turn_notes": [
                {
                    "turn_id": f"t-{i:04d}",
                    "answer_summary": f"ans{i}",
                    "user_review": {"summary": f"sum{i}"},
                }
                for i in range(25)
            ],
        }
    )
    payload = drmod._build_summary(9, report, profile_id=2, company="c", role="r")
    assert payload.session_id == 9
    assert len(payload.turn_note_digest) == 20
    assert payload.turn_note_digest[0].startswith("t-0000:")


@contextmanager
def _session_ctx(db):
    yield db


@pytest.mark.asyncio
async def test_run_debrief_no_row_returns_none(db) -> None:
    # No report row -> None without touching the agent.
    with patch(
        "realmock.domains.records.services.debrief_runner.sessions_db_session",
        side_effect=lambda: _session_ctx(db),
    ):
        out = await drmod.run_debrief_for_session(None, None, 999991, ledger={})
        assert out is None


@pytest.mark.asyncio
async def test_run_debrief_ready_returns_parsed(db) -> None:
    store.persist_ready(db, 511, DebriefReport.model_validate(_report_dict(81)))
    with patch(
        "realmock.domains.records.services.debrief_runner.sessions_db_session",
        side_effect=lambda: _session_ctx(db),
    ):
        out = await drmod.run_debrief_for_session(None, None, 511)
    assert out is not None and out.overall_score == 81


@pytest.mark.asyncio
async def test_run_debrief_generating_fresh_returns_none(db) -> None:
    row = store.upsert_pending(db, 512)
    row.status = store.STATUS_GENERATING
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    with patch(
        "realmock.domains.records.services.debrief_runner.sessions_db_session",
        side_effect=lambda: _session_ctx(db),
    ):
        assert await drmod.run_debrief_for_session(None, None, 512) is None


@pytest.mark.asyncio
async def test_run_debrief_success_persists_and_notifies(db) -> None:
    store.upsert_pending(db, 513)
    fake = DebriefReport.model_validate(_report_dict(77))
    snap = _snap_dict(id=513, ledger={"frozen": True}, process_id=None)

    catalog = MagicMock()
    catalog.get_session_snapshot.return_value = snap
    catalog.get_process_context.return_value = ""

    agent = MagicMock()
    agent.run = AsyncMock(return_value=fake)

    with (
        patch(
            "realmock.domains.records.services.debrief_runner.sessions_db_session",
            side_effect=lambda: _session_ctx(db),
        ),
        patch(
            "realmock.domains.records.services.debrief_runner.get_session_catalog",
            return_value=catalog,
        ),
        patch(
            "realmock.domains.records.services.debrief_runner.DeepReportAgent",
            return_value=agent,
        ),
        patch(
            "realmock.domains.records.services.debrief_runner.notify_report_summary",
            new=AsyncMock(),
        ) as notified,
        patch(
            "realmock.domains.records.services.debrief_runner.apply_session_overall_score",
        ) as applied,
    ):
        out = await drmod.run_debrief_for_session(None, None, 513, llm=FakeLLMClient(), ledger=None)
    assert out is not None and out.overall_score == 77
    notified.assert_awaited_once()
    applied.assert_called_once()
    assert store.get_report_row(db, 513).status == store.STATUS_READY


@pytest.mark.asyncio
async def test_run_debrief_score_projection_failure_still_ready(db) -> None:
    store.upsert_pending(db, 514)
    fake = DebriefReport.model_validate(_report_dict(76))
    catalog = MagicMock()
    catalog.get_session_snapshot.return_value = _snap_dict(id=514, process_id=None)
    catalog.get_process_context.return_value = ""
    agent = MagicMock()
    agent.run = AsyncMock(return_value=fake)
    with (
        patch(
            "realmock.domains.records.services.debrief_runner.sessions_db_session",
            side_effect=lambda: _session_ctx(db),
        ),
        patch(
            "realmock.domains.records.services.debrief_runner.get_session_catalog",
            return_value=catalog,
        ),
        patch(
            "realmock.domains.records.services.debrief_runner.DeepReportAgent",
            return_value=agent,
        ),
        patch(
            "realmock.domains.records.services.debrief_runner.notify_report_summary",
            new=AsyncMock(),
        ),
        patch(
            "realmock.domains.records.services.debrief_runner.apply_session_overall_score",
            side_effect=RuntimeError("projection down"),
        ),
    ):
        out = await drmod.run_debrief_for_session(None, None, 514, llm=FakeLLMClient())
    assert out is not None
    assert store.get_report_row(db, 514).status == store.STATUS_READY


@pytest.mark.asyncio
async def test_run_debrief_agent_failure_marks_failed(db) -> None:
    store.upsert_pending(db, 515)
    catalog = MagicMock()
    catalog.get_session_snapshot.return_value = None
    agent = MagicMock()
    agent.run = AsyncMock(side_effect=RuntimeError("agent down"))
    with (
        patch(
            "realmock.domains.records.services.debrief_runner.sessions_db_session",
            side_effect=lambda: _session_ctx(db),
        ),
        patch(
            "realmock.domains.records.services.debrief_runner.get_session_catalog",
            return_value=catalog,
        ),
        patch(
            "realmock.domains.records.services.debrief_runner.DeepReportAgent",
            return_value=agent,
        ),
    ):
        out = await drmod.run_debrief_for_session(None, None, 515, llm=FakeLLMClient())
    assert out is None
    assert store.get_report_row(db, 515).status == store.STATUS_FAILED


# ---- history routes ----








