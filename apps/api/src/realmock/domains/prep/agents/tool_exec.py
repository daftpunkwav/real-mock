"""Build the Prep tool execution callback: ask_user dispatch, short-circuit for identical arguments,
circuit breaker for repeated failures, and constraints for timeouts and retrieval failures.

During tool rounds, the orchestration layer (:mod:`agents.agent`) uses
:func:`build_execute_callback` to build the think-then-act ``execute`` callback; domain-tool definitions
and execution remain in :mod:`agents.tools`. Failures are persisted via ``log_agent_error`` scoped by
``error_context`` (``{"domain": ..., "session": ...}``).

Error contract (mirrors :func:`run_agent_loop`): :class:`ApiBusinessError`
propagates to the caller so routes can render business HTTP errors; every other
failure becomes a model observation. Only one dialog (1–8 questions) per turn:
after ``ask_user`` fires, further tool calls in the same turn are refused without
executing (same-round parallel siblings still run to completion and their
results are discarded; the dialog gate only stops later rounds).

Resilience contract: every tool declares its own default timeout (a memory
lookup is instant, a web search scrapes live pages); the model may override it
per call through the injected ``timeout_seconds`` argument (clamped). Transient
failures (timeout / exception / retrieval outage) are retried automatically
twice with a short pause before they count; the circuit breaker tally is
written into every failure observation so the model sees exactly how close the
tool is to being refused (``2/3 — one more failure opens the breaker``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.orm import Session

from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.knowledge.search.web import SearchHit
from realmock.platform.core.agent_error_log import log_agent_error
from realmock.platform.core.errors import ApiBusinessError
from realmock.platform.core.security import redact_api_key

from .ask_user import dispatch_ask_user
from .tools.registry import TOOL_REGISTRY

logger = logging.getLogger(__name__)

#: Fallback timeout for tools without a spec timeout (candidate/profile
#: declarations and registry-less control tools).
_TOOL_TIMEOUT_SEC = 18.0
#: Timeouts for registry-less control tools handled inside the agent.
_CONTROL_TOOL_TIMEOUTS: dict[str, float] = {
    "compact_context": 150.0,
    "ask_user": 30.0,
}
#: Per-call override bounds (the model may not stall a turn forever).
_TIMEOUT_OVERRIDE_MIN = 5.0
_TIMEOUT_OVERRIDE_MAX = 180.0
#: Automatic retries for transient failures before the failure counts.
_TOOL_RETRY_ATTEMPTS = 2
_RETRY_PAUSE_SECONDS = 1.0
# Circuit breaker: a tool failing this many times in a row is refused without
# spending another call (mirrors the resume-review executor). Bounds retries:
# failed calls stay retryable with different args, but never spin forever.
_TOOL_CIRCUIT_BREAKER_STREAK = 3

# Structured retrieval-failure code. Observations carry this JSON code plus the
# legacy SEARCH_UNAVAILABLE marker (older prompts/models key on the marker).
RETRIEVAL_ERROR_CODE = "retrieval_unavailable"
_RETRIEVAL_LEGACY_MARKERS = ("SEARCH_UNAVAILABLE", "search temporarily unavailable")

ToolRunner = Callable[[str, dict[str, Any], Session], Awaitable[tuple[str, list[SearchHit]]]]
ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]


def _resolve_timeout(name: str, args: dict[str, Any]) -> float:
    """Per-call timeout: model override (clamped) → tool default → fallbacks."""
    override = args.get("timeout_seconds")
    if isinstance(override, (int, float)) and override > 0:
        return float(min(max(override, _TIMEOUT_OVERRIDE_MIN), _TIMEOUT_OVERRIDE_MAX))
    spec = TOOL_REGISTRY.get(name)
    if spec is not None:
        return float(spec.timeout_seconds)
    return float(_CONTROL_TOOL_TIMEOUTS.get(name, _TOOL_TIMEOUT_SEC))


def build_execute_callback(
    *,
    run_named_tool: ToolRunner,
    memory: WorkingMemory,
    db: Session,
    search_groups: list[dict[str, Any]],
    events: asyncio.Queue | None,
    asked_user: dict[str, bool] | None,
    error_context: dict[str, Any] | None = None,
) -> ToolExecutor:
    """Build the tool execution callback; ``events``/``asked_user`` enable immediate reporting through the streaming channel.

    Duplicate calls with identical arguments within the same turn are short-circuited (prevents think-then-act spinning);
    failed/timed-out calls are not cached, allowing retries with different arguments, but a tool failing
    ``_TOOL_CIRCUIT_BREAKER_STREAK`` times in a row trips the circuit breaker and is refused without
    another call. ``error_context`` (``{"domain": ..., "session": ...}``) scopes persisted error records.

    Args:
        run_named_tool: Agent-owned dispatcher ``(name, args, db)`` actually running tools.
        memory: Working memory handed to ask_user and domain handlers.
        db: Sessions database session handed to the dispatcher.
        search_groups: Mutable list collecting web-search cards for display.
        events: Optional event queue for live thinking/tool/dialog callbacks
            (None disables emission; the non-streaming channel passes None).
        asked_user: Optional one-dialog gate flag (None disables the gate).
        error_context: Optional ``{"domain": ..., "session": ...}`` scoping
            persisted error records.

    Returns:
        The ``(name, args) -> observation`` executor for the ReAct loop.
    """
    attempted: dict[str, str] = {}
    error_streak: dict[str, int] = {}

    def _scope() -> tuple[str, str]:
        if not isinstance(error_context, dict):
            return "", ""
        return str(error_context.get("domain") or ""), str(error_context.get("session") or "")

    def _circuit_note(streak: int) -> str:
        """Transparency line: the model must see how close the breaker is."""
        remaining = _TOOL_CIRCUIT_BREAKER_STREAK - streak
        return (
            f"Circuit breaker {streak}/{_TOOL_CIRCUIT_BREAKER_STREAK}: "
            f"{max(remaining, 0)} more consecutive failure(s) will block this tool."
        )

    def _failure_observation(kind: str, tool: str, message: str, streak: int) -> str:
        payload = {
            "error": kind,
            "tool": tool,
            "message": message,
            "consecutive_failures": streak,
            "breaker": f"{streak}/{_TOOL_CIRCUIT_BREAKER_STREAK}",
        }
        note = "" if streak < _TOOL_CIRCUIT_BREAKER_STREAK else (
            f" {tool} is now blocked for the rest of this turn; continue with "
            "other tools or general knowledge."
        )
        return json.dumps(payload, ensure_ascii=False) + note

    def _circuit_open_observation(tool: str) -> str:
        """Refuse a repeatedly failing tool without spending another call."""
        return json.dumps(
            {
                "error": "circuit_open",
                "tool": tool,
                "message": (
                    f"{tool} failed {_TOOL_CIRCUIT_BREAKER_STREAK} times in a row; "
                    "further calls are blocked to protect the tool budget. "
                    "Continue coaching with other tools or general knowledge."
                ),
            },
            ensure_ascii=False,
        )

    def _is_retrieval_failure(obs: str) -> bool:
        """Detect retrieval failures via the structured code or legacy markers.

        The structured ``retrieval_unavailable`` code is authoritative; legacy
        substring markers stay for observations produced before the code existed.
        """
        return RETRIEVAL_ERROR_CODE in obs or any(m in obs for m in _RETRIEVAL_LEGACY_MARKERS)

    def _dialog_already_shown() -> bool:
        return isinstance(asked_user, dict) and bool(asked_user.get("on"))

    async def execute(name: str, args: dict[str, Any]) -> str:
        if not isinstance(args, dict):
            args = {}
        if _dialog_already_shown():
            # One dialog per turn: refuse further calls without side effects.
            # Same-round parallel siblings may still race (the loop only stops
            # them after the round); sequential rounds are fully covered.
            if name == "ask_user":
                return (
                    "Duplicate dialog skipped (ask_user already shown this turn). "
                    "Continue the turn without another dialog."
                )
            return (
                f"[{name}] Skipped: a dialog is already awaiting the user this turn. "
                "Continue coaching without calling more tools."
            )
        if name == "ask_user":
            return await dispatch_ask_user(
                args=args,
                memory=memory,
                events=events,
                search_groups=search_groups,
                asked_user=asked_user,
            )
        query = args.get("query") or args.get("company") or args.get("repo") or ""
        header = f"[{name}] {query}".strip()
        if error_streak.get(name, 0) >= _TOOL_CIRCUIT_BREAKER_STREAK:
            return f"{header}\n{_circuit_open_observation(name)}"
        try:
            key = name + ":" + json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            # Non-serializable/circular args: skip dedup for this call only.
            key = ""
        if key and key in attempted:
            return (
                "Duplicate call skipped (same args as an earlier call). "
                "Continue from existing observations; change args if you truly need a retry."
            )
        if key:
            attempted[key] = ""
        domain, session = _scope()
        timeout = _resolve_timeout(name, args)
        attempts_left = 1 + max(0, _TOOL_RETRY_ATTEMPTS)
        obs: str | None = None
        hits: list[SearchHit] = []
        failure: tuple[str, str] | None = None  # (kind, message)
        while attempts_left > 0:
            attempts_left -= 1
            try:
                obs, hits = await asyncio.wait_for(
                    run_named_tool(name, args, db),
                    timeout=timeout,
                )
                if obs is not None and not _is_retrieval_failure(obs):
                    failure = None
                    break
                # Retrieval outage: retryable — the tool ran but its source failed.
                failure = ("retrieval_failed", str(obs or "")[:400])
                obs = None
            except ApiBusinessError:
                # Business failures (auth/quota/validation) must surface as HTTP
                # errors via the route layer, never as model observations.
                # ApiBusinessError subclasses HTTPException, so the FastAPI
                # envelope handler renders the catalog copy and status code.
                raise
            except asyncio.TimeoutError:
                logger.warning("Tool timeout %s (%.0fs)", name, timeout)
                failure = ("tool_timeout", f"{name} exceeded its {timeout:.0f}s timeout")
            except Exception as exc:
                # Convert to a JSON observation (resume-executor contract) so the model
                # always sees the failure and the streak counts it; never propagate
                # (ApiBusinessError above is the only exception that propagates).
                # Redact before exposing to the model: tracebacks may carry keys/paths.
                safe_detail = redact_api_key(str(exc))[:400]
                logger.warning("Tool failed %s: %s", name, safe_detail, exc_info=True)
                failure = ("tool_failed", safe_detail)
            if attempts_left > 0:
                # Transient failures get a short pause, then one more shot;
                # only the final outcome tallies the circuit breaker.
                await asyncio.sleep(_RETRY_PAUSE_SECONDS * (1 + (_TOOL_RETRY_ATTEMPTS - attempts_left)))
        if failure is not None or obs is None:
            kind, message = failure or ("tool_failed", "unknown failure")
            streak = error_streak.get(name, 0) + 1
            error_streak[name] = streak
            if key:
                attempted.pop(key, None)
            if kind == "tool_timeout":
                log_agent_error(
                    domain=domain, session=session, tool=name, kind="timeout",
                    message=f"Tool exceeded {timeout:.0f}s (after {_TOOL_RETRY_ATTEMPTS} retries)",
                )
            elif kind == "retrieval_failed":
                log_agent_error(
                    domain=domain, session=session, tool=name, kind="retrieval_failed",
                    message=message,
                )
            else:
                log_agent_error(
                    domain=domain, session=session, tool=name, kind="tool_failed",
                    message=message,
                )
            observation = _failure_observation(kind, name, message, streak)
            if kind == "retrieval_failed":
                observation += (
                    "\n\n[System constraint] Retrieval failed. Do not invent search result "
                    "lists, links, or citations; continue coaching with general knowledge "
                    "and state that it is based on general knowledge, not live search."
                )
            if name == "web_search":
                observation += (
                    "\n[Hint] A timeout here usually means the network path is slow — "
                    "retry with a higher timeout_seconds, or move on with general knowledge."
                )
            return f"{header}\n{observation}"
        if name == "web_search" and hits:
            search_groups.append({"query": str(query or ""), "results": hits})
        error_streak.pop(name, None)
        if key:
            attempted[key] = f"{header}\n{obs}"
        return f"{header}\n{obs}"

    return execute


__all__ = ["RETRIEVAL_ERROR_CODE", "build_execute_callback"]
