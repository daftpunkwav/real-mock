"""HTTP request bodies for the resume domain.

Responsibilities:
- Optional ``POST /resume/{id}/analyze`` body (locale)

Must not import FastAPI or ORM.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from realmock.domains.resume.schemas.limits import DEFAULT_ANALYSIS_LOCALE


class ResumeAnalyzeRequest(BaseModel):
    """Optional body for ``POST /resume/{id}/analyze``.

    Missing or empty body defaults to ``zh-CN`` for backward compatibility.
    """

    locale: Literal["zh-CN", "en"] = DEFAULT_ANALYSIS_LOCALE

    @field_validator("locale", mode="before")
    @classmethod
    def _empty_locale_defaults_zh(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return DEFAULT_ANALYSIS_LOCALE
        return value
