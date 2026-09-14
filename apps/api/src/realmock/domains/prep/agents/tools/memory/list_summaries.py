"""Memory index tool: list long-term memory summaries."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from realmock.domains.prep.agents.tools.spec import SearchHits, ToolSpec, TOOL_TIER_SECONDARY
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.database import sessions_db_session
from realmock.domains.prep.services import (
    MEMORY_LIST_DEFAULT_LIMIT,
    MEMORY_LIST_MAX_LIMIT,
    list_memories,
    memory_to_summary,
)


def _list_summaries_sync(tag: str | None, limit: int) -> str:
    """Synchronous summary listing; always run inside ``asyncio.to_thread``."""
    with sessions_db_session() as db:
        items = [
            memory_to_summary(row).model_dump(mode="json")
            for row in list_memories(db, tag=tag, limit=limit)
        ]
    return json.dumps({"memories": items}, ensure_ascii=False)


async def run_memory_list_summaries(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """List memory index entries (id/summary/tags, newest first).

    Args:
        args: Tool arguments (``tag`` optional single-tag filter, ``limit``
            clamped to the service list window).
        memory: Unused (read-only index lookup).

    Returns:
        ``(json_text, [])`` with the ``memories`` array.
    """
    del memory
    tag = str(args.get("tag") or "").strip() or None
    try:
        limit = int(args.get("limit") or MEMORY_LIST_DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = MEMORY_LIST_DEFAULT_LIMIT
    limit = max(1, min(MEMORY_LIST_MAX_LIMIT, limit))
    return await asyncio.to_thread(_list_summaries_sync, tag, limit), []


MEMORY_LIST_SUMMARIES_SPEC = ToolSpec(
    name="memory_list_summaries",
    description=(
        "List long-term memory index entries (id/summary/tags, newest first). "
        "Check before memory_write to avoid duplicates; use memory_get_detail for full text."
    ),
    parameters={
        "type": "object",
        "properties": {
            "tag": {"type": "string", "description": "Filter by one tag"},
            "limit": {"type": "integer", "description": "Max entries (default 20)"},
        },
    },
    handler=run_memory_list_summaries,
    tier=TOOL_TIER_SECONDARY,
    keywords=("memory", "summary", "记忆", "摘要", "summaries", "index", "索引", "list"),
)


__all__ = ["MEMORY_LIST_SUMMARIES_SPEC", "run_memory_list_summaries"]
