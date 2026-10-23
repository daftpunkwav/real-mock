"""Resume domain schema exports.

Public surface:
- ``ResumeResponse`` / ``ResumeAnalysis`` / ``ResumeAnalyzeRequest``
- ``ResumeDomainLimits`` — GET /resume/limits
- result envelopes for delete / clear / page-meta operations
- nested analysis models for typed review payloads

Limits and locale helpers stay in ``limits`` / ``locale``; import them
from those modules when a caller outside HTTP needs them.
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
from realmock.domains.resume.schemas.response import (
    ResumeAnalysesClearResponse,
    ResumeCollectionDeleteResponse,
    ResumeDeleteResponse,
    ResumeDomainLimits,
    ResumePagesMetaResponse,
    ResumeResponse,
)

__all__ = [
    "CareerAnalysis",
    "CompanyFit",
    "DimensionScore",
    "ProjectCard",
    "RepoEvidence",
    "RepoVerification",
    "ResumeAnalysesClearResponse",
    "ResumeAnalysis",
    "ResumeAnalyzeRequest",
    "ResumeCollectionDeleteResponse",
    "ResumeDeleteResponse",
    "ResumeDomainLimits",
    "ResumePagesMetaResponse",
    "ResumeResponse",
    "RewriteExample",
    "SectionReview",
    "SkillTrust",
]
