"""Memory detail tool: load one long-term memory with full turn bodies."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from realmock.domains.prep.agents.tools.spec import SearchHits, ToolSpec, TOOL_TIER_SECONDARY
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.database import sessions_db_session
from realmock.domains.prep.services import get_memory, memory_to_detail


def _get_detail_sync(memory_id: int) -> str:
    """Synchronous detail load; always run inside ``asyncio.to_thread``."""
    with sessions_db_session() as db:
        row = get_memory(db, memory_id)
        if row is None:
            return json.dumps({"error": "not_found", "id": memory_id}, ensure_ascii=False)
        payload = memory_to_detail(row).model_dump(mode="json")
    # Bound the observation: full turn bodies can be long; the summary already indexed them.
    for key in ("user_input", "agent_output"):
        if isinstance(payload.get(key), str):
            payload[key] = payload[key][:2000]
    return json.dumps(payload, ensure_ascii=False)


async def run_memory_get_detail(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """Load one memory by id; invalid ids yield a JSON error, never raise.

    Args:
        args: Tool arguments (``id`` memory id, positive).
        memory: Unused (read-only detail lookup).

    Returns:
        ``(json_text, [])`` with the detail payload or an error object.
    """
    del memory
    try:
        memory_id = int(args.get("id") or 0)
    except (TypeError, ValueError):
        memory_id = 0
    if memory_id <= 0:
        return json.dumps({"error": "invalid_id"}, ensure_ascii=False), []
    return await asyncio.to_thread(_get_detail_sync, memory_id), []


MEMORY_GET_DETAIL_SPEC = ToolSpec(
    name="memory_get_detail",
    description="Load one long-term memory with its full user input and agent output.",
    parameters={
        "type": "object",
        "properties": {"id": {"type": "integer"}},
        "required": ["id"],
    },
    handler=run_memory_get_detail,
    tier=TOOL_TIER_SECONDARY,
    keywords=("memory", "detail", "记忆", "详情", "full text", "全文"),
)


__all__ = ["MEMORY_GET_DETAIL_SPEC", "run_memory_get_detail"]
