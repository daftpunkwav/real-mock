"""Build the Prep tool execution callback: ask_user dispatch, short-circuit for identical arguments,
circuit breaker for repeated failures, and constraints for timeouts and retrieval failures.

During tool rounds, the orchestration layer (:mod:`agent`) uses
:func:`build_execute_callback` to build the think-then-act ``execute`` callback; domain-tool definitions
and execution remain in :mod:`tools`. Failures are persisted via ``log_agent_error`` scoped by
``error_context`` (``{"domain": ..., "session": ...}``).

Error contract (mirrors :func:`run_agent_loop`): :class:`ApiBusinessError`
propagates to the caller so routes can render business HTTP errors; every other
failure becomes a model observation. Only one dialog (1–8 questions) per turn:
after ``ask_user`` fires, further tool calls in the same turn are refused without
executing (same-round parallel siblings still run to completion and their
results are discarded; the dialog gate only stops later rounds).
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

logger = logging.getLogger(__name__)

_TOOL_TIMEOUT_SEC = 18.0
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
    """
    attempted: dict[str, str] = {}
    error_streak: dict[str, int] = {}

    def _scope() -> tuple[str, str]:
        if not isinstance(error_context, dict):
            return "", ""
        return str(error_context.get("domain") or ""), str(error_context.get("session") or "")

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
        try:
            obs, hits = await asyncio.wait_for(
                run_named_tool(name, args, db),
                timeout=_TOOL_TIMEOUT_SEC,
            )
        except ApiBusinessError:
            # Business failures (auth/quota/validation) must surface as HTTP
            # errors via the route layer, never as model observations.
            # ApiBusinessError subclasses HTTPException, so the FastAPI
            # envelope handler renders the catalog copy and status code.
            raise
        except asyncio.TimeoutError:
            logger.warning("Tool timeout %s (%.0fs)", name, _TOOL_TIMEOUT_SEC)
            log_agent_error(
                domain=domain, session=session, tool=name, kind="timeout",
                message=f"Tool exceeded {_TOOL_TIMEOUT_SEC:.0f}s",
            )
            error_streak[name] = error_streak.get(name, 0) + 1
            if key:
                attempted.pop(key, None)
            obs = (
                "SEARCH_UNAVAILABLE\n"
                + json.dumps(
                    {
                        "error": RETRIEVAL_ERROR_CODE,
                        "tool": name,
                        "message": (
                            f"Search timed out (>{_TOOL_TIMEOUT_SEC:.0f}s). "
                            "Do not invent results; continue with general knowledge."
                        ),
                    },
                    ensure_ascii=False,
                )
            )
            hits = []
        except Exception as exc:
            # Convert to a JSON observation (resume-executor contract) so the model
            # always sees the failure and the streak counts it; never propagate
            # (ApiBusinessError above is the only exception that propagates).
            # Redact before exposing to the model: tracebacks may carry keys/paths.
            safe_detail = redact_api_key(str(exc))[:400]
            logger.warning("Tool failed %s: %s", name, safe_detail, exc_info=True)
            log_agent_error(
                domain=domain, session=session, tool=name, kind="tool_failed",
                message=safe_detail,
            )
            error_streak[name] = error_streak.get(name, 0) + 1
            if key:
                attempted.pop(key, None)
            return (
                f"{header}\n"
                + json.dumps(
                    {"error": "tool_failed", "tool": name, "message": safe_detail},
                    ensure_ascii=False,
                )
            )
        if name == "web_search" and hits:
            search_groups.append({"query": str(query or ""), "results": hits})
        if _is_retrieval_failure(obs):
            error_streak[name] = error_streak.get(name, 0) + 1
            if key:
                attempted.pop(key, None)
            log_agent_error(
                domain=domain, session=session, tool=name, kind="retrieval_failed",
                message=str(obs)[:400],
            )
            obs += (
                "\n\n[System constraint] Retrieval failed. Do not invent search result "
                "lists, links, or citations; continue coaching with general knowledge "
                "and state that it is based on general knowledge, not live search."
            )
            return f"{header}\n{obs}"
        error_streak.pop(name, None)
        if key:
            attempted[key] = f"{header}\n{obs}"
        return f"{header}\n{obs}"

    return execute


__all__ = ["RETRIEVAL_ERROR_CODE", "build_execute_callback"]
