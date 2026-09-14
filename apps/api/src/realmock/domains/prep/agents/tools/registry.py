"""Tool registry assembly: the only place that knows the full toolset.

Leaf families (basic / memory / repo / candidate / system) expose SPECS lists;
this module concatenates them once into TOOL_REGISTRY / SECONDARY_TOOLS /
DOMAIN_TOOL_DEFINITIONS. No leaf module imports this file at import time
(system/search_tools reads it lazily at call time to avoid a cycle).
"""

from __future__ import annotations

from typing import Any

from realmock.domains.prep.agents.tools.basic import BASIC_SPECS
from realmock.domains.prep.agents.tools.candidate import (
    PROFILE_RESUME_NAMES,
    candidate_declaration_specs,
    run_profile_or_resume,
)
from realmock.domains.prep.agents.tools.memory import MEMORY_SPECS
from realmock.domains.prep.agents.tools.repo.github import GITHUB_SPECS
from realmock.domains.prep.agents.tools.spec import ToolSpec
from realmock.domains.prep.agents.tools.system.search_tools import SEARCH_TOOLS_SPEC
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.agent.tools import openai_tool
from realmock.platform.capabilities.ai.llm.client.tool_args import parse_tool_arguments
from realmock.platform.capabilities.knowledge.search.web import SearchHit

SearchHits = list[SearchHit]

_TOOL_SPECS: list[ToolSpec] = [
    *BASIC_SPECS,
    *MEMORY_SPECS,
    *GITHUB_SPECS,
    SEARCH_TOOLS_SPEC,
]

TOOL_REGISTRY: dict[str, ToolSpec] = {spec.name: spec for spec in _TOOL_SPECS}

#: On-demand loading catalog: secondary-tier specs searchable through ``search_tools``.
SECONDARY_TOOLS: dict[str, ToolSpec] = {
    spec.name: spec for spec in _TOOL_SPECS if spec.tier == "secondary"
}

DOMAIN_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }
    for spec in _TOOL_SPECS
] + candidate_declaration_specs()

# Backward-compatible alias; prefer :data:`DOMAIN_TOOL_DEFINITIONS` for the
# registry subset and :data:`realmock.domains.prep.agents.agent.PREP_TOOL_DEFINITIONS`
# for the complete turn-start set including ``ask_user``.
PREP_TOOL_DEFINITIONS = DOMAIN_TOOL_DEFINITIONS

#: Full function-calling declarations of on-demand tools, keyed for mid-turn expansion.
#: The turn toolset only ever grows by appending these (never reordered),
#: so the cached prefix head stays stable across rounds.
SECONDARY_DEFINITIONS: dict[str, dict[str, Any]] = {
    spec.name: openai_tool(spec) for spec in SECONDARY_TOOLS.values()
}


async def execute_prep_tool(
    name: str,
    args: dict[str, Any],
    memory: WorkingMemory,
    *,
    resume_id: int | None = None,
) -> tuple[str, SearchHits]:
    """Dispatch tools through the registry; return ``(observation_text, search_hits)``."""
    if name in PROFILE_RESUME_NAMES:
        return await run_profile_or_resume(name, args, resume_id=resume_id)
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return f"Unknown tool: {name}", []
    if not isinstance(args, dict):
        args = parse_tool_arguments(args)
    return await spec.handler(args, memory)


__all__ = [
    "DOMAIN_TOOL_DEFINITIONS",
    "PREP_TOOL_DEFINITIONS",
    "SECONDARY_DEFINITIONS",
    "SECONDARY_TOOLS",
    "TOOL_REGISTRY",
    "execute_prep_tool",
]
