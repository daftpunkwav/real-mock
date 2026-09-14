"""Candidate data tools: profile family + resume family + shared live binding."""

from __future__ import annotations

from typing import Any

from realmock.domains.prep.agents.tools.candidate.profile import PROFILE_NAMES, profile_declaration_specs
from realmock.domains.prep.agents.tools.candidate.resume import RESUME_NAMES, resume_declaration_specs
from realmock.domains.prep.agents.tools.candidate.shared import (
    PROFILE_RESUME_NAMES,
    run_profile_or_resume,
)


def candidate_declaration_specs() -> list[dict[str, Any]]:
    """Function-calling declarations for all candidate tools (profile + resume shapes)."""
    specs: list[dict[str, Any]] = []
    specs.extend(profile_declaration_specs())
    specs.extend(resume_declaration_specs())
    return specs


__all__ = [
    "PROFILE_NAMES",
    "PROFILE_RESUME_NAMES",
    "RESUME_NAMES",
    "candidate_declaration_specs",
    "profile_declaration_specs",
    "resume_declaration_specs",
    "run_profile_or_resume",
]
