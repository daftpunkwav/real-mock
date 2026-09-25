"""Timeout + error-classification wrapper for single tool calls.

Canonical observation contract across domains:

- success → ``(raw, "done")``
- timeout → ``(json, "error")`` with ``{"error": "timeout", "tool", ...}``
- unexpected exception → ``(json, "error")`` with ``{"error": "tool_failed", ...}``
- :class:`ApiBusinessError` propagates to the caller (the Agent loop lets it
  through; see ``loop.run_agent_loop``) instead of being disguised as a model
  observation.

Error observations carry the tool, an echo of the call arguments, the (large)
provider error body, and a ``hint`` for known failure classes so the model can
decide its next move from the observation alone. Transient connection errors
are retried once — they fail fast, unlike timeouts, which consume their whole
budget and are never retried here.

Single source for the resume-review invoker and the records report agents.
:class:`ToolRunGuard` is the shared per-loop policy (call budget + same-args
circuit breaker) on top of single-call execution.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from realmock.platform.core.agent_error_log import error_scope, log_agent_error
from realmock.platform.core.errors import ApiBusinessError

from .spec import ToolBundle

logger = logging.getLogger(__name__)

# Fallback wall-clock budget for tools that declare no ``timeout_seconds``.
DEFAULT_TOOL_TIMEOUT_SECONDS: float = 30.0

# Exception class names treated as transient connect-phase failures (duck-typed
# to stay dependency-free across http/urllib/asyncio transports).
_CONNECTION_ERROR_NAMES = frozenset({
    "ConnectError",
    "ConnectTimeout",
    "ConnectionError",
    "ConnectionResetError",
    "ReadError",
    "WriteError",
    "RemoteProtocolError",
    "SSLError",
})

# Upper bound for the echoed call arguments in an error observation.
_ARGS_ECHO_MAX_CHARS = 400
# Provider error bodies are small in practice; 2000 chars effectively means
# "the whole error" while still bounding a pathological HTML error page.
_ERROR_MESSAGE_MAX_CHARS = 2000


def _args_echo(args: dict[str, Any]) -> str:
    """Truncated JSON echo of the model's own call arguments."""
    try:
        rendered = json.dumps(args, ensure_ascii=False, default=str)
    except Exception:
        rendered = str(args)
    return rendered[:_ARGS_ECHO_MAX_CHARS]


def _error_hint(kind: str, exc: Exception | None) -> str:
    """Actionable next-step hint for known failure classes; empty when unknown."""
    if kind == "timeout":
        return (
            "The tool exceeded its time budget. Narrow the arguments "
            "(fewer results, one specific file or repository) or use a different tool."
        )
    text = str(exc or "").lower()
    name = type(exc).__name__ if exc is not None else ""
    if "rate limit" in text or " 429" in text or " 403" in text or "forbidden" in text:
        return (
            "Quota or access limited by the provider. Avoid repeating this call; "
            "continue with other evidence or write the final answer."
        )
    if " 404" in text or "not found" in text:
        return (
            "Target not found. Verify the identifier (repository, user, path) "
            "or pick a different target."
        )
    if " 409" in text or "conflict" in text:
        return (
            "Often an empty repository or transient API state. Retry once with "
            "different arguments or pick another repository."
        )
    if name in _CONNECTION_ERROR_NAMES:
        return (
            "Transient network failure. An identical retry may succeed, "
            "or pick different arguments."
        )
    return ""


def _error_observation(kind: str, name: str, args: dict[str, Any], exc: Exception) -> str:
    payload: dict[str, Any] = {
        "error": kind,
        "tool": name,
        "args": _args_echo(args),
        "message": str(exc)[:_ERROR_MESSAGE_MAX_CHARS],
    }
    hint = _error_hint(kind, exc)
    if hint:
        payload["hint"] = hint
    return json.dumps(payload, ensure_ascii=False)


