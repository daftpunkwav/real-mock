"""Ledger schema version and preview size limits."""

from __future__ import annotations

SCHEMA = "realmock.ledger.v1"
PREVIEW_MAX_CHARS = 2048
# Agent loop encodes tool exceptions with this prefix.
TOOL_FAILURE_PREFIXES: tuple[str, ...] = ("Tool execution failed",)

# Reserved seq for the corrupt-evidence pseudo-turn: written once by the
# legacy-blob migration, skipped by every store read/append. Writer and
# reader must agree — this constant IS that contract.
CORRUPT_SEQ = 0
# Max chars of corrupt raw JSON preserved (avoid unbounded growth); applied
# on the migration write and again defensively on the store read.
CORRUPT_RAW_MAX = 65536


def is_tool_failure_result(result: str) -> bool:
    """True when a tool observation string marks an execution failure."""
    text = result or ""
    return any(text.startswith(prefix) for prefix in TOOL_FAILURE_PREFIXES)


__all__ = [
    "CORRUPT_RAW_MAX",
    "CORRUPT_SEQ",
    "PREVIEW_MAX_CHARS",
    "SCHEMA",
    "TOOL_FAILURE_PREFIXES",
    "is_tool_failure_result",
]
