"""Timeout + error-classification wrapper for single tool calls.

Canonical observation contract across domains:

- success → ``(raw, "done")``
- timeout → ``(json, "error")`` with ``{"error": "timeout", "tool", "message"}``
- unexpected exception → ``(json, "error")`` with ``{"error": "tool_failed", ...}``
- :class:`ApiBusinessError` propagates to the caller (the Agent loop lets it
  through; see ``loop.run_agent_loop``) instead of being disguised as a model
  observation.

Single source for the resume-review invoker and the records report agents,
which previously used three incompatible ``{"error", "name"}`` dialects.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from realmock.platform.core.agent_error_log import log_agent_error
from realmock.platform.core.errors import ApiBusinessError

from .spec import ToolBundle

logger = logging.getLogger(__name__)


def _error_scope(context: dict[str, Any] | None) -> tuple[str, str]:
    if not isinstance(context, dict):
        return "", ""
    return str(context.get("domain") or ""), str(context.get("session") or "")


async def invoke_with_timeout(
    bundle: ToolBundle,
    name: str,
    args: dict[str, Any],
    *,
    timeout: float,
    context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Run one tool. Returns ``(observation, status)``; business errors raise.

    ``context`` is an optional ``{"domain": ..., "session": ...}`` mapping
    attached to persisted agent-error records. Timeouts and unexpected
    exceptions are returned (not raised) so the model always sees them.
    """
    try:
        raw = await asyncio.wait_for(bundle.execute(name, args), timeout=timeout)
        return raw, "done"
    except asyncio.TimeoutError:
        logger.warning("Agent tool timeout name=%s timeout=%.0fs", name, timeout)
        domain, session = _error_scope(context)
        log_agent_error(
            domain=domain, session=session, tool=name, kind="timeout",
            message=f"Tool exceeded {timeout:.0f}s",
        )
        return (
            json.dumps(
                {
                    "error": "timeout",
                    "tool": name,
                    "message": f"Tool exceeded {timeout:.0f}s",
                },
                ensure_ascii=False,
            ),
            "error",
        )
    except ApiBusinessError:
        raise
    except Exception as exc:
        logger.warning("Agent tool failed name=%s: %s", name, exc, exc_info=True)
        domain, session = _error_scope(context)
        log_agent_error(
            domain=domain, session=session, tool=name, kind="tool_failed",
            message=str(exc),
        )
        return (
            json.dumps(
                {
                    "error": "tool_failed",
                    "tool": name,
                    "message": str(exc)[:400],
                },
                ensure_ascii=False,
            ),
            "error",
        )


__all__ = ["invoke_with_timeout"]
