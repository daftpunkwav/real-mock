"""Parse LLM function-calling tool arguments (shared and independent of any business domain).

For OpenAI / Anthropic / custom OpenAI protocols, tool call arguments are usually JSON strings,
but may also be dict values (some SDKs parse them early). This function handles both consistently.
"""

from __future__ import annotations

import json
from typing import Any


def parse_tool_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    """Parse tool arguments returned by the LLM (possibly a JSON string).

    Always returns a dict; returns {} when parsing fails, and the tool execution layer handles missing arguments.
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


__all__ = ["parse_tool_arguments"]
