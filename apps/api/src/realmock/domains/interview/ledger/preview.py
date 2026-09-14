"""JSON-safe truncation helpers for ledger tool args/results."""

from __future__ import annotations

import json
from typing import Any

from realmock.domains.interview.ledger.constants import PREVIEW_MAX_CHARS


def truncate_preview(value: Any, max_chars: int = PREVIEW_MAX_CHARS) -> Any:
    """Return a JSON-safe summary of ``value``, truncated to ``max_chars``.

    Strings are sliced. Nested structures are JSON-serialized when possible and
    truncated as text; non-serializable values become ``repr`` snippets.
    """
    if value is None:
        return None
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        return value[: max_chars - 1] + "…"
    if isinstance(value, (int, float, bool)):
        return value
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = repr(value)
    if len(text) <= max_chars:
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text
    truncated = text[: max_chars - 1] + "…"
    return truncated


__all__ = ["truncate_preview"]
