"""Candidate grounding shared by the two planners.

Responsibilities:
- Render the candidate profile block of a planner user message. Both
  planners ground their plan in the same profile fields, so the block is
  rendered once here instead of once per planner.

Contracts:
- The block is the same text for both planners; only the round planner
  caps the career highlights, and it states the cap explicitly.

Constraints:
- Pure text construction: no LLM call, no database access.
"""

from __future__ import annotations

from realmock.platform.schemas import UserProfileSnapshot

#: Characters of the career highlights the HR round planner renders. The
#: round program is a short document, so the highlights are a teaser; the
#: flow planner renders them in full.
HR_HIGHLIGHTS_MAX_CHARS = 400


def candidate_profile_block(
    profile: UserProfileSnapshot | None,
    *,
    max_highlights_chars: int | None = None,
) -> str:
    """Render the candidate profile block of a planner user message.

    Returns an empty string when there is no profile. ``max_highlights_chars``
    caps the length of the career-highlights text; without it the highlights
    are rendered in full.
    """
    if profile is None:
        return ""
    highlights = profile.career_highlights or "—"
    if max_highlights_chars is not None:
        highlights = highlights[:max_highlights_chars]
    return (
        "## Candidate profile\n"
        f"Name: {profile.name or '—'}\n"
        f"Target role: {profile.target_role or '—'}\n"
        f"Experience: {profile.experience_years or '—'} years\n"
        f"Tech domains: {', '.join(profile.tech_domains_list) or '—'}\n"
        f"Highlights: {highlights}"
    )


__all__ = ["HR_HIGHLIGHTS_MAX_CHARS", "candidate_profile_block"]
