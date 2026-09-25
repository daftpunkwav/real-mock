"""Candidate Profile and Resume Selector Contract."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
