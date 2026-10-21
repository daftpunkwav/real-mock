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
    """A missing session is A2001 and a finished one is A2002.

    The route's own ``raise_error`` runs here: the catalog code is part of the
    API contract the client dispatches on, so the assertion pins the code
    instead of merely observing that the route refused the call.
    """
    from realmock.domains.interview.routes import turns as mod
    from realmock.platform.core.errors import ApiBusinessError

    with pytest.raises(ApiBusinessError) as exc:
        await mod.start_interview(1, db=_turn_db(None), access="tok")
    assert exc.value.error_code == "A2001"

    with pytest.raises(ApiBusinessError) as exc2:
        await mod.start_interview(1, db=_turn_db(_turn_session(status="completed")), access="tok")
    assert exc2.value.error_code == "A2002"


@pytest.mark.asyncio
async def test_turns_start_missing_llm_key() -> None:
    from realmock.domains.interview.routes import turns as mod
    from realmock.platform.core.errors import ApiBusinessError

    db = _turn_db(_turn_session(status="pending"))
    with (
        patch.object(mod, "assert_session_token", return_value=None),
        patch.object(mod, "session_llm", return_value=SimpleNamespace(api_key="")),
    ):
        with pytest.raises(ApiBusinessError) as exc:
            await mod.start_interview(1, db=db, access="tok")
    assert exc.value.error_code == "A0006"


@pytest.mark.asyncio
async def test_turns_finish_missing_and_lifecycle_failure() -> None:
    from realmock.domains.interview.routes import turns as mod
    from realmock.platform.core.errors import ApiBusinessError

    with pytest.raises(ApiBusinessError) as exc:
        await mod.finish_interview(1, db=_turn_db(None), access="tok")
    assert exc.value.error_code == "A2001"

    db = _turn_db(_turn_session(status="active"))
    with (
        patch.object(mod, "assert_session_token", return_value=None),
        patch.object(mod, "run_finish_lifecycle", side_effect=RuntimeError("freeze down")),
    ):
        with pytest.raises(RuntimeError) as exc2:
            await mod.finish_interview(1, db=db, access="tok")
    assert "freeze down" in str(exc2.value)
