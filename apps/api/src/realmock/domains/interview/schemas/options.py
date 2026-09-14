"""Interview configuration page options and directory contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field

from realmock.platform.schemas import CompanyInfo


class WorkflowTypeOption(BaseModel):
    id: str
    name: str
    phases: list[str]


class PersonalityOption(BaseModel):
    id: str
    name: str
    description: str


class InterviewStyleOption(BaseModel):
    id: str
    name: str
    description: str


class CatalogOption(BaseModel):
    id: str
    name: str


class AvatarOption(BaseModel):
    id: str
    name: str
    voice: str = ""


class OptionsResponse(BaseModel):
    roles: list[str]
    levels: list[str]
    experience_years: list[str]
    companies: list[CompanyInfo]
    personalities: list[PersonalityOption]
    interview_styles: list[InterviewStyleOption]
    workflow_types: list[WorkflowTypeOption]
    phase_labels: dict[str, str] = Field(default_factory=dict)
    avatars: list[AvatarOption] = Field(default_factory=list)
    scenes: list[CatalogOption] = Field(default_factory=list)
    tts_voices: list[CatalogOption] = Field(default_factory=list)
    silence_nudge_seconds: int = 25
