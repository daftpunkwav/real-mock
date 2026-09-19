"""Composable OpenAI-function tool registry.

Domains assemble schemas + handlers without importing each other. A tool is a
``ToolSpec`` (JSON schema + async execute). ``ToolBundle`` is the runtime
dispatcher used by Agent loops.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

ToolHandler = Callable[[dict[str, Any]], Awaitable[str]]


class OpenAIToolSchema(Protocol):
    """Function-schema fields :func:`openai_tool` renders; domain specs duck-type this."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def parameters(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ToolSpec:
    """One function-calling tool: OpenAI schema fields plus an execute body."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


def openai_tool(spec: OpenAIToolSchema) -> dict[str, Any]:
    """Render a spec as an OpenAI ``tools[]`` item."""
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }


@dataclass
class ToolBundle:
    """Ordered registry. Later ``add`` calls with the same name replace the earlier spec."""

    _specs: dict[str, ToolSpec] = field(default_factory=dict)
    _order: list[str] = field(default_factory=list)

    def add(self, spec: ToolSpec) -> None:
        if spec.name not in self._specs:
            self._order.append(spec.name)
        self._specs[spec.name] = spec

    def extend(self, specs: list[ToolSpec]) -> None:
        for spec in specs:
            self.add(spec)

    def definitions(self) -> list[dict[str, Any]]:
        return [openai_tool(self._specs[name]) for name in self._order if name in self._specs]

    def names(self) -> frozenset[str]:
        return frozenset(self._specs)

    async def execute(self, name: str, args: dict[str, Any]) -> str:
        spec = self._specs.get(name)
        if spec is None:
            return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)
        if not isinstance(args, dict):
            args = {}
        return await spec.handler(args)


__all__ = ["ToolBundle", "ToolHandler", "ToolSpec", "openai_tool"]
