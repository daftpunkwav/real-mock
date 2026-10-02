"""Process service tests for src/realmock/domains/interview/process/process_service.py.

Covers: get_process_detail not-found, record_round_finished missing/exception paths
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


# ---- plan_prompts (61, 68, 78-89, 96) ----




# ---- process_service (165, 278-279, 308-310) ----


def test_process_detail_not_found(db) -> None:
    from realmock.domains.interview.process import process_service as mod

    with pytest.raises(mod.ProcessRoundError) as exc:
        mod.get_process_detail(db, 999999)
    assert exc.value.code == "A2001"


def test_record_round_finished_missing_process(db, caplog) -> None:
    from realmock.domains.interview.process import process_service as mod

    session = SimpleNamespace(id=1, process_id=999999, round_no=1, result="passed")
    with caplog.at_level(logging.WARNING):
        mod.record_round_finished(db, session)  # type: ignore[arg-type]
    assert any(
        "record_round_finished: process missing" in r.message for r in caplog.records
    )


def test_record_round_finished_exception_rolls_back(db, caplog) -> None:
    from realmock.domains.interview.models import InterviewProcess
    from realmock.domains.interview.process import process_service as mod

    proc = InterviewProcess(role="fe", level="mid", company="acme")
    db.add(proc)
    db.commit()
    original_memory = proc.memory
    session = SimpleNamespace(id=1, process_id=proc.id, round_no=1, result="passed")

    def _boom(*args, **kwargs):
        proc.memory = "dirty"
        raise RuntimeError("db down")

    with (
        patch.object(mod, "append_round", side_effect=_boom),
        caplog.at_level(logging.ERROR),
    ):
        mod.record_round_finished(db, session)  # type: ignore[arg-type]

    assert any(
        "record_round_finished failed" in r.message for r in caplog.records
    )
    # The failed unit of work must leave no residue: without the rollback the
    # pending dirty write would be flushed by the next commit on this session.
    db.commit()
    db.expire_all()
    assert db.get(InterviewProcess, proc.id).memory == original_memory


# ---- turns (115, 118, 122, 155, 166-168) ----


def _turn_session(**kw):
    base = {
        "id": 1,
        "status": "pending",
        "current_phase": "tech",
        "access_token": "tok",
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _turn_db(session_row=None):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = session_row
    return db
