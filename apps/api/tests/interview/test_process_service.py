"""Process service tests for src/realmock/domains/interview/process/process_service.py.

Covers: get_process_detail not-found, record_round_finished missing/exception paths
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

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


def test_record_round_finished_missing_process() -> None:
    from realmock.domains.interview.process import process_service as mod

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    session = SimpleNamespace(id=1, process_id=999, round_no=1, result="passed")
    mod.record_round_finished(db, session)  # type: ignore[arg-type]
    # No crash, warning path (278-279).


def test_record_round_finished_exception_rolls_back() -> None:
    from realmock.domains.interview.process import process_service as mod

    db = MagicMock()
    db.query.side_effect = RuntimeError("db down")
    db.rollback = MagicMock()
    session = SimpleNamespace(id=2, process_id=1, round_no=1, result="passed")
    mod.record_round_finished(db, session)  # type: ignore[arg-type]
    db.rollback.assert_called()


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






