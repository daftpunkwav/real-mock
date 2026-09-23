"""Reusable public-web search tool for Agents.

Does not import FastAPI or ORM. Callers decide whether to scope queries to
job boards via ``sites``. Result counts are named constants, not literals.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec
from realmock.platform.capabilities.knowledge.search.web import SearchHit, web_search_with_hits

SEARCH_DEFAULT_MAX_RESULTS = 8
SEARCH_HARD_MAX_RESULTS = 12

OnSearchHits = Callable[[str, list[SearchHit]], None]


def _clamp_max_results(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = SEARCH_DEFAULT_MAX_RESULTS
    return max(1, min(value, SEARCH_HARD_MAX_RESULTS))


async def execute_web_search(
    args: dict[str, Any],
    *,
    default_max_results: int = SEARCH_DEFAULT_MAX_RESULTS,
    sites: list[str] | None = None,
    on_hits: OnSearchHits | None = None,
) -> str:
    """Run one web search and optionally a job-board pass, then merge unique URLs."""
    query = str(args.get("query") or "").strip()
    if not query:
        return json.dumps({"error": "empty_query"}, ensure_ascii=False)
    max_results = _clamp_max_results(args.get("max_results") or default_max_results)
    prefer_boards = bool(args.get("prefer_job_boards"))
    board_sites = sites if prefer_boards else None

    def _run_open() -> tuple[str, list[SearchHit]]:
        return web_search_with_hits(query, max_results)

    def _run_boards() -> tuple[str, list[SearchHit]]:
        return web_search_with_hits(query, max_results, sites=board_sites)

    open_text, open_hits = await asyncio.to_thread(_run_open)
    hits: list[SearchHit] = list(open_hits)
    blocks = [open_text]
    if board_sites:
        board_text, board_hits = await asyncio.to_thread(_run_boards)
        seen = {h["url"] for h in hits}
        extra = [h for h in board_hits if h["url"] not in seen]
        hits.extend(extra)
        if extra:
            blocks.append("[Job-board scoped]\n" + board_text)
    if on_hits is not None:
        on_hits(query, hits[:SEARCH_HARD_MAX_RESULTS])
    payload = {
        "query": query,
        "hit_count": len(hits),
        "results": hits[:SEARCH_HARD_MAX_RESULTS],
        "text": "\n\n".join(blocks),
    }
    return json.dumps(payload, ensure_ascii=False)


def search_tool_spec(
    *,
    default_max_results: int = SEARCH_DEFAULT_MAX_RESULTS,
    sites: list[str] | None = None,
    on_hits: OnSearchHits | None = None,
    force_job_boards: bool = False,
) -> ToolSpec:
    """Build a ``web_search`` spec bound to optional job-board sites and a hit callback."""

    async def handler(args: dict[str, Any]) -> str:
        merged = dict(args or {})
        if force_job_boards:
            merged["prefer_job_boards"] = True
        return await execute_web_search(
            merged,
            default_max_results=default_max_results,
            sites=sites,
            on_hits=on_hits,
        )

    board_hint = (
        "Job-board domains configured by the caller are always included."
        if force_job_boards
        else "Set prefer_job_boards=true to also query configured job boards."
    )
    return ToolSpec(
        name="web_search",
        description=(
            "Search the public web for hiring requirements, role keywords, interview "
            "topics, or timely technical material. If the target role is unknown, "
            "search by skills / project keywords from the resume — never invent a "
            "generic canned job title. "
            + board_hint
            + " Do not invent URLs when the tool returns SEARCH_UNAVAILABLE."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query tailored to the candidate, not a canned job title",
                },
                "max_results": {
                    "type": "integer",
                    "description": (
                        f"Hits to fetch, default {default_max_results}, "
                        f"maximum {SEARCH_HARD_MAX_RESULTS}"
                    ),
                },
                "prefer_job_boards": {
                    "type": "boolean",
                    "description": "Also search configured job-board domains and merge unique hits",
                },
            },
            "required": ["query"],
        },
        handler=handler,
        timeout_seconds=30.0,
    )


__all__ = [
    "SEARCH_DEFAULT_MAX_RESULTS",
    "SEARCH_HARD_MAX_RESULTS",
    "execute_web_search",
    "search_tool_spec",
]
