"""ToolRunGuard unit tests: shared budget + same-args circuit breaker policy."""

from __future__ import annotations

from realmock.platform.capabilities.ai.agent.tools.executor import ToolRunGuard


def _guard(*, max_total: int = 5, streak: int = 3) -> ToolRunGuard:
    return ToolRunGuard(
        max_total_calls=max_total,
        circuit_streak=streak,
        budget_refusal=lambda name, limit: f"BUDGET:{name}:{limit}",
        circuit_refusal=lambda name, streak: f"CIRCUIT:{name}:{streak}",
    )


def test_acquire_reserves_and_counts() -> None:
    guard = _guard(max_total=3)
    assert guard.acquire("t", {"a": 1}) is None
    assert guard.acquire("t", {"a": 2}) is None
    assert guard.used == 2
    assert guard.acquire("t", {"a": 3}) is None
    assert guard.used == 3
    # Soft ceiling: refused, and the refusal does not change the count.
    refusal = guard.acquire("t", {"a": 4})
    assert refusal == "BUDGET:t:3"
    assert guard.used == 3


def test_circuit_breaker_keys_on_tool_and_args() -> None:
    guard = _guard(streak=3)
    for _ in range(3):
        assert guard.acquire("t", {"repo": "a/b"}) is None
        guard.report("t", {"repo": "a/b"}, failed=True)
    blocked = guard.acquire("t", {"repo": "a/b"})
    assert blocked == "CIRCUIT:t:3"
    assert guard.used == 3, "breaker refusal refunds its own slot only"
    # Different arguments are a different workload: never blocked.
    assert guard.acquire("t", {"repo": "c/d"}) is None
    # A different tool with the same args is never blocked either.
    assert guard.acquire("other", {"repo": "a/b"}) is None


def test_report_success_clears_streak() -> None:
    guard = _guard(max_total=20, streak=3)
    for _ in range(2):
        assert guard.acquire("t", {"k": 1}) is None
        guard.report("t", {"k": 1}, failed=True)
    assert guard.acquire("t", {"k": 1}) is None
    guard.report("t", {"k": 1}, failed=False)
    # Streak cleared: two more failures are needed before the breaker trips.
    assert guard.acquire("t", {"k": 1}) is None
    guard.report("t", {"k": 1}, failed=True)
    assert guard.acquire("t", {"k": 1}) is None
    guard.report("t", {"k": 1}, failed=True)
    assert guard.acquire("t", {"k": 1}) is None


def test_args_key_normalizes_dict_order() -> None:
    guard = _guard(streak=1)
    assert guard.acquire("t", {"a": 1, "b": 2}) is None
    guard.report("t", {"b": 2, "a": 1}, failed=True)
    # Same arguments in a different insertion order are the same call.
    assert guard.acquire("t", {"b": 2, "a": 1}) == "CIRCUIT:t:1"


def test_custom_args_key_is_honored() -> None:
    class FixedKeyGuard(ToolRunGuard):

        @staticmethod
        def default_args_key(args: dict) -> str:
            return "fixed"

    guard = FixedKeyGuard(
        max_total_calls=5,
        circuit_streak=1,
        budget_refusal=lambda name, limit: f"BUDGET:{name}",
        circuit_refusal=lambda name, streak: f"CIRCUIT:{name}:{streak}",
    )
    assert guard.acquire("t", {"x": 1}) is None
    guard.report("t", {"x": 1}, failed=True)
    # Any args map to the same key, so the same tool is blocked...
    assert guard.acquire("t", {"y": 2}) == "CIRCUIT:t:1"
    # ...while a different tool never shares the breaker key.
    assert guard.acquire("other", {"y": 2}) is None
