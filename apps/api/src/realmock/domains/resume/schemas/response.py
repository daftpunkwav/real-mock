"""HTTP response contracts for the resume domain.

Responsibilities:
- ``ResumeResponse`` for list / get / upload / activate
- ``ResumeDomainLimits`` for ``GET /resume/limits`` (frontend catalog alignment)

``analysis`` stays ``dict`` so a corrupted JSON blob degrades to ``{}``
instead of failing response validation. Typed review lives on the analyze
endpoint as ``ResumeAnalysis``.

Must not import FastAPI or ORM.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from realmock.platform.schemas import CandidateProfile
from realmock.domains.resume.schemas.limits import client_limits_payload


class ResumeResponse(BaseModel):
    """One resume row as returned by list / get / upload / activate / retry."""

    id: int
    filename: str
    file_type: str
    parsed_profile: CandidateProfile
    # Background parse lifecycle: pending | done | failed (legacy rows: done).
    parse_status: str = "done"
    parse_error: str = ""
    is_active: bool = False
    score: int | None = None
    analysis: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    family_id: int = 0
    version_n: int = 1


class ResumeDomainLimits(BaseModel):
    """Public, stable limits the frontend catalog must match.

    Source of truth is ``schemas.limits``; this model is the OpenAPI surface.
    ``x-resume-catalog`` embeds the live payload so frontend tests can
    compare values, not just property names.
    """

    model_config = ConfigDict(
        json_schema_extra={"x-resume-catalog": cast("dict[str, Any]", client_limits_payload())}
    )

    allowed_extensions: list[str]
    max_upload_bytes: int
    max_parallel_analyze: int
    dimension_keys: list[str]
    analysis_locales: list[str]
    filename_max_length: int
    file_type_max_length: int
    max_resume_versions: int
    percentile_floor: int
    percentile_ceiling: int
    min_scored_dimensions: int
    score_band_fair: int
    score_band_strong: int
    score_band_standout: int
