"""System-level meta tools: discovery, compaction declaration, availability gates."""

from __future__ import annotations

from realmock.domains.prep.agents.tools.system.availability import preload_secondary, tool_available
from realmock.domains.prep.agents.tools.system.compact import COMPACT_TOOL_DEFINITION, COMPACT_TOOL_NAME
from realmock.domains.prep.agents.tools.system.search_tools import SEARCH_TOOLS_SPEC, mini_spec, search_specs

__all__ = [
    "COMPACT_TOOL_DEFINITION",
    "COMPACT_TOOL_NAME",
    "SEARCH_TOOLS_SPEC",
    "mini_spec",
    "preload_secondary",
    "search_specs",
    "tool_available",
]
