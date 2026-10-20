"""Candidate Profile and Resume Selector Contract."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CompanyInfo(BaseModel):
    id: str
    name: str
    style: str
    focus_areas: list[str]
    sample_questions: list[str]
    # The original directory data carries the following two fields at the same time; the contract layer is completed to avoid inconsistency between dual views from the same source
    interview_flow: str = ""
    pressure_level: str = ""


# Structured candidate resume profile.
#
# Produced by the resume domain parser and read by the interview Agent to build the candidate persona;
# shared by both domains, so it belongs in the platform contract layer.
class CandidateProfile(BaseModel):
    name: str = ""
    education: list[dict[str, Any]] = Field(default_factory=list)
    work_experience: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    target_role: str = ""
    github_urls: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    awards: list[str] = Field(default_factory=list)
    publications: list[str] = Field(default_factory=list)
    email: str = ""
    phone: str = ""
    city: str = ""
    layout_notes: str = ""
    parse_degraded: bool = Field(
        default=False,
        description=(
            "True when structured parse fell back to a raw-text summary "
            "(LLM failure or missing API key)."
        ),
    )


# Resume drop-down read-only summary: shared by prep/interview configuration pages, does not include analysis text and in-depth evaluation.
class ResumePickerItem(BaseModel):
    id: int
    filename: str
    is_active: bool = False
    score: int | None = None


# Read-only projection of one stored user-profile row.
#
# The agent domains (interview / prep / growth / records / resume) read the
# candidate profile through ``platform.services.candidate_read``; this model is
# the shape they receive. The ORM row stays inside the read port, so a column
# rename is mapped in one place instead of in every prompt builder that used
# to reach for the row attributes.
class UserProfileSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int = 0
    name: str = ""
    gender: str = ""
    identity: str = ""
    school: str = ""
    major: str = ""
    graduation_year: str = ""
    job_direction: str = ""
    experience_years: str = ""
    work_years_detail: str = ""
    current_company: str = ""
    expected_salary: str = ""
    expected_city: str = ""
    notice_period: str = ""
    open_to_remote: str = ""
    self_intro: str = ""
    target_role: str = ""
    github_username: str = ""
    portfolio_url: str = ""
    linkedin_url: str = ""
    city: str = ""
    preferred_languages: str = ""
    career_highlights: str = ""
    education_level: str = ""
    email: str = ""
    phone: str = ""
    certificates: str = ""
    english_level: str = ""
    signature_projects: str = ""
    strengths: str = ""
    weaknesses: str = ""
    # Decoded tech-domain list; the stored column holds JSON text.
    tech_domains_list: list[str] = Field(default_factory=list)
