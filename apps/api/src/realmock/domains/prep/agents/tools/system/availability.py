"""Turn-start tool availability: name-gated static subset policy.

Predicates take (user_text, resume_id); anything unlisted is always loaded.
Secondary-tier preload gates live here too (repo talk only; memory queries wait
for an explicit search_tools call).
"""

from __future__ import annotations

import re
from typing import Any

from realmock.domains.prep.agents.tools.repo.github import GITHUB_TOOL_NAMES

#: Turn-start static subset: name-gated tools load only when relevant.
#: Predicates take (user_text, resume_id); anything unlisted is always loaded.
_TOOL_AVAILABILITY: dict[str, Any] = {}


def mentions_repo(user_text: str, resume_id: int | None) -> bool:
    """Repository signals in the turn input (repo talk only)."""
    del resume_id
    text = str(user_text or "")
    return bool(
        re.search(r"github\.com|owner\s*/\s*repo|\brepo\b|仓库|代码仓", text, re.IGNORECASE)
    )


def has_resume(user_text: str, resume_id: int | None) -> bool:
    """Resume inspection needs a bound resume."""
    del user_text
    return resume_id is not None


_TOOL_AVAILABILITY.update(
    {name: mentions_repo for name in GITHUB_TOOL_NAMES}
    | {"resume_overview": has_resume, "resume_get_section": has_resume}
)


def tool_available(name: str, user_text: str, resume_id: int | None) -> bool:
    """Whether a named tool joins this turn's declarations. Never raises."""
    try:
        predicate = _TOOL_AVAILABILITY.get(name)
        if predicate is None:
            return True
        return bool(predicate(user_text, resume_id))
    except Exception:
        return True


def preload_secondary(name: str, user_text: str, resume_id: int | None) -> bool:
    """Whether an on-demand tool preloads this turn on a matched signal gate.

    Only signal-gated secondary tools (repo talk) preload; pure on-demand
    tools (memory queries) wait for an explicit ``search_tools`` call.
    Never raises.
    """
    try:
        gate = _TOOL_AVAILABILITY.get(name)
        if gate is None:
            return False
        return bool(gate(user_text, resume_id))
    except Exception:
        return False


__all__ = ["preload_secondary", "tool_available"]
