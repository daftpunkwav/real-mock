"""Tool registry assembly: the only place that knows the full toolset.

Leaf families (basic / memory / repo / candidate / system) expose SPECS lists;
this module concatenates them once into TOOL_REGISTRY / SECONDARY_TOOLS /
DOMAIN_TOOL_DEFINITIONS. No leaf module imports this file at import time
(system/search_tools reads it lazily at call time to avoid a cycle).
"""

from __future__ import annotations

from dataclasses import replace
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

# Per-tool default execution timeouts (seconds). Tools differ wildly: a
# memory lookup is instant, a web search scrapes live pages, GitHub file
# fetches traverse redirects. The executor applies these unless the model
# overrides per call (clamped); tools missing here keep the spec default.
_TOOL_TIMEOUT_SECONDS: dict[str, float] = {
    "web_search": 25.0,
    "company_info": 5.0,
    "code_exec": 20.0,
    "quiz": 5.0,
    "take_note": 5.0,
    "memory_list_tags": 10.0,
    "memory_list_summaries": 10.0,
    "memory_get_detail": 10.0,
    "memory_write": 10.0,
    "github_list_repos": 20.0,
    "github_get_repo": 25.0,
    "github_get_readme": 20.0,
    "github_list_commits": 20.0,
    "github_get_user": 15.0,
    "github_get_file": 25.0,
    "search_tools": 10.0,
}

_TOOL_SPECS = [
    (
        replace(_spec, timeout_seconds=_TOOL_TIMEOUT_SECONDS[_spec.name])
        if _spec.name in _TOOL_TIMEOUT_SECONDS
        else _spec
    )
    for _spec in _TOOL_SPECS
]

# LLM-visible per-call timeout override: every tool schema gains one optional
# argument so the model can extend a slow call (e.g. a big file fetch) without
# a special-case schema. The executor clamps the value.
_TIMEOUT_OVERRIDE_PROPERTY: dict[str, Any] = {
    "type": "number",
    "description": (
        "Optional timeout for this single call in seconds (5-180). "
        "Omit to use the tool's default; raise it only when a previous attempt "
        "timed out legitimately (large page, slow network)."
    ),
}


def _inject_timeout_override(spec: ToolSpec) -> None:
    parameters = spec.parameters
    if not isinstance(parameters, dict):
        return
    properties = parameters.setdefault("properties", {})
    if isinstance(properties, dict) and "timeout_seconds" not in properties:
        properties["timeout_seconds"] = _TIMEOUT_OVERRIDE_PROPERTY


for _spec in _TOOL_SPECS:
    _inject_timeout_override(_spec)

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

# Candidate/profile schemas get the same override property (declaration-only
# specs built outside ToolSpec).
for _definition in DOMAIN_TOOL_DEFINITIONS:
    try:
        _params = _definition["function"]["parameters"]
        _props = _params.setdefault("properties", {})
        if isinstance(_props, dict) and "timeout_seconds" not in _props:
            _props["timeout_seconds"] = _TIMEOUT_OVERRIDE_PROPERTY
    except (KeyError, TypeError, AttributeError):
        continue

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
    """Dispatch tools through the registry.

    Args:
        name: Tool name (profile/resume names bind live ORM rows per call).
        args: Raw tool arguments (non-dict payloads are parsed first).
        memory: Working memory handed to the handler.
        resume_id: Bound resume for profile/resume inspection (or None).

    Returns:
        ``(observation_text, search_hits)``; unknown tools yield an error
        observation instead of raising.
    """
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
