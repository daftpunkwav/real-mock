"""Web page fetch tool: read the full text of one page found via web_search."""

from __future__ import annotations

import json
from typing import Any

from realmock.domains.prep.agents.tools.spec import (
    TOOL_TIER_SECONDARY,
    SearchHits,
    ToolSpec,
)
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.agent.tools.fetch import execute_web_fetch


async def run_web_fetch(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """Fetch one public page and return its readable text (never raises).

    Args:
        args: ``url`` required; ``max_chars`` optional (clamped by the platform).
        memory: Working memory (the fetched URL is noted for later turns).

    Returns:
        ``(observation_text, hits)``; failures arrive as structured
        FETCH_FAILED payloads so the executor's circuit breaker sees them.
    """
    url = str(args.get("url", "") or "").strip()
    if url:
        memory.remember("note", f"fetch:{url}")
    raw = await execute_web_fetch(args or {})
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw, []
    text = str(data.get("text") or raw)
    return text, []


WEB_FETCH_SPEC = ToolSpec(
    name="web_fetch",
    description=(
        "Fetch ONE public web page (a URL you found via web_search) and read its "
        "actual content. Use it to deep-read a promising search hit, verify a "
        "claim, or quote a source accurately; never guess page contents."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Absolute http(s) URL to fetch"},
            "max_chars": {
                "type": "integer",
                "description": "Readable-text characters to return (default 6000, max 12000)",
            },
        },
        "required": ["url"],
    },
    handler=run_web_fetch,
    tier=TOOL_TIER_SECONDARY,
    keywords=(
        "web", "fetch", "url", "网页", "链接", "正文", "原文", "读取网页",
    ),
    timeout_seconds=40.0,
)


__all__ = ["WEB_FETCH_SPEC", "run_web_fetch"]
