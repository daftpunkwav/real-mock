"""Ingest tests for realmock.domains.records.services.ingest.

Covers: _coerce_ended_at branches, handle_interview_finished skip/run/swallow and lifecycle-hook wiring
Conventions: sessions_db_session and runner faked; no real DB; rate limits reset per test
"""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from realmock.platform.core.ratelimit import reset_rate_limit

@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()

@pytest.mark.asyncio
async def test_coerce_ended_at_branches() -> None:
    from realmock.domains.records.services.ingest import _coerce_ended_at

    assert _coerce_ended_at(None) is None
    now = datetime.now()
    assert _coerce_ended_at(now) is now
    assert _coerce_ended_at("2024-01-02T03:04:05Z") is not None
    assert _coerce_ended_at("not-a-date") is None

@pytest.mark.asyncio
async def test_ingest_skips_ready_and_generating(monkeypatch) -> None:
    import realmock.domains.records.services.ingest as ingest_mod
    from realmock.platform.contracts.interview_finished import InterviewFinishedPayload

    for status in ("ready", "generating"):
        from contextlib import contextmanager

        @contextmanager
        def _fake_session():
            db = MagicMock()
            yield db

        monkeypatch.setattr(ingest_mod, "sessions_db_session", _fake_session)
        monkeypatch.setattr(ingest_mod, "upsert_pending", lambda db, sid: MagicMock(status=status))
        run = AsyncMock()
        monkeypatch.setattr(ingest_mod, "run_debrief_for_session", run)
        payload = InterviewFinishedPayload(session_id=1, ledger={})
        await ingest_mod.handle_interview_finished(payload)
        assert run.await_count == 0

@pytest.mark.asyncio
async def test_ingest_runs_and_swallows_errors(monkeypatch) -> None:
    import realmock.domains.records.services.ingest as ingest_mod
    from realmock.platform.contracts.interview_finished import InterviewFinishedPayload
    from contextlib import contextmanager

    @contextmanager
    def _fake_session():
        yield MagicMock()

    monkeypatch.setattr(ingest_mod, "sessions_db_session", _fake_session)
    monkeypatch.setattr(ingest_mod, "upsert_pending", lambda db, sid: MagicMock(status="pending"))
    monkeypatch.setattr(ingest_mod, "run_debrief_for_session", AsyncMock(return_value=None))
    payload = InterviewFinishedPayload(session_id=7, ledger={"a": 1}, ended_at="2024-01-01T00:00:00Z")
    await ingest_mod.handle_interview_finished(payload)

    # Failure inside runner must not raise.
    monkeypatch.setattr(
        ingest_mod, "run_debrief_for_session", AsyncMock(side_effect=RuntimeError("boom"))
    )
    await ingest_mod.handle_interview_finished(payload)

def test_register_handlers_wires_hook() -> None:
    import realmock.domains.records.services.ingest as ingest_mod

    ingest_mod.register_records_lifecycle_handlers()
    from realmock.platform.contracts import lifecycle_hooks as hooks

    assert hooks._on_interview_finished is ingest_mod.handle_interview_finished
