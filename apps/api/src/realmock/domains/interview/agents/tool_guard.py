"""Per-tool resilience for interview function tools: timeout + retry + circuit breaker.

Rounds cluster (see :mod:`realmock.domains.interview.agents`): wraps
:func:`execute_interview_tool` at the two call sites (turn loop, detailed
reference hint). Same-round parallel execution already happens in the platform
loop (:func:`run_agent_loop` via ``asyncio.gather``); this module bounds the
other axis — how long one tool may burn and how often a broken tool is
retried:

- timeout: every call gets ``timeout_sec`` (default 30s); timeouts retry once
  with the same args (transient blips are the common case);
- circuit breaker: a tool failing ``circuit_streak`` times in a row is refused
  without another call until ``circuit_ttl_sec`` passes (half-open trial);
- streaks persist in ``agent_state["_tool_guard"]`` so a chronically broken
  tool (bad token, dead endpoint) stays open across turns.

Contract (mirrors the platform loop): success — including soft-failure
observations such as ``search_failed`` — returns the observation string;
terminal guard failures raise :class:`ToolGuardError` with model-actionable
guidance (the loop renders it as ``Tool execution failed: ...`` so ledger
failure detection keeps working); :class:`ApiBusinessError` always
propagates untouched.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, MutableMapping

from realmock.platform.core.agent_error_log import log_agent_error
from realmock.platform.core.errors import ApiBusinessError
from realmock.platform.core.security import redact_api_key

logger = logging.getLogger(__name__)

#: Per-attempt wall clock for one tool call (covers inner HTTP retries).
TOOL_TIMEOUT_SEC = 30.0
#: Attempts per call: first try + one retry on timeout only.
TOOL_MAX_ATTEMPTS = 2
#: Consecutive terminal failures before the circuit opens.
TOOL_CIRCUIT_STREAK = 3
#: How long an open circuit refuses calls before a half-open trial.
CIRCUIT_OPEN_TTL_SEC = 600.0

#: agent_state key holding breaker streaks (JSON-safe, survives save_state).
GUARD_STATE_KEY = "_tool_guard"


class ToolGuardError(Exception):
    """Terminal tool-guard failure (timeout-exhausted or circuit open).

    Carries ``error_kind`` and ``already_logged`` so the platform loop can
    avoid double-counting the same guard failure in agent-error logs.
    """

    def __init__(
        self,
        message: str,
        *,
        kind: str = "tool_failed",
        already_logged: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_kind = kind
        self.already_logged = already_logged


def _scope(error_context: dict[str, Any] | None) -> tuple[str, Any]:
    if not isinstance(error_context, dict):
        return "", ""
    return str(error_context.get("domain") or ""), error_context.get("session", "")


class ToolGuard:
    """Timeout/retry/circuit-breaker wrapper around one tool-callable factory."""

    def __init__(
        self,
        *,
        timeout_sec: float = TOOL_TIMEOUT_SEC,
        max_attempts: int = TOOL_MAX_ATTEMPTS,
        circuit_streak: int = TOOL_CIRCUIT_STREAK,
        circuit_ttl_sec: float = CIRCUIT_OPEN_TTL_SEC,
        state_fn: Callable[[], MutableMapping[str, Any]] | None = None,
        error_context: dict[str, Any] | None = None,
    ) -> None:
        self.timeout_sec = timeout_sec
        self.max_attempts = max(1, max_attempts)
        self.circuit_streak = max(1, circuit_streak)
        self.circuit_ttl_sec = circuit_ttl_sec
        self._local_box: dict[str, Any] = {}
        self._scratch: dict[str, Any] = {}
        self._state_fn = state_fn
        self._error_context = error_context
        self._lock = asyncio.Lock()

    def _box(self, *, create: bool = False) -> MutableMapping[str, Any]:
        """Streak store: shared agent_state when wired, else instance-local.

        Read paths use ``create=False`` so a healthy session never grows a
        ``_tool_guard`` key; the failure path passes ``create=True``.
        """
        if self._state_fn is not None:
            try:
                state = self._state_fn()
            except Exception:
                state = None
            if isinstance(state, MutableMapping):
                if create:
                    store = state.setdefault(GUARD_STATE_KEY, {})
                    if isinstance(store, MutableMapping):
                        return store
                    return self._scratch
                existing = state.get(GUARD_STATE_KEY)
                if isinstance(existing, MutableMapping):
                    return existing
                return self._scratch
        if create:
            store = self._local_box.setdefault(GUARD_STATE_KEY, {})
            if isinstance(store, MutableMapping):
                return store
        existing = self._local_box.get(GUARD_STATE_KEY)
        if isinstance(existing, MutableMapping):
            return existing
        return self._scratch

    def _entry(self, box: MutableMapping[str, Any], name: str) -> dict[str, Any]:
        entry = box.get(name)
        if isinstance(entry, dict):
            return entry
        return {"streak": 0, "opened_at": None}

    async def run(
        self,
        name: str,
        args: dict[str, Any],
        call: Callable[[], Awaitable[str]],
    ) -> str:
        """Execute one tool call with timeout, one timeout-retry, and breaker.

        Args:
            name: tool name (breaker key + log label).
            args: tool arguments (logged on failure, never mutated).
            call: zero-arg factory producing the call coroutine (must be
                re-invokable: timeouts retry by calling it again).

        Raises:
            ToolGuardError: timeout-exhausted, tool exception, or open circuit.
            ApiBusinessError: passes through unwrapped (route-layer contract).
        """
        box = self._box()
        entry = self._entry(box, name)
        streak = int(entry.get("streak") or 0)
        opened_at = entry.get("opened_at")
        now = time.time()
        if streak >= self.circuit_streak and isinstance(opened_at, (int, float)):
            if now - opened_at < self.circuit_ttl_sec:
                raise ToolGuardError(
                    f"[{name}] unavailable: failed {streak} times in a row; "
                    "further calls are blocked for a while. Continue with other "
                    f"tools or general knowledge; do not invent {name} results."
                )
            # TTL expired: half-open trial (streak reset, this call decides).
            streak = 0
            entry = {"streak": 0, "opened_at": None}

        fail_kind = ""
        fail_msg = ""
        attempts = 0
        for attempt in range(1, self.max_attempts + 1):
            attempts = attempt
            t0 = time.perf_counter()
            try:
                result = await asyncio.wait_for(call(), timeout=self.timeout_sec)
            except ApiBusinessError:
                raise
            except asyncio.TimeoutError:
                logger.warning(
                    "tool timeout name=%s attempt=%d/%d budget=%.0fs",
                    name, attempt, self.max_attempts, self.timeout_sec,
                )
                if attempt < self.max_attempts:
                    continue
                fail_kind = "timeout"
                fail_msg = (
                    f"timed out after {self.timeout_sec:.0f}s "
                    f"(retried {self.max_attempts - 1}x)"
                )
                break
            except Exception as exc:
                # No retry: deterministic failures (bad args, code bugs) would
                # just burn a second call. The model may still retry deliberately.
                fail_kind = "tool_failed"
                fail_msg = f"failed: {redact_api_key(str(exc))[:400]}"
                break
            else:
                # Success (soft-failure observations included): close the breaker.
                if name in box:
                    box.pop(name, None)
                logger.debug(
                    "tool done name=%s ms=%.0f attempt=%d",
                    name, (time.perf_counter() - t0) * 1000.0, attempt,
                )
                return result

        async with self._lock:
            box = self._box(create=True)
            entry = self._entry(box, name)
            streak = entry.get("streak", 0) + 1
            opened = streak >= self.circuit_streak
            entry["streak"] = streak
            entry["opened_at"] = now if opened else None
            box[name] = entry
        domain, session = _scope(self._error_context)
        log_agent_error(
            domain=domain, session=session, tool=name, kind=fail_kind,
            message=f"{fail_msg} (attempts={attempts} streak={streak})",
        )
        suffix = " Further calls are blocked for a while." if opened else ""
        if fail_kind == "timeout":
            raise ToolGuardError(
                f"[{name}] {fail_msg}. Continue without it or retry later with "
                "narrower args; do not invent results." + suffix,
                kind=fail_kind,
                already_logged=True,
            )
        raise ToolGuardError(
            f"[{name}] {fail_msg}. Continue with other tools or general "
            "knowledge; do not invent results." + suffix,
            kind=fail_kind,
            already_logged=True,
        )


__all__ = [
    "CIRCUIT_OPEN_TTL_SEC",
    "GUARD_STATE_KEY",
    "TOOL_CIRCUIT_STREAK",
    "TOOL_MAX_ATTEMPTS",
    "TOOL_TIMEOUT_SEC",
    "ToolGuard",
    "ToolGuardError",
]
