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


def test_timeout_fails_fast_without_auto_retry():
    """Live interview policy: a hung tool is cut once, never auto-retried."""
    calls = {"n": 0}

    async def hang() -> str:
        calls["n"] += 1
        await asyncio.sleep(60)

    guard = ToolGuard(state_fn=lambda: {}, timeout_sec=0.05)
    with pytest.raises(ToolGuardError, match="timed out"):
        asyncio.run(guard.run("lookup_company_profile", {}, hang))
    assert calls["n"] == 1


def test_per_call_timeout_override_extends_budget():
    calls = {"n": 0}

    async def slow() -> str:
        calls["n"] += 1
        await asyncio.sleep(0.12)
        return "recovered"

    guard = ToolGuard(state_fn=lambda: {}, timeout_sec=0.05)
    # Default budget cuts it; the model-requested override lets it finish.
    with pytest.raises(ToolGuardError):
        asyncio.run(guard.run("web_fetch", {}, slow))
    assert asyncio.run(guard.run("web_fetch", {}, slow, timeout_sec=2.0)) == "recovered"
    # Overrides clamp to a sane floor.
    assert asyncio.run(guard.run("web_fetch", {}, slow, timeout_sec=0.0)) == "recovered"


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
            asyncio.run(guard.run("web_search", {}, boom))
    assert calls["n"] == 3  # exceptions never retry
    # 4th call refused without executing.
    with pytest.raises(ToolGuardError, match="blocked for a while"):
        asyncio.run(guard.run("web_search", {}, boom))
    assert calls["n"] == 3
    # TTL expiry allows a half-open trial.
    state[GUARD_STATE_KEY]["web_search"]["opened_at"] = time.time() - 601.0
    with pytest.raises(ToolGuardError):
        asyncio.run(guard.run("web_search", {}, boom))
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


def test_concurrent_failures_count_every_increment():
    """Parallel failures must not overwrite each other's streak increment."""
    state: dict = {}

    async def run_parallel() -> None:
        guard = ToolGuard(state_fn=lambda: state, timeout_sec=5.0, circuit_streak=10)

        async def boom() -> str:
            raise RuntimeError("dead endpoint")

        await asyncio.gather(
            *(guard.run("web_search", {}, boom) for _ in range(3)),
            return_exceptions=True,
        )

    asyncio.run(run_parallel())
    assert state[GUARD_STATE_KEY]["web_search"]["streak"] == 3


def test_circuit_open_refusal_carries_error_kind():
    """A circuit-open refusal is classified apart from a real tool failure."""
    state: dict = {GUARD_STATE_KEY: {"t": {"streak": 3, "opened_at": time.time()}}}
    guard = ToolGuard(state_fn=lambda: state, timeout_sec=5.0, circuit_streak=3)
    with pytest.raises(ToolGuardError) as err:
        asyncio.run(guard.run("t", {}, _ok()))
    assert err.value.error_kind == "circuit_open"
    # The guard does not log this path; the loop records it exactly once.
    assert err.value.already_logged is False


def test_probe_failure_after_ttl_does_not_reopen():
    """TTL expiry resets the streak IN THE SHARED BOX: a probe failure counts
    as failure #1 and must NOT re-trip the breaker."""
    state: dict = {}
    guard = ToolGuard(
        state_fn=lambda: state, timeout_sec=0.05, circuit_streak=2, circuit_ttl_sec=600.0
    )

    async def boom() -> str:
        raise RuntimeError("dead endpoint")

    for _ in range(2):
        with pytest.raises(ToolGuardError):
            asyncio.run(guard.run("t", {}, boom))
    assert state[GUARD_STATE_KEY]["t"]["streak"] == 2
    # TTL expiry allows a probe; the reset must be visible in the shared box.
    state[GUARD_STATE_KEY]["t"]["opened_at"] = time.time() - 601.0
    with pytest.raises(ToolGuardError):
        asyncio.run(guard.run("t", {}, boom))
    entry = state[GUARD_STATE_KEY]["t"]
    assert entry["streak"] == 1
    assert entry["opened_at"] is None  # breaker stays CLOSED
    # A second consecutive failure trips it again.
    with pytest.raises(ToolGuardError, match="blocked for a while"):
        asyncio.run(guard.run("t", {}, boom))
    assert state[GUARD_STATE_KEY]["t"]["streak"] == 2


def test_streak_never_exceeds_threshold_across_windows():
    """The persisted reset keeps the streak bounded: repeated
    open -> TTL expiry -> probe failure -> failure cycles can no longer
    accumulate an unbounded streak (and the refusal message stays truthful)."""
    state: dict = {}

    async def boom() -> str:
        raise RuntimeError("dead endpoint")

    guard = ToolGuard(
        state_fn=lambda: state, timeout_sec=0.05, circuit_streak=2, circuit_ttl_sec=600.0
    )
    for _ in range(10):
        with pytest.raises(ToolGuardError):
            asyncio.run(guard.run("t", {}, boom))
        with pytest.raises(ToolGuardError):
            asyncio.run(guard.run("t", {}, boom))
        assert state[GUARD_STATE_KEY]["t"]["streak"] <= 2
        state[GUARD_STATE_KEY]["t"]["opened_at"] = time.time() - 601.0
        with pytest.raises(ToolGuardError):
            asyncio.run(guard.run("t", {}, boom))
        assert state[GUARD_STATE_KEY]["t"]["streak"] <= 2


def test_probe_success_after_ttl_closes_breaker():
    """A successful probe still clears the tool entry entirely."""
    state: dict = {}
    guard = ToolGuard(
        state_fn=lambda: state, timeout_sec=0.05, circuit_streak=2, circuit_ttl_sec=600.0
    )

    async def boom() -> str:
        raise RuntimeError("dead endpoint")

    for _ in range(2):
        with pytest.raises(ToolGuardError):
            asyncio.run(guard.run("t", {}, boom))
    state[GUARD_STATE_KEY]["t"]["opened_at"] = time.time() - 601.0
    assert asyncio.run(guard.run("t", {}, _ok())) == "obs"
    assert "t" not in state[GUARD_STATE_KEY]
