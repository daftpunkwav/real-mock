"""Prep-domain tool registry (package).

Leaf families live in basic/ / memory/ / repo/ / candidate/ / system/;
registry.py is the only assembler. This file re-exports the historical
``tools`` names so ``from ...tools import X`` keeps working.
"""

from __future__ import annotations

from realmock.domains.prep.agents.tools.registry import (
    DOMAIN_TOOL_DEFINITIONS,
    PREP_TOOL_DEFINITIONS,
    SECONDARY_DEFINITIONS,
    SECONDARY_TOOLS,
    TOOL_REGISTRY,
    execute_prep_tool,
)
from realmock.domains.prep.agents.tools.spec import (
    TOOL_TIER_PRIMARY,
    TOOL_TIER_SECONDARY,
    ToolSpec,
)
from realmock.domains.prep.agents.tools.system.availability import preload_secondary, tool_available
from realmock.domains.prep.agents.tools.system.compact import COMPACT_TOOL_DEFINITION, COMPACT_TOOL_NAME
from realmock.domains.prep.agents.tools.system.search_tools import mini_spec, search_specs

__all__ = [
    "COMPACT_TOOL_DEFINITION",
    "COMPACT_TOOL_NAME",
    "DOMAIN_TOOL_DEFINITIONS",
    "PREP_TOOL_DEFINITIONS",
    "SECONDARY_DEFINITIONS",
    "SECONDARY_TOOLS",
    "TOOL_REGISTRY",
    "TOOL_TIER_PRIMARY",
    "TOOL_TIER_SECONDARY",
    "ToolSpec",
    "execute_prep_tool",
    "mini_spec",
    "preload_secondary",
    "search_specs",
    "tool_available",
]
