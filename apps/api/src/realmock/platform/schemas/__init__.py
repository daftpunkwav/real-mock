"""Contracts shared across services (Pydantic models).

Ownership rule: include only types shared by two or more services (or by a service and the
voice/LLM capability layer)—error envelopes, handler configuration, LLM settings, and company
information. Domain-specific types belong to their respective services.

Submodules are split by boundary: pipeline / errors / candidate.
"""

from realmock.platform.schemas.candidate import CandidateProfile, CompanyInfo, ResumePickerItem
from realmock.platform.schemas.errors import APIError, ErrorBody
from realmock.platform.schemas.pipeline import (
    LLMTestResponse,
    StageConfigResponse,
    StageConfigUpdate,
    StageConfigsResponse,
    StageFallbackConfig,
    StageModelCapability,
    StageTestRequest,
)

__all__ = [
    "APIError",
    "CandidateProfile",
    "CompanyInfo",
    "ErrorBody",
    "LLMTestResponse",
    "ResumePickerItem",
    "StageConfigResponse",
    "StageConfigUpdate",
    "StageConfigsResponse",
    "StageFallbackConfig",
    "StageModelCapability",
    "StageTestRequest",
]
