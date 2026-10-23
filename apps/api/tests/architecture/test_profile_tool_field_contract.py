"""The profile agent tool must read the declared profile read model.

``platform.capabilities.ai.agent.tools.profile`` publishes the five profile
sections and the field names each section carries. Those names are fields of
``UserProfileSnapshot`` — the read model the agent domains receive from
``platform.services.candidate_read``. The tool reads them dynamically, so a
rename in the read model would not be a type error there; it would silently
empty the profile section for every domain that uses the tool.

This guard keeps the two declarations in step: every exposed field must be a
declared field of the read model.
"""

from __future__ import annotations

from realmock.platform.capabilities.ai.agent.tools.profile import PROFILE_SECTION_FIELDS
from realmock.platform.schemas import UserProfileSnapshot

#: The tool's ``tech_domains`` entry is the decoded list of the read model.
_TECH_DOMAINS_ALIAS = "tech_domains"


def test_profile_tool_fields_are_declared_read_model_fields() -> None:
    """Every profile field the tool exposes exists on the read model."""
    declared = set(UserProfileSnapshot.model_fields)
    unknown = sorted(
        field
        for fields in PROFILE_SECTION_FIELDS.values()
        for field in fields
        if field != _TECH_DOMAINS_ALIAS and field not in declared
    )
    assert not unknown, (
        "the profile tool exposes fields the read model does not declare "
        f"(they would read as empty): {unknown}"
    )


def test_profile_tool_tech_domains_alias_resolves() -> None:
    """The ``tech_domains`` entry maps to the decoded list of the read model.

    This entry is the one the field-name guard above cannot cover: the tool
    key (``tech_domains``) differs from the read-model field it resolves to
    (``tech_domains_list``), so a rename there would leave the tool serving
    an empty list instead of failing the field-name check.
    """
    from realmock.platform.capabilities.ai.agent.tools.profile import snapshot_from_profile

    snapshot = snapshot_from_profile(UserProfileSnapshot(tech_domains_list=["Python", "Redis"]))
    assert snapshot.fields[_TECH_DOMAINS_ALIAS] == ["Python", "Redis"]
