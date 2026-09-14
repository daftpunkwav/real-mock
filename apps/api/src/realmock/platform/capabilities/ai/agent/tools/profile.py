"""Hierarchical user-profile tools for Agents.

Two levels only:
1. ``profile_list_sections`` — the five section names and whether each is filled
2. ``profile_get_section`` — the fields of one section

Never dump the whole profile in one call. This module takes a plain snapshot
so prep / interview / resume can share it without importing ORM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec

PROFILE_SECTION_ORDER: tuple[str, ...] = (
    "basics",
    "education",
    "career",
    "skills",
    "links",
)

PROFILE_SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "basics": (
        "name",
        "gender",
        "identity",
        "city",
        "email",
        "phone",
        "preferred_languages",
    ),
    "education": (
        "school",
        "major",
        "graduation_year",
        "education_level",
        "english_level",
        "certificates",
    ),
    "career": (
        "job_direction",
        "target_role",
        "experience_years",
        "work_years_detail",
        "current_company",
        "expected_salary",
        "expected_city",
        "notice_period",
        "open_to_remote",
    ),
    "skills": (
        "tech_domains",
        "self_intro",
        "strengths",
        "weaknesses",
        "career_highlights",
        "signature_projects",
    ),
    "links": (
        "github_username",
        "portfolio_url",
        "linkedin_url",
    ),
}

PROFILE_SECTION_LABELS: dict[str, str] = {
    "basics": "Basic identity and contact",
    "education": "Education background",
    "career": "Career target and work history",
    "skills": "Skills, intro, and self-assessment",
    "links": "Public profiles and portfolio",
}


@dataclass(frozen=True)
class ProfileSnapshot:
    """Plain profile payload. Empty ``fields`` means no profile row exists."""

    fields: dict[str, Any]


def _is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    return bool(str(value).strip())


def _section_payload(snapshot: ProfileSnapshot, section: str) -> dict[str, Any]:
    keys = PROFILE_SECTION_FIELDS.get(section) or ()
    out: dict[str, Any] = {}
    for key in keys:
        value = snapshot.fields.get(key)
        if value is not None:
            out[key] = value
    return out


def profile_from_orm(row: Any | None) -> ProfileSnapshot:
    """Build a snapshot from a UserProfile ORM row (or None)."""
    if row is None:
        return ProfileSnapshot(fields={})
    data: dict[str, Any] = {}
    for keys in PROFILE_SECTION_FIELDS.values():
        for key in keys:
            if key == "tech_domains":
                getter = getattr(row, "tech_domains_list", None)
                data[key] = list(getter) if getter else []
                continue
            data[key] = getattr(row, key, "") or ""
    return ProfileSnapshot(fields=data)


def profile_tool_specs(snapshot: ProfileSnapshot) -> list[ToolSpec]:
    """Bind hierarchical profile tools to one snapshot."""

    async def list_sections(args: dict[str, Any]) -> str:
        del args
        if not snapshot.fields:
            return json.dumps(
                {"available": False, "reason": "no_profile_on_file", "sections": []},
                ensure_ascii=False,
            )
        sections = []
        for key in PROFILE_SECTION_ORDER:
            payload = _section_payload(snapshot, key)
            sections.append(
                {
                    "id": key,
                    "label": PROFILE_SECTION_LABELS[key],
                    "filled": any(_is_filled(v) for v in payload.values()),
                }
            )
        return json.dumps({"available": True, "sections": sections}, ensure_ascii=False)

    async def get_section(args: dict[str, Any]) -> str:
        section = str(args.get("section") or "").strip()
        if section not in PROFILE_SECTION_FIELDS:
            return json.dumps(
                {
                    "error": "unknown_section",
                    "allowed": list(PROFILE_SECTION_ORDER),
                },
                ensure_ascii=False,
            )
        if not snapshot.fields:
            return json.dumps({"error": "no_profile_on_file", "section": section}, ensure_ascii=False)
        return json.dumps(
            {
                "section": section,
                "label": PROFILE_SECTION_LABELS[section],
                "fields": _section_payload(snapshot, section),
            },
            ensure_ascii=False,
        )

    return [
        ToolSpec(
            name="profile_list_sections",
            description=(
                "List the five user-profile sections and whether each has data. "
                "Call this before profile_get_section. Do not assume the profile "
                "duplicates the resume."
            ),
            parameters={"type": "object", "properties": {}, "required": []},
            handler=list_sections,
        ),
        ToolSpec(
            name="profile_get_section",
            description=(
                "Read one profile section (basics / education / career / skills / links). "
                "Use after profile_list_sections when that section is needed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "enum": list(PROFILE_SECTION_ORDER),
                    },
                },
                "required": ["section"],
            },
            handler=get_section,
        ),
    ]


__all__ = [
    "PROFILE_SECTION_FIELDS",
    "PROFILE_SECTION_ORDER",
    "ProfileSnapshot",
    "profile_from_orm",
    "profile_tool_specs",
]
