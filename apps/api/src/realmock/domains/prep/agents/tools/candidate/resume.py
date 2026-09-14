"""Candidate resume tools: bound-resume overview and section inspection."""

from __future__ import annotations

from typing import Any

from realmock.platform.capabilities.ai.agent.tools import openai_tool, resume_tool_specs
from realmock.platform.capabilities.ai.agent.tools.resume import ResumeSnapshot

RESUME_NAMES = frozenset({"resume_overview", "resume_get_section"})


def resume_declaration_specs() -> list[dict[str, Any]]:
    """Function-calling declarations for resume tools (empty snapshot for shape only)."""
    specs = resume_tool_specs(ResumeSnapshot(resume_id=0, filename="", file_type=""))
    return [openai_tool(spec) for spec in specs if spec.name in RESUME_NAMES]


__all__ = ["RESUME_NAMES", "resume_declaration_specs"]
