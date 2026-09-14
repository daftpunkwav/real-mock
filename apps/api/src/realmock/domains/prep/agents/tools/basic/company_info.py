"""Company info tool: target-company interview style lookup."""

from __future__ import annotations

import asyncio
from typing import Any

from realmock.domains.prep.agents.tools.spec import SearchHits, ToolSpec
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.catalogs.company import get_company_context


async def run_company_info(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """Look up company interview focus.

    Args:
        args: Tool arguments (``company`` id, e.g. bytedance / tencent).
        memory: Unused (no turn state to record).

    Returns:
        ``(observation_text, [])``; unknown companies yield catalog fallback text.
    """
    del memory
    company = str(args.get("company", "") or "")
    return await asyncio.to_thread(get_company_context, company), []


COMPANY_INFO_SPEC = ToolSpec(
    name="company_info",
    description="Look up the target company's interview style, focus areas, and sample questions.",
    parameters={
        "type": "object",
        "properties": {
            "company": {
                "type": "string",
                "description": "Company id, e.g. bytedance / tencent",
            },
        },
        "required": ["company"],
    },
    handler=run_company_info,
)


__all__ = ["COMPANY_INFO_SPEC", "run_company_info"]
