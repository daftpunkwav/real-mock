"""Compatibility barrel for resume HTTP contracts.

Prefer ``realmock.domains.resume.schemas`` (package) or the split modules
(``analysis`` / ``request`` / ``response``). This module re-exports the same
public names so existing ``schemas.resume`` imports keep working.
"""

from realmock.domains.resume.schemas.analysis import (
    CareerAnalysis,
    CompanyFit,
    DimensionScore,
    ProjectCard,
    RepoEvidence,
    RepoVerification,
    ResumeAnalysis,
    RewriteExample,
    SectionReview,
    SkillTrust,
)
from realmock.domains.resume.schemas.request import ResumeAnalyzeRequest
from realmock.domains.resume.schemas.response import ResumeDomainLimits, ResumeResponse

__all__ = [
    "CareerAnalysis",
    "CompanyFit",
    "DimensionScore",
    "ProjectCard",
    "RepoEvidence",
    "RepoVerification",
    "ResumeAnalysis",
    "ResumeAnalyzeRequest",
    "ResumeDomainLimits",
    "ResumeResponse",
    "RewriteExample",
    "SectionReview",
    "SkillTrust",
]
