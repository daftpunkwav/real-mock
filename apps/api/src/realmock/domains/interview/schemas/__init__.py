"""Mock interview domain contracts: split by subdomain and re-exported uniformly from this package."""

from __future__ import annotations

from realmock.platform.schemas import CompanyInfo, ResumePickerItem

from .options import OptionsResponse, WorkflowTypeOption
from .process import (
    InterviewProcessResponse,
    ProcessCreatedResponse,
    ProcessCreateRequest,
    ProcessRoundItem,
)
from .session import (
    AiOverrides,
    ChatMessage,
    FinishInterviewResponse,
    InterviewConfig,
    InterviewMessageRequest,
    InterviewMessageResponse,
    InterviewSessionResponse,
    InterviewStartResponse,
)

__all__ = [
    "AiOverrides",
    "ChatMessage",
    "CompanyInfo",
    "InterviewConfig",
    "InterviewProcessResponse",
    "ProcessCreateRequest",
    "ProcessCreatedResponse",
    "ProcessRoundItem",
    "ResumePickerItem",
    "InterviewMessageRequest",
    "InterviewMessageResponse",
    "InterviewStartResponse",
    "FinishInterviewResponse",
    "InterviewSessionResponse",
    "OptionsResponse",
    "WorkflowTypeOption",
]
