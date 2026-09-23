"""Reusable GitHub Agent tools.

Wraps ``integrations.github.tools`` so prep / interview / resume share one
schema + execute path. This module must not import domain packages.
"""

from __future__ import annotations

from typing import Any

from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec
from realmock.platform.capabilities.integrations.github.tools import (
    GITHUB_TOOL_DEFINITIONS,
    execute_github_tool,
)


def github_tool_specs(*, names: frozenset[str] | None = None) -> list[ToolSpec]:
    """Return GitHub ``ToolSpec`` values, optionally filtered by function name."""
    specs: list[ToolSpec] = []
    for raw in GITHUB_TOOL_DEFINITIONS:
        fn = raw.get("function") or {}
        name = str(fn.get("name") or "")
        if not name:
            continue
        if names is not None and name not in names:
            continue

        async def handler(args: dict[str, Any], *, _name: str = name) -> str:
            return await execute_github_tool(_name, args)

        # Content endpoints return potentially large bodies; metadata endpoints
        # are single JSON round-trips.
        timeout = 25.0 if ("readme" in name or "content" in name or "file" in name) else 20.0
        specs.append(
            ToolSpec(
                name=name,
                description=str(fn.get("description") or ""),
                parameters=dict(fn.get("parameters") or {"type": "object"}),
                handler=handler,
                timeout_seconds=timeout,
            )
        )
    return specs


__all__ = ["github_tool_specs"]
