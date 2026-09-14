"""Prep HTTP contract: request/response schemas for the interview-preparation domain."""

from __future__ import annotations

from realmock.platform.schemas import ResumePickerItem

from realmock.domains.prep.schemas.prep import (
    MEMORY_ORIGINS,
    PrepArchiveRequest,
    PrepCompactRequest,
    PrepCompactResponse,
    PrepContextBucket,
    PrepContextResponse,
    PrepCreateRequest,
    PrepForkRequest,
    PrepForkResponse,
    PrepHistoryMessage,
    PrepLinkRequest,
    PrepMemoryBatchDelete,
    PrepMemoryCreate,
    PrepMemoryDetail,
    PrepMemorySummary,
    PrepMemoryUpdate,
    PrepMessageRequest,
    PrepMessageResponse,
    PrepSessionCreateResponse,
    PrepSessionSummary,
    PrepSummaryUpdateRequest,
    PrepTruncateRequest,
)

__all__ = [
    "MEMORY_ORIGINS",
    "PrepArchiveRequest",
    "PrepCompactRequest",
    "PrepCompactResponse",
    "PrepContextBucket",
    "PrepContextResponse",
    "PrepCreateRequest",
    "PrepForkRequest",
    "PrepForkResponse",
    "PrepHistoryMessage",
    "PrepLinkRequest",
    "PrepMemoryBatchDelete",
    "PrepMemoryCreate",
    "PrepMemoryDetail",
    "PrepMemorySummary",
    "PrepMemoryUpdate",
    "PrepMessageRequest",
    "PrepMessageResponse",
    "PrepSessionCreateResponse",
    "PrepSessionSummary",
    "PrepSummaryUpdateRequest",
    "PrepTruncateRequest",
    "ResumePickerItem",
]
