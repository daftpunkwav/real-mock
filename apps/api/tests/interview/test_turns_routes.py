"""Turns routes tests for src/realmock/domains/interview/routes/turns.py.

Covers: start/finish missing/bad-status/no-key/lifecycle-failure branches
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

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




    # No crash, warning path (278-279).




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


@pytest.mark.asyncio
async def test_turns_start_missing_and_bad_status() -> None:
    from realmock.domains.interview.routes import turns as mod

    with patch.object(mod, "raise_error", side_effect=RuntimeError("A2001")):
        try:
            await mod.start_interview(1, db=_turn_db(None), access="tok")
            assert False
        except RuntimeError:
            pass
    with patch.object(mod, "raise_error", side_effect=RuntimeError("A2002")):
        try:
            await mod.start_interview(
                1, db=_turn_db(_turn_session(status="completed")), access="tok"
            )
            assert False
        except RuntimeError:
            pass


@pytest.mark.asyncio
async def test_turns_start_missing_llm_key() -> None:
    from realmock.domains.interview.routes import turns as mod

    db = _turn_db(_turn_session(status="pending"))
    with (
        patch.object(mod, "assert_session_token", return_value=None),
        patch.object(mod, "session_llm", return_value=SimpleNamespace(api_key="")),
        patch.object(mod, "raise_error", side_effect=RuntimeError("A0006")),
    ):
        try:
            await mod.start_interview(1, db=db, access="tok")
            assert False
        except RuntimeError as e:
            assert "A0006" in str(e)


@pytest.mark.asyncio
async def test_turns_finish_missing_and_lifecycle_failure() -> None:
    from realmock.domains.interview.routes import turns as mod

    with patch.object(mod, "raise_error", side_effect=RuntimeError("A2001")):
        try:
            await mod.finish_interview(1, db=_turn_db(None), access="tok")
            assert False
        except RuntimeError:
            pass

    db = _turn_db(_turn_session(status="active"))
    with (
        patch.object(mod, "assert_session_token", return_value=None),
        patch.object(mod, "run_finish_lifecycle", side_effect=RuntimeError("freeze down")),
    ):
        try:
            await mod.finish_interview(1, db=db, access="tok")
            assert False
        except RuntimeError as e:
            assert "freeze down" in str(e)
