"""Profile tool tests for apps/api/src/realmock/platform/capabilities/ai/agent/tools/profile.py.

Covers: _is_filled branches and profile_list_sections/profile_get_section handlers
(empty/unknown/no-profile/available paths), and the mapping of the declared
candidate-profile read model onto the tool snapshot.

Conventions: no network, async handlers; asyncio_mode=auto.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    try:
        from realmock.platform.capabilities.integrations.github.github_http import (
            _LAST_QUOTA,
        )

        _LAST_QUOTA.clear()
    except Exception:
        pass
    yield
    reset_rate_limit()
    try:
        from realmock.platform.capabilities.integrations.github.github_http import (
            _LAST_QUOTA,
        )

        _LAST_QUOTA.clear()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_profile_gaps() -> None:
    from realmock.platform.capabilities.ai.agent.tools.profile import (
        ProfileSnapshot,
        _is_filled,
        profile_tool_specs,
    )

    assert _is_filled(None) is False
    assert _is_filled([]) is False
    assert _is_filled(["  ", ""]) is False
    assert _is_filled(["ok"]) is True

    empty_specs = {s.name: s for s in profile_tool_specs(ProfileSnapshot(fields={}))}
    listed = json.loads(await empty_specs["profile_list_sections"].handler({}))
    assert listed["available"] is False

    unknown = json.loads(await empty_specs["profile_get_section"].handler({"section": "nope"}))
    assert unknown["error"] == "unknown_section"

    noprof = json.loads(await empty_specs["profile_get_section"].handler({"section": "basics"}))
    assert noprof["error"] == "no_profile_on_file"

    ok_specs = {s.name: s for s in profile_tool_specs(ProfileSnapshot(fields={"name": "Ada"}))}
    listed2 = json.loads(await ok_specs["profile_list_sections"].handler({}))
    assert listed2["available"] is True
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_snapshot_from_profile_serves_the_declared_read_model() -> None:
    """The tool must serve the candidate-profile read model, not an ORM row.

    The agent domains receive a ``UserProfileSnapshot`` from the read port.
    The tool reads its fields dynamically, so a mismatch between the read
    model and the tool would silently empty a section instead of raising.
    """
    from realmock.platform.capabilities.ai.agent.tools.profile import (
        profile_tool_specs,
        snapshot_from_profile,
    )
    from realmock.platform.schemas import UserProfileSnapshot

    # No profile on file: the tool reports "no profile" instead of empty fields.
    assert snapshot_from_profile(None).fields == {}

    profile = UserProfileSnapshot(
        name="Ada",
        target_role="Backend",
        tech_domains_list=["Python", "Redis"],
    )
    snapshot = snapshot_from_profile(profile)
    assert snapshot.fields["name"] == "Ada"
    assert snapshot.fields["target_role"] == "Backend"
    # The decoded tech domains reach the tool under the tool's own key.
    assert snapshot.fields["tech_domains"] == ["Python", "Redis"]

    specs = {s.name: s for s in profile_tool_specs(snapshot)}
    listed = json.loads(await specs["profile_list_sections"].handler({}))
    assert listed["available"] is True
    skills = json.loads(await specs["profile_get_section"].handler({"section": "skills"}))
    assert skills["fields"]["tech_domains"] == ["Python", "Redis"]