async def invoke_with_timeout(
    bundle: ToolBundle,
    name: str,
    args: dict[str, Any],
    *,
    timeout: float | None = None,
    context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Run one tool. Returns ``(observation, status)``; business errors raise.

    ``timeout`` wins when given; otherwise the tool's declared
    ``timeout_seconds`` applies, falling back to ``DEFAULT_TOOL_TIMEOUT_SECONDS``.
    ``context`` is an optional ``{"domain": ..., "session": ...}`` mapping
    attached to persisted agent-error records. Timeouts and unexpected
    exceptions are returned (not raised) so the model always sees them.
    """
    effective = timeout
    if effective is None:
        spec_timeout = getattr(bundle, "spec_timeout", None)
        declared = spec_timeout(name) if callable(spec_timeout) else None
        effective = declared or DEFAULT_TOOL_TIMEOUT_SECONDS
    for attempt in range(2):
        try:
            raw = await asyncio.wait_for(bundle.execute(name, args), timeout=effective)
            return raw, "done"
        except asyncio.TimeoutError:
            logger.warning("Agent tool timeout name=%s timeout=%.0fs", name, effective)
            domain, session = error_scope(context)
            log_agent_error(
                domain=domain, session=session, tool=name, kind="timeout",
                message=f"Tool exceeded {effective:.0f}s",
            )
            return (
                _error_observation(
                    "timeout", name, args, TimeoutError(f"Tool exceeded {effective:.0f}s")
                ),
                "error",
            )
        except ApiBusinessError:
            raise
        except Exception as exc:
            # Connect-phase failures die in milliseconds, so one immediate
            # retry is cheap; timeouts already consumed their budget and are
            # never retried here.
            if attempt == 0 and type(exc).__name__ in _CONNECTION_ERROR_NAMES:
                logger.warning(
                    "Agent tool transient connection failure name=%s (%s); retrying once",
                    name, type(exc).__name__,
                )
                continue
            logger.warning("Agent tool failed name=%s: %s", name, exc, exc_info=True)
            domain, session = error_scope(context)
            log_agent_error(
                domain=domain, session=session, tool=name, kind="tool_failed",
                message=str(exc),
            )
            return (_error_observation("tool_failed", name, args, exc), "error")
    return (
        _error_observation("tool_failed", name, args, RuntimeError("unreachable retry state")),
        "error",
    )



class ToolRunGuard:
    """Per-loop tool-run policy shared by tool-calling agents: a total-call
    budget with a soft ceiling plus a same-args circuit breaker.

    Semantics (resume-review parity, now the shared contract):
    - ``acquire`` checks the budget first, then the breaker, and reserves the
      slot before any await point so parallel rounds cannot jointly overshoot
      the soft ceiling. A breaker refusal refunds its slot — the call never
      reached the provider, so it costs no budget.
    - ``report`` records the outcome: a failure extends that exact call's
      breaker streak, a success clears it. Different arguments are never
      blocked — the workload differs, so retrying with new args stays the
      model's decision.
    - Refusal observations are produced by the caller-provided factories so
      each domain keeps its own copy; the guard only decides *whether*.

    Not shared across loops: one guard per ``run_agent_loop`` invocation.
    """

    def __init__(
        self,
        *,
        max_total_calls: int,
        circuit_streak: int = 3,
        budget_refusal: Callable[[str, int], str],
        circuit_refusal: Callable[[str, int], str],
    ) -> None:
        self._max = max(1, int(max_total_calls))
        self._streak = max(1, int(circuit_streak))
        self._budget_refusal = budget_refusal
        self._circuit_refusal = circuit_refusal
        self.used = 0
        self._streaks: dict[tuple[str, str], int] = {}

    @staticmethod
    def default_args_key(args: dict[str, Any]) -> str:
        """Canonical breaker key for one call's arguments (bounded)."""
        try:
            return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)[:500]
        except Exception:
            return str(args)[:500]

    def acquire(self, name: str, args: dict[str, Any]) -> str | None:
        """Refusal observation when blocked/exhausted; else None (slot reserved)."""
        if self.used >= self._max:
            return self._budget_refusal(name, self._max)
        self.used += 1
        key = (name, self.default_args_key(args))
        if self._streaks.get(key, 0) >= self._streak:
            self.used -= 1  # refusal costs no provider budget
            return self._circuit_refusal(name, self._streak)
        return None

    def report(self, name: str, args: dict[str, Any], *, failed: bool) -> None:
        """Record one dispatched call's outcome for the breaker."""
        key = (name, self.default_args_key(args))
        if failed:
            self._streaks[key] = self._streaks.get(key, 0) + 1
        else:
            self._streaks.pop(key, None)


__all__ = ["DEFAULT_TOOL_TIMEOUT_SECONDS", "invoke_with_timeout", "ToolRunGuard"]
