"""Memory tag index tool: list distinct long-term memory tags."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from realmock.domains.prep.agents.tools.spec import SearchHits, ToolSpec, TOOL_TIER_SECONDARY
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.database import sessions_db_session
from realmock.domains.prep.services import memory_tags


def _list_tags_sync() -> str:
    """Synchronous tag listing; always run inside ``asyncio.to_thread``."""
    with sessions_db_session() as db:
        tags = memory_tags(db)
    return json.dumps({"tags": tags}, ensure_ascii=False)


async def run_memory_list_tags(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """List distinct memory tags (most-recently-used first).

    Args:
        args: Unused (no parameters).
        memory: Unused (read-only index lookup).

    Returns:
        ``(json_text, [])`` with the ``tags`` array.
    """
    del args, memory
    return await asyncio.to_thread(_list_tags_sync), []


MEMORY_LIST_TAGS_SPEC = ToolSpec(
    name="memory_list_tags",
    description=(
        "List distinct long-term memory tags (most-recently-used first). "
        "Call before memory_write to avoid duplicate topics."
    ),
    parameters={"type": "object", "properties": {}},
    handler=run_memory_list_tags,
    tier=TOOL_TIER_SECONDARY,
    keywords=("memory", "tag", "记忆", "标签", "tags", "index", "索引"),
)


__all__ = ["MEMORY_LIST_TAGS_SPEC", "run_memory_list_tags"]
