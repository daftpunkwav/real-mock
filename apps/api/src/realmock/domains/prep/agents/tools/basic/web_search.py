"""Web search tool: public interview tips / tech material lookup."""

from __future__ import annotations

import json
from typing import Any

from realmock.domains.prep.agents.tools.spec import SearchHits, ToolSpec
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.agent.tools.search import execute_web_search

_WEB_SEARCH_MAX_RESULTS = 3


_WEB_SEARCH_HARD_LIMIT = 5


async def run_web_search(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """Search public material; returns (observation_text, search_hits)."""
    query = str(args.get("query", "") or "")
    if query:
        memory.remember("note", f"search:{query}")
    try:
        requested = int(args.get("max_results") or _WEB_SEARCH_MAX_RESULTS)
    except (TypeError, ValueError):
        requested = _WEB_SEARCH_MAX_RESULTS
    max_results = max(1, min(_WEB_SEARCH_HARD_LIMIT, requested))
    raw = await execute_web_search(
        {"query": query, "max_results": max_results},
        default_max_results=_WEB_SEARCH_MAX_RESULTS,
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw, []
    hits = data.get("results") if isinstance(data.get("results"), list) else []
    text = str(data.get("text") or raw)
    return text, hits


WEB_SEARCH_SPEC = ToolSpec(
    name="web_search",
    description="Search public interview tips / tech material. Use only when you need timely info.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    handler=run_web_search,
)


__all__ = ["WEB_SEARCH_SPEC", "run_web_search"]
