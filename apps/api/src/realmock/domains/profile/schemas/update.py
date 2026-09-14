"""UserProfileUpdate API contract.

Responsibilities:
- Declare the full PUT body fields (max lengths from field_meta)
- Enforce required non-blank strings and non-empty tech_domains
- Fail with 422 via Pydantic when the client omits required data

Must not touch the database or FastAPI routers.

``tech_domains`` is a list, not a string: it is excluded from
``REQUIRED_STRING_FIELDS`` on purpose. Emptiness is enforced by
``Field(min_length=1)``, ``_tech_domains_nonempty``, and the explicit
branch in ``_assert_required_present``.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from realmock.domains.profile.schemas.field_meta import (
    FIELD_MAX_LENGTH,
    REQUIRED_STRING_FIELDS,
    TECH_DOMAINS_MAX_COUNT,
)
from realmock.domains.profile.schemas.required import (
    RequiredIdentity,
    RequiredJobDirection,
    RequiredName,
    RequiredSelfIntro,
    RequiredTargetRole,
)
from realmock.domains.profile.schemas.tech_domains import UpdateTechDomains


class UserProfileUpdate(BaseModel):
    """Full profile update body."""

    name: RequiredName
    gender: str = Field("", max_length=FIELD_MAX_LENGTH["gender"])
    identity: RequiredIdentity
    school: str = Field("", max_length=FIELD_MAX_LENGTH["school"])
    major: str = Field("", max_length=FIELD_MAX_LENGTH["major"])
    graduation_year: str = Field("", max_length=FIELD_MAX_LENGTH["graduation_year"])
    job_direction: RequiredJobDirection
    experience_years: str = Field("", max_length=FIELD_MAX_LENGTH["experience_years"])
    work_years_detail: str = Field("", max_length=FIELD_MAX_LENGTH["work_years_detail"])
    current_company: str = Field("", max_length=FIELD_MAX_LENGTH["current_company"])
    expected_salary: str = Field("", max_length=FIELD_MAX_LENGTH["expected_salary"])
    self_intro: RequiredSelfIntro
    tech_domains: UpdateTechDomains = Field(
        ..., max_length=TECH_DOMAINS_MAX_COUNT, min_length=1
    )
    target_role: RequiredTargetRole
    github_username: str = Field("", max_length=FIELD_MAX_LENGTH["github_username"])
    portfolio_url: str = Field("", max_length=FIELD_MAX_LENGTH["portfolio_url"])
    linkedin_url: str = Field("", max_length=FIELD_MAX_LENGTH["linkedin_url"])
    city: str = Field("", max_length=FIELD_MAX_LENGTH["city"])
    preferred_languages: str = Field("", max_length=FIELD_MAX_LENGTH["preferred_languages"])
    career_highlights: str = Field("", max_length=FIELD_MAX_LENGTH["career_highlights"])
    open_to_remote: str = Field("", max_length=FIELD_MAX_LENGTH["open_to_remote"])
    notice_period: str = Field("", max_length=FIELD_MAX_LENGTH["notice_period"])
    education_level: str = Field("", max_length=FIELD_MAX_LENGTH["education_level"])
    expected_city: str = Field("", max_length=FIELD_MAX_LENGTH["expected_city"])
    email: str = Field("", max_length=FIELD_MAX_LENGTH["email"])
    phone: str = Field("", max_length=FIELD_MAX_LENGTH["phone"])
    certificates: str = Field("", max_length=FIELD_MAX_LENGTH["certificates"])
    english_level: str = Field("", max_length=FIELD_MAX_LENGTH["english_level"])
    signature_projects: str = Field("", max_length=FIELD_MAX_LENGTH["signature_projects"])
    strengths: str = Field("", max_length=FIELD_MAX_LENGTH["strengths"])
    weaknesses: str = Field("", max_length=FIELD_MAX_LENGTH["weaknesses"])

    @field_validator("tech_domains")
    @classmethod
    def _tech_domains_nonempty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("Fill in at least one technical field")
        return value

    @model_validator(mode="after")
    def _assert_required_present(self) -> Self:
        """Defense in depth: re-check required keys if Annotated metadata is bypassed.

        Loop is string fields only. ``tech_domains`` is checked on the next line
        because ``str([]) == "[]"`` would look filled if it were in that loop.
        """
        missing = [
            name
            for name in REQUIRED_STRING_FIELDS
            if not str(getattr(self, name, "")).strip()
        ]
        if not self.tech_domains:
            missing.append("tech_domains")
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
        return self
