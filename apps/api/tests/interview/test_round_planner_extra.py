"""Round planner tests for src/realmock/domains/interview/agents/planning/round_planner.py.

Covers: first-session lookup, generate_round_plan_for_process no-process/no-session/no-key/timeout/invalid (existing test_round_planner.py kept)
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from realmock.domains.interview.agents.session_state import (
    InterviewSessionState,
)
from realmock.domains.interview.models import InterviewProcess, InterviewSession
from realmock.platform.core.ratelimit import reset_rate_limit
from tests.fakes import FakeLLMClient


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def _llm() -> MagicMock:
    m = MagicMock()
    m.api_key = ""
    return m


def _db_file(db) -> str:
    """The database file a session is bound to."""
    bind = db.get_bind()
    url = getattr(bind, "url", None)
    return str(getattr(url, "database", "") or "")


def _row(**overrides) -> InterviewSession:
    base = {
        "profile_id": 1,
        "role": "Backend",
        "level": "junior",
        "company": "acme",
        "workflow_type": "technical",
        "status": "pending",
        "current_phase": "identity_check",
        "agent_state": "{}",
        "messages": "[]",
    }
    base.update(overrides)
    return InterviewSession(**base)


def _state(db, **overrides) -> InterviewSessionState:
    row = _row(**overrides)
    db.add(row)
    db.commit()
    db.refresh(row)
    return InterviewSessionState(row, _llm())


# ---- _is_summary_phase ----


# ---- load / clamp ----


# ---- notes ----


# ---- pace ----


# ---- phase queries ----


# ---- progression ----


# ---- session_overrides ----


# ---- compaction thresholds ----


# ---- round plan schema extras ----


# ---- round planner background ----


def test_first_session_orders_by_round(db) -> None:
    from realmock.domains.interview.agents.planning import round_planner as rp

    proc = InterviewProcess(role="r", level="l", company="c", max_rounds=3)
    db.add(proc)
    db.commit()
    db.refresh(proc)
    assert rp._first_session(db, proc.id) is None


@pytest.mark.asyncio
async def test_generate_round_plan_no_process(monkeypatch) -> None:
    from realmock.domains.interview.agents.planning import round_planner as rp

    class _Ctx:
        def __enter__(self):
            return MagicMock(get=lambda *a, **k: None)

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(rp, "sessions_db_session", lambda: _Ctx())
    await rp.generate_round_plan_for_process(999999)  # never raises


@pytest.mark.asyncio
async def test_generate_round_plan_no_first_session_marks_failed(db, monkeypatch) -> None:
    from realmock.domains.interview.agents.planning import round_planner as rp
    from realmock.domains.interview.process.process_service import (
        create_process_with_first_round,
    )
    from realmock.domains.interview.schemas.process import ProcessCreateRequest

    proc, first = create_process_with_first_round(
        db, ProcessCreateRequest(role="r", level="l", company="c", max_rounds=2)
    )
    db.query(InterviewSession).filter(InterviewSession.process_id == proc.id).delete()
    db.commit()
    await rp.generate_round_plan_for_process(proc.id)
    db.expire_all()
    assert db.get(InterviewProcess, proc.id).round_plan_status == "failed"


@pytest.mark.asyncio
async def test_generate_round_plan_no_api_key_marks_failed(db, monkeypatch) -> None:
    from realmock.domains.interview.agents.planning import round_planner as rp
    from realmock.domains.interview.process.process_service import (
        create_process_with_first_round,
    )
    from realmock.domains.interview.schemas.process import ProcessCreateRequest

    proc, _ = create_process_with_first_round(
        db, ProcessCreateRequest(role="r", level="l", company="c", max_rounds=2)
    )
    llm = MagicMock()
    llm.api_key = ""
    monkeypatch.setattr(rp, "api_session_llm", lambda *a, **k: llm)
    await rp.generate_round_plan_for_process(proc.id)
    db.expire_all()
    assert db.get(InterviewProcess, proc.id).round_plan_status == "failed"


@pytest.mark.asyncio
async def test_generate_round_plan_timeout_marks_failed(db, monkeypatch) -> None:
    import asyncio as _asyncio

    from realmock.domains.interview.agents.planning import round_planner as rp
    from realmock.domains.interview.process.process_service import (
        create_process_with_first_round,
    )
    from realmock.domains.interview.schemas.process import ProcessCreateRequest

    proc, _ = create_process_with_first_round(
        db, ProcessCreateRequest(role="r", level="l", company="c", max_rounds=2)
    )
    llm = FakeLLMClient()
    monkeypatch.setattr(rp, "api_session_llm", lambda *a, **k: llm)

    async def _timeout(coro, *a, **k):
        try:
            coro.close()
        except Exception:
            pass
        raise _asyncio.TimeoutError()

    monkeypatch.setattr(rp.asyncio, "wait_for", _timeout)
    await rp.generate_round_plan_for_process(proc.id)
    db.expire_all()
    assert db.get(InterviewProcess, proc.id).round_plan_status == "failed"


@pytest.mark.asyncio
async def test_generate_round_plan_invalid_payload_marks_failed(db, monkeypatch) -> None:
    from realmock.domains.interview.agents.planning import round_planner as rp
    from realmock.domains.interview.process.process_service import (
        create_process_with_first_round,
    )
    from realmock.domains.interview.schemas.process import ProcessCreateRequest

    proc, _ = create_process_with_first_round(
        db, ProcessCreateRequest(role="r", level="l", company="c", max_rounds=2)
    )

    class _Bad(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3, **kw):
            return {"garbage": True}

    monkeypatch.setattr(rp, "api_session_llm", lambda *a, **k: _Bad())
    await rp.generate_round_plan_for_process(proc.id)
    db.expire_all()
    assert db.get(InterviewProcess, proc.id).round_plan_status == "failed"


@pytest.mark.asyncio
async def test_generate_round_plan_resolves_the_chat_model_from_the_api_database(
    db, monkeypatch
) -> None:
    """The chat configuration lives in the api database.

    The sessions database carries the process rows and none of the model
    configuration tables, so resolving the model through the sessions session
    raises "no such table: model_profiles" and the round program is never
    written.
    """
    from realmock.domains.interview.agents import session_overrides
    from realmock.domains.interview.agents.planning import round_planner as rp
    from realmock.domains.interview.process.process_service import (
        create_process_with_first_round,
    )
    from realmock.domains.interview.schemas.process import ProcessCreateRequest

    proc, _ = create_process_with_first_round(
        db, ProcessCreateRequest(role="r", level="l", company="c", max_rounds=2)
    )
    resolved: list[str] = []

    def _record(db_, session):
        resolved.append(_db_file(db_))
        return SimpleNamespace(api_key="")

    monkeypatch.setattr(session_overrides, "session_llm", _record)
    await rp.generate_round_plan_for_process(proc.id)
    assert resolved and resolved[0].endswith("api.db"), resolved
