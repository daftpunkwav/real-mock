"""Report live-stream tests for realmock.domains.records.routes.report.

Covers: _generate_with_live_events drain and get_report_stream cancel/failure paths
Conventions: run_debrief_for_session and sessions DB faked; temp DB for store; rate limits reset per test
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from realmock.domains.records.schemas.report import DebriefReport
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


@pytest.fixture(autouse=True)
def _records_table(engine):
    import realmock.domains.records.models.report  # noqa: F401
    from realmock.platform.database import SessionsBase

    SessionsBase.metadata.create_all(bind=engine)
    yield


def _report_dict(score=80) -> dict:
    return {
        "overall_score": score,
        "score_breakdown": {"technical": score, "overall": score},
        "strengths": ["ok"],
        "weaknesses": ["x"],
        "improvement_suggestions": ["y"],
        "turn_notes": [],
    }


def _snap(**overrides):
    from realmock.platform.contracts.session_catalog import SessionSnapshot

    base = {
        "id": 1,
        "role": "Backend",
        "level": "Senior",
        "company": "bytedance",
        "status": "completed",
        "messages": "[]",
        "ledger_frozen": True,
    }
    base.update(overrides)
    return SessionSnapshot.model_validate(base)


@pytest.mark.asyncio
async def test_generate_drains_second_while() -> None:
    import realmock.domains.records.routes.report as rmod
    from realmock.domains.records.services import report_events
    from tests.fakes import FakeLLMClient

    sid = 777002
    fake = DebriefReport.model_validate(_report_dict(75))
    orig_sub = report_events.subscribe

    def _fake_sub(sid_arg):
        q = orig_sub(sid_arg)
        q.put_nowait({"type": "stage", "stage": "first"})
        q.put_nowait({"type": "stage", "stage": "second"})
        return q

    async def _fake_run(*a, **k):
        return fake

    with (
        patch.object(report_events, "subscribe", side_effect=_fake_sub),
        patch.object(rmod, "run_debrief_for_session", side_effect=_fake_run),
    ):
        out: list = []
        lines = []
        async for line in rmod._generate_with_live_events(
            sid, snap=_snap(id=sid), llm=FakeLLMClient(), report_out=out
        ):
            lines.append(line)
        assert out and out[0].overall_score == 75
        assert any("second" in line or "first" in line for line in lines)


@pytest.mark.asyncio
async def test_report_stream_cancel_keeps_generating(db) -> None:
    import realmock.domains.records.routes.report as rmod
    from realmock.domains.records.services import report_store as store
    from realmock.platform.capabilities.ai.llm.client import LLMClient
    from tests.fakes import FakeLLMClient

    sid_seed = 888002
    # Seed a generating row visible to sessions_db_session (same temp DB file).
    store.upsert_pending(db, sid_seed)
    row = store.get_report_row(db, sid_seed)
    assert row is not None
    row.status = store.STATUS_GENERATING
    from contextlib import contextmanager
    from datetime import datetime
    from datetime import timezone as _tz

    row.updated_at = datetime.now(_tz.utc)
    db.commit()
    db.expire_all()

    async def _cancel(*a, **k):
        raise asyncio.CancelledError()

    @contextmanager
    def _same_session():
        yield db

    with (
        patch.object(rmod, "run_debrief_for_session", side_effect=_cancel),
        patch.object(LLMClient, "from_db", classmethod(lambda cls, db: FakeLLMClient())),
        patch.object(rmod, "_require_finished_session", return_value=_snap(id=sid_seed)),
        patch("realmock.platform.database.sessions_db_session", side_effect=_same_session),
    ):
        resp = await rmod.get_report_stream(sid_seed, db=db, api_db=MagicMock(), access="t")
        with pytest.raises(asyncio.CancelledError):
            async for _ in resp.body_iterator:
                pass
    # Client disconnect must not fail the report: the background debrief keeps
    # running and the next GET/stream polls it up (regression: old code marked
    # failed here, turning transient disconnects into permanent A2005).
    assert store.get_report_row(db, sid_seed).status == store.STATUS_GENERATING  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_debrief_failure_after_disconnect_is_observed(caplog) -> None:
    """A debrief that fails AFTER the client disconnected must be logged once
    by the orphan-task observer instead of surfacing later as GC
    "exception was never retrieved" noise."""
    import logging as _logging

    import realmock.domains.records.routes.report as rmod
    from tests.fakes import FakeLLMClient

    sid = 777004
    started = asyncio.Event()

    async def _late_failure(*a, **k):
        started.set()
        await asyncio.sleep(0.05)
        raise RuntimeError("llm exploded after disconnect")

    with patch.object(rmod, "run_debrief_for_session", side_effect=_late_failure):
        out: list = []
        gen = rmod._generate_with_live_events(
            sid, snap=_snap(id=sid), llm=FakeLLMClient(), report_out=out
        )
        first = asyncio.ensure_future(gen.__anext__())
        await started.wait()
        # Client disconnect cancels the streaming generator mid-relay.
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        # The debrief task keeps running by design; wait for it to fail and
        # for the done callback to log the failure.
        with caplog.at_level(_logging.ERROR, logger=rmod.__name__):
            await asyncio.sleep(0.2)
        assert not out
        assert any("failed after SSE disconnect" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_report_stream_cancel_inner_failure_covered(db) -> None:
    import realmock.domains.records.routes.report as rmod
    from realmock.domains.records.services import report_store as store
    from realmock.platform.capabilities.ai.llm.client import LLMClient
    from tests.fakes import FakeLLMClient

    sid_seed = 888003
    store.upsert_pending(db, sid_seed)
    db.commit()

    async def _cancel(*a, **k):
        raise asyncio.CancelledError()

    def _boom_session():
        raise RuntimeError("sessions db down")

    with (
        patch.object(rmod, "run_debrief_for_session", side_effect=_cancel),
        patch.object(LLMClient, "from_db", classmethod(lambda cls, db: FakeLLMClient())),
        patch.object(rmod, "_require_finished_session", return_value=_snap(id=sid_seed)),
        patch("realmock.platform.database.sessions_db_session", side_effect=_boom_session),
    ):
        resp = await rmod.get_report_stream(sid_seed, db=db, api_db=MagicMock(), access="t")
        with pytest.raises(asyncio.CancelledError):
            async for _ in resp.body_iterator:
                pass
