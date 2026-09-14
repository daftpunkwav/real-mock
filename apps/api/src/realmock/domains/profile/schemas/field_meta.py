"""Single source for profile update field lengths and required string keys.

Responsibilities:
- Declare max_length for every UserProfileUpdate string field
- Declare which string fields are required (tech_domains is constrained separately)
- Declare tech_domains item/count limits

ORM column lengths stay on UserProfile; contract_guard rejects schema max > ORM length.
Must not import FastAPI, ORM, or Pydantic models.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StringField:
    """Contract metadata for one UserProfileUpdate string field."""

    max_length: int
    required: bool = False


STRING_FIELDS: dict[str, StringField] = {
    "name": StringField(100, required=True),
    "gender": StringField(20),
    "identity": StringField(50, required=True),
    "school": StringField(200),
    "major": StringField(100),
    "graduation_year": StringField(20),
    "job_direction": StringField(100, required=True),
    "experience_years": StringField(50),
    "work_years_detail": StringField(100),
    "current_company": StringField(200),
    "expected_salary": StringField(100),
    "self_intro": StringField(2000, required=True),
    "target_role": StringField(100, required=True),
    "github_username": StringField(100),
    "portfolio_url": StringField(500),
    "linkedin_url": StringField(500),
    "city": StringField(100),
    "preferred_languages": StringField(200),
    "career_highlights": StringField(2000),
    "open_to_remote": StringField(20),
    "notice_period": StringField(50),
    "education_level": StringField(50),
    "expected_city": StringField(100),
    "email": StringField(200),
    "phone": StringField(100),
    "certificates": StringField(2000),
    "english_level": StringField(100),
    "signature_projects": StringField(2000),
    "strengths": StringField(2000),
    "weaknesses": StringField(2000),
}

FIELD_MAX_LENGTH: dict[str, int] = {
    name: spec.max_length for name, spec in STRING_FIELDS.items()
}

REQUIRED_STRING_FIELDS: tuple[str, ...] = tuple(
    name for name, spec in STRING_FIELDS.items() if spec.required
)

TECH_DOMAIN_ITEM_MAX = 50
TECH_DOMAINS_MAX_COUNT = 20
