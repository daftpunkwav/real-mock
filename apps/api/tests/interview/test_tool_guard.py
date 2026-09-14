"""Interview tool guard: timeout/retry, breaker open/half-open, error contract."""

from __future__ import annotations

import asyncio
import time

import pytest

from realmock.domains.interview.agents.tool_guard import (
    GUARD_STATE_KEY,
    ToolGuard,
    ToolGuardError,
)
from realmock.domains.interview.ledger.constants import is_tool_failure_result
from realmock.platform.core.errors import ApiBusinessError, CATALOG


def _ok(result: str = "obs") -> object:
    async def call() -> str:
        return result

    return call


def _hang() -> object:
    async def call() -> str:
        await asyncio.sleep(60)
        return "never"

    return call


def test_success_returns_observation_without_streak():
    state: dict = {}
    guard = ToolGuard(state_fn=lambda: state, timeout_sec=5.0)
    assert asyncio.run(guard.run("github_get_user", {}, _ok())) == "obs"
    assert GUARD_STATE_KEY not in state


def test_timeout_retries_once_then_succeeds():
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            await asyncio.sleep(60)
        return "recovered"

    guard = ToolGuard(state_fn=lambda: {}, timeout_sec=0.05)
    assert asyncio.run(guard.run("lookup_company_profile", {}, flaky)) == "recovered"
    assert calls["n"] == 2


def test_timeout_exhausted_raises_with_guidance_and_streak():
    state: dict = {}
    guard = ToolGuard(state_fn=lambda: state, timeout_sec=0.05)
    with pytest.raises(ToolGuardError, match="timed out"):
        asyncio.run(guard.run("github_get_readme", {}, _hang()))
    assert is_tool_failure_result("Tool execution failed: timed out")
    assert state[GUARD_STATE_KEY]["github_get_readme"]["streak"] == 1


def test_breaker_opens_after_streak_and_half_opens_on_ttl():
    state: dict = {}
    guard = ToolGuard(
        state_fn=lambda: state, timeout_sec=0.05, circuit_streak=3, circuit_ttl_sec=600.0
    )
    calls = {"n": 0}

    async def boom() -> str:
        calls["n"] += 1
        raise RuntimeError("dead endpoint")

    for _ in range(3):
        with pytest.raises(ToolGuardError):
            asyncio.run(guard.run("web_search_interview_exp", {}, boom))
    assert calls["n"] == 3  # exceptions never retry
    # 4th call refused without executing.
    with pytest.raises(ToolGuardError, match="blocked for a while"):
        asyncio.run(guard.run("web_search_interview_exp", {}, boom))
    assert calls["n"] == 3
    # TTL expiry allows a half-open trial.
    state[GUARD_STATE_KEY]["web_search_interview_exp"]["opened_at"] = time.time() - 601.0
    with pytest.raises(ToolGuardError):
        asyncio.run(guard.run("web_search_interview_exp", {}, boom))
    assert calls["n"] == 4


def test_success_closes_breaker_streak():
    state: dict = {GUARD_STATE_KEY: {"github_list_repos": {"streak": 2, "opened_at": None}}}
    guard = ToolGuard(state_fn=lambda: state, timeout_sec=5.0)
    assert asyncio.run(guard.run("github_list_repos", {}, _ok())) == "obs"
    assert "github_list_repos" not in state[GUARD_STATE_KEY]


def test_business_error_propagates_without_streak():
    async def biz() -> str:
        raise ApiBusinessError(CATALOG["C0001"], message="quota exhausted")

    state: dict = {}
    guard = ToolGuard(state_fn=lambda: state, timeout_sec=5.0)
    with pytest.raises(ApiBusinessError):
        asyncio.run(guard.run("github_get_user", {}, biz))
    assert GUARD_STATE_KEY not in state


def test_local_box_when_no_state_wired():
    guard = ToolGuard(timeout_sec=0.05)
    with pytest.raises(ToolGuardError):
        asyncio.run(guard.run("t", {}, _hang()))
    # Breaker still works instance-locally.
    guard2 = ToolGuard(timeout_sec=5.0)
    assert asyncio.run(guard2.run("t", {}, _ok())) == "obs"
