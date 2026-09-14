"""Candidate profile tools: user-profile section inspection."""

from __future__ import annotations

from typing import Any

from realmock.platform.capabilities.ai.agent.tools import openai_tool, profile_tool_specs
from realmock.platform.capabilities.ai.agent.tools.profile import ProfileSnapshot

PROFILE_NAMES = frozenset({"profile_list_sections", "profile_get_section"})


def profile_declaration_specs() -> list[dict[str, Any]]:
    """Function-calling declarations for profile tools (empty snapshot for shape only)."""
    specs = profile_tool_specs(ProfileSnapshot(fields={}))
    return [openai_tool(spec) for spec in specs if spec.name in PROFILE_NAMES]


__all__ = ["PROFILE_NAMES", "profile_declaration_specs"]
