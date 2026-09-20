"""Ledger schema version and preview size limits."""

from __future__ import annotations

SCHEMA = "realmock.ledger.v1"
PREVIEW_MAX_CHARS = 2048
# Agent loop encodes tool exceptions with this prefix.
TOOL_FAILURE_PREFIXES: tuple[str, ...] = ("Tool execution failed",)


def is_tool_failure_result(result: str) -> bool:
    """True when a tool observation string marks an execution failure."""
    text = result or ""
    return any(text.startswith(prefix) for prefix in TOOL_FAILURE_PREFIXES)


__all__ = [
    "SCHEMA",
    "PREVIEW_MAX_CHARS",
    "TOOL_FAILURE_PREFIXES",
    "is_tool_failure_result",
]
