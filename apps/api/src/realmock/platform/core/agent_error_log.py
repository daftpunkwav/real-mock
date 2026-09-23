"""Best-effort JSONL log for agent tool/loop failures (dev/debug aid).

Disabled by default; enable with ``REALMOCK_AGENT_ERROR_LOG=1`` and point
elsewhere with ``REALMOCK_AGENT_ERROR_LOG_PATH`` (default
``logs/agent_errors.log``). Each record carries timestamp/domain/session/
tool/kind/message so a failed review can be replayed from disk.

The log never raises: diagnostics must never break a review, so every
filesystem or serialization failure is swallowed after one logger warning.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FLAG_ENV = "REALMOCK_AGENT_ERROR_LOG"
PATH_ENV = "REALMOCK_AGENT_ERROR_LOG_PATH"
DEFAULT_PATH = "logs/agent_errors.log"


def enabled() -> bool:
    """True only when the operator explicitly opted in."""
    return os.environ.get(FLAG_ENV) == "1"


def _log_path() -> Path:
    override = os.environ.get(PATH_ENV)
    return Path(override) if override else Path(DEFAULT_PATH)


def error_scope(context: dict[str, Any] | None) -> tuple[str, str]:
    """Best-effort ``(domain, session)`` pair for persisted error records.

    Single source for the Agent loop and the tool executor, which both attach
    this scope to :func:`log_agent_error` calls.
    """
    if not isinstance(context, dict):
        return "", ""
    return str(context.get("domain") or ""), str(context.get("session") or "")


def log_agent_error(
    *,
    domain: str = "",
    session: str = "",
    tool: str = "",
    kind: str = "",
    message: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one failure record. No-op when disabled; never raises."""
    if not enabled():
        return
    try:
        record: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "domain": domain,
            "session": str(session or ""),
            "tool": tool,
            "kind": kind,
            "message": str(message or "")[:2000],
        }
        if extra:
            record["extra"] = extra
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Agent error log write failed: %s", exc)


__all__ = [
    "DEFAULT_PATH",
    "FLAG_ENV",
    "PATH_ENV",
    "enabled",
    "error_scope",
    "log_agent_error",
]
