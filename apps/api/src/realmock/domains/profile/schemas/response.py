"""Profile read response contract (built from an ORM row).

Responsibilities:
- Mirror UserProfileUpdate fields plus id / updated_at
- Coerce ORM tech_domains JSON via OrmTechDomains (invalid JSON → [])

Field-set alignment with UserProfileUpdate is enforced by contract_guard.
Must not declare write-side max_length (that lives in field_meta).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from realmock.domains.profile.schemas.tech_domains import OrmTechDomains


class UserProfileResponse(BaseModel):
    """Profile read response, built from an ORM row plus id/updated_at."""

    # from_attributes: build directly from an ORM row without hand-written mapping
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    gender: str = ""
    identity: str = ""
    school: str = ""
    major: str = ""
    graduation_year: str = ""
    job_direction: str
    experience_years: str
    work_years_detail: str = ""
    current_company: str = ""
    expected_salary: str = ""
    self_intro: str = ""
    tech_domains: OrmTechDomains
    target_role: str
    github_username: str = ""
    portfolio_url: str = ""
    linkedin_url: str = ""
    city: str = ""
    preferred_languages: str = ""
    career_highlights: str = ""
    open_to_remote: str = ""
    notice_period: str = ""
    education_level: str = ""
    expected_city: str = ""
    email: str = ""
    phone: str = ""
    certificates: str = ""
    english_level: str = ""
    signature_projects: str = ""
    strengths: str = ""
    weaknesses: str = ""
    updated_at: datetime | None = None
