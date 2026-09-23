"""Tool declaration primitive shared by all prep tools.

Defines the single ToolSpec shape (function-calling schema + handler) and loading tiers.
Leaf tool modules depend only on this file (plus platform/services); the
registry assembles them. No handler logic lives here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.knowledge.search.web import SearchHit

SearchHits = list[SearchHit]
ToolHandler = Callable[[dict[str, Any], WorkingMemory], Awaitable[tuple[str, SearchHits]]]


@dataclass(frozen=True)
class ToolSpec:
    """A complete declaration of a domain tool: schema + execution body."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    #: Loading tier: "primary" tools are declared every turn, "secondary"
    #: tools load on demand through ``search_tools`` (descriptions stay
    #: complete either way — tiering only defers declaration, never content).
    tier: str = "primary"
    #: Search aliases (Chinese + English) for ``search_tools`` matching.
    keywords: tuple[str, ...] = ()
    #: Default execution timeout for this tool (seconds). Tools differ wildly
    #: (a memory lookup is instant, a search scrapes the web, an LLM-powered
    #: compaction takes tens of seconds), so the timeout is declared per tool;
    #: the model may override per call via the injected ``timeout_seconds``
    #: argument (clamped by the executor).
    timeout_seconds: float = 18.0


#: Loading tiers (capability names, no vendor terms).
TOOL_TIER_PRIMARY = "primary"
TOOL_TIER_SECONDARY = "secondary"


__all__ = [
    "SearchHits",
    "ToolHandler",
    "ToolSpec",
    "TOOL_TIER_PRIMARY",
    "TOOL_TIER_SECONDARY",
]
