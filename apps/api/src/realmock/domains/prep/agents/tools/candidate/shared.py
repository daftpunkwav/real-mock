"""Candidate data binding shared by profile and resume tools.

Profile/resume inspection uses live ORM binding per call (never cached across
calls): only the snapshot load runs in a worker thread; the bound handler works
on detached in-memory data.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from realmock.domains.prep.agents.tools.spec import SearchHits
from realmock.platform.capabilities.ai.agent.tools import (
    profile_from_orm,
    profile_tool_specs,
    resume_tool_specs,
    snapshot_from_payload,
)
from realmock.platform.database import api_db_session
from realmock.platform.services.candidate_read import (
    get_default_user_profile,
    get_resume_agent_payload,
)

PROFILE_RESUME_NAMES = frozenset(
    {
        "profile_list_sections",
        "profile_get_section",
        "resume_overview",
        "resume_get_section",
    }
)

# Backward-compatible alias.
_PROFILE_RESUME_NAMES = PROFILE_RESUME_NAMES


async def run_profile_or_resume(
    name: str, args: dict[str, Any], *, resume_id: int | None
) -> tuple[str, SearchHits]:
    """Profile/resume inspection with per-call live binding (never cached across calls).

    Only the ORM snapshot load runs in a worker thread; the bound handler
    itself works on detached in-memory data.
    """
    bound = await asyncio.to_thread(load_profile_or_resume_spec, name, resume_id)
    if isinstance(bound, str):
        return bound, []
    return await bound.handler(args), []


def load_profile_or_resume_spec(name: str, resume_id: int | None) -> Any:
    """Load one bound profile/resume spec; returns a JSON error string when unresolvable.

    Always run inside ``asyncio.to_thread`` (synchronous ORM access).
    """
    with api_db_session() as api_db:
        if name.startswith("profile_"):
            specs = {
                spec.name: spec
                for spec in profile_tool_specs(profile_from_orm(get_default_user_profile(api_db)))
            }
            bound = specs.get(name)
            if bound is None:
                return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)
            return bound
        payload = get_resume_agent_payload(api_db, resume_id)
        if payload is None:
            return json.dumps({"error": "no_resume_bound"}, ensure_ascii=False)
        specs = {spec.name: spec for spec in resume_tool_specs(snapshot_from_payload(payload))}
        bound = specs.get(name)
        if bound is None:
            return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)
        return bound


# Backward-compatible alias.
_load_profile_or_resume_spec = load_profile_or_resume_spec


__all__ = ["PROFILE_RESUME_NAMES", "load_profile_or_resume_spec", "run_profile_or_resume"]
