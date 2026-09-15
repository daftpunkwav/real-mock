"""History compaction thresholds tests for src/realmock/domains/interview/agents/history_compaction.py.

Covers: adaptive_fold_thresholds bands, maybe_fold_history skip/failure/no-shrink (existing test_history_compaction.py kept)
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realmock.domains.interview.agents.history_compaction import (
    adaptive_fold_thresholds,
    maybe_fold_history,
)
from realmock.domains.interview.agents.session_state import (
    InterviewSessionState,
)
from realmock.domains.interview.models import InterviewSession
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def _llm() -> MagicMock:
    m = MagicMock()
    m.api_key = ""
    return m


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


def test_adaptive_fold_thresholds_bands() -> None:
    assert adaptive_fold_thresholds(8000) == (0.25, 0.40)
    assert adaptive_fold_thresholds(128000) == (0.40, 0.60)
    assert adaptive_fold_thresholds(32000) == (0.30, 0.50)
    assert adaptive_fold_thresholds("bad") == (0.30, 0.50)
    assert adaptive_fold_thresholds(None) == (0.30, 0.50)


@pytest.mark.asyncio
async def test_maybe_fold_unparsable_window_skips() -> None:
    agent = SimpleNamespace(messages=[{"role": "user", "content": "hi"}], agent_state={})
    assert await maybe_fold_history(agent, llm=MagicMock(), context_window="bad") is False


@pytest.mark.asyncio
async def test_maybe_fold_short_history_skips() -> None:
    agent = SimpleNamespace(messages=[{"role": "user", "content": "hi"}], agent_state={})
    assert await maybe_fold_history(agent, llm=MagicMock(), context_window=1000) is False


@pytest.mark.asyncio
async def test_maybe_fold_estimate_failure_skips() -> None:
    msgs = [{"role": "user", "content": "x" * 500} for _ in range(30)]
    agent = SimpleNamespace(messages=msgs, agent_state={})
    with patch(
        "realmock.domains.interview.agents.history_compaction.estimate_messages_tokens",
        side_effect=RuntimeError("est down"),
    ):
        assert await maybe_fold_history(agent, llm=MagicMock(), context_window=100) is False


@pytest.mark.asyncio
async def test_maybe_fold_compact_failure_keeps_messages() -> None:
    msgs = [{"role": "user", "content": "x" * 500} for _ in range(30)]
    agent = SimpleNamespace(messages=list(msgs), agent_state={})
    with (
        patch(
            "realmock.domains.interview.agents.history_compaction.estimate_messages_tokens",
            return_value=10**6,
        ),
        patch(
            "realmock.domains.interview.agents.history_compaction.compact_with_summary",
            side_effect=RuntimeError("llm down"),
        ),
    ):
        assert await maybe_fold_history(agent, llm=MagicMock(), context_window=1000) is False
        assert agent.messages == msgs


@pytest.mark.asyncio
async def test_maybe_fold_no_shrink_returns_false() -> None:
    msgs = [{"role": "user", "content": "x" * 500} for _ in range(30)]
    agent = SimpleNamespace(messages=list(msgs), agent_state={})
    with (
        patch(
            "realmock.domains.interview.agents.history_compaction.estimate_messages_tokens",
            return_value=10**6,
        ),
        patch(
            "realmock.domains.interview.agents.history_compaction.compact_with_summary",
            new=AsyncMock(return_value=list(msgs)),
        ),
    ):
        assert await maybe_fold_history(agent, llm=MagicMock(), context_window=1000) is False


# ---- round plan schema extras ----








# ---- round planner background ----












