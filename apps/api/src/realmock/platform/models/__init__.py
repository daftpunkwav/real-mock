"""Shared data-domain models (api.db).

- StageConfig / LLMSettings: processor configuration tables shared across services, extracted to
  ``realmock.platform.models.config_models`` and re-exported here for compatibility.
- Resume / UserProfile: stored in api.db; **write** ownership belongs to the profile/resume/settings domains (upload/analysis/profile CRUD).
  agent / interview **reads** must go through ``realmock.platform.services.candidate_read``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from realmock.platform.database import ApiBase
from realmock.platform.models.rate_limit_bucket import RateLimitBucket
from realmock.platform.models.config_models import (  # noqa: F401  # re-export
    IntegrationCredential,
    LLMSettings,
    LlmProvider,
    ModelProfile,
    StageConfig,
    TaskBinding,
)


logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Resume(ApiBase):
    """Uploaded resume and analysis results."""

    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, default=1)
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(20))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    parsed_profile: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analysis: Mapped[str] = mapped_column(Text, default="{}")  # Rating suggestions JSON
    family_id: Mapped[int] = mapped_column(Integer, default=0)
    version_n: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class UserProfile(ApiBase):
    """Local user profile (core candidate data, api.db; writable by the profile/resume domains).

    Single-tenant: the database contains only one profile row, with no per-user isolation; add a user dimension to the model before supporting multiple users.
    """

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    gender: Mapped[str] = mapped_column(String(20), default="")
    identity: Mapped[str] = mapped_column(String(50), default="")  # Student/employed/unemployed
    school: Mapped[str] = mapped_column(String(200), default="")
    major: Mapped[str] = mapped_column(String(100), default="")
    graduation_year: Mapped[str] = mapped_column(String(20), default="")
    job_direction: Mapped[str] = mapped_column(String(100), default="")
    experience_years: Mapped[str] = mapped_column(String(50), default="")
    work_years_detail: Mapped[str] = mapped_column(String(100), default="")
    current_company: Mapped[str] = mapped_column(String(200), default="")
    expected_salary: Mapped[str] = mapped_column(String(100), default="")
    self_intro: Mapped[str] = mapped_column(Text, default="")
    tech_domains: Mapped[str] = mapped_column(Text, default="[]")
    target_role: Mapped[str] = mapped_column(String(100), default="")
    # Extension fields: for Agent to obtain richer candidate context
    github_username: Mapped[str] = mapped_column(String(100), default="")
    portfolio_url: Mapped[str] = mapped_column(String(500), default="")
    linkedin_url: Mapped[str] = mapped_column(String(500), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    preferred_languages: Mapped[str] = mapped_column(String(200), default="")  # Such as Chinese,English
    career_highlights: Mapped[str] = mapped_column(Text, default="")
    open_to_remote: Mapped[str] = mapped_column(String(20), default="")  # yes/no/hybrid
    notice_period: Mapped[str] = mapped_column(String(50), default="")
    # Commonly used extension fields for interviews
    education_level: Mapped[str] = mapped_column(String(50), default="")  # Undergraduate/Master/PhD, etc.
    expected_city: Mapped[str] = mapped_column(String(100), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(100), default="")  # Phone or WeChat
    certificates: Mapped[str] = mapped_column(Text, default="")
    english_level: Mapped[str] = mapped_column(String(100), default="")
    signature_projects: Mapped[str] = mapped_column(Text, default="")
    strengths: Mapped[str] = mapped_column(Text, default="")
    weaknesses: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    @property
    def tech_domains_list(self) -> list[str]:
        """Decoded tech_domains for prompt builders (interview / Prep).

        Invalid JSON or a non-list value returns [] and logs a warning.
        The HTTP GET path uses ``coerce_domains_from_orm`` instead of this property.
        """
        raw = self.tech_domains
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Corrupt user_profiles.tech_domains JSON; returning []. id=%s length=%s",
                getattr(self, "id", None),
                len(raw) if isinstance(raw, str) else 0,
            )
            return []
        if isinstance(parsed, list):
            return parsed
        logger.warning(
            "user_profiles.tech_domains JSON is not a list; returning []. id=%s json_type=%s",
            getattr(self, "id", None),
            type(parsed).__name__,
        )
        return []

    def set_tech_domains(self, domains: list[str]) -> None:
        self.tech_domains = json.dumps(domains, ensure_ascii=False)


__all__ = [
    "IntegrationCredential",
    "LLMSettings",
    "LlmProvider",
    "ModelProfile",
    "RateLimitBucket",
    "Resume",
    "StageConfig",
    "TaskBinding",
    "UserProfile",
]
