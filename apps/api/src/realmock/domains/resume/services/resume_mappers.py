"""Resume row mapping: tolerant JSON coercion and API response assembly.

Responsibilities:
- Coerce corrupted JSON blobs to an empty profile / empty analysis dict
  (a damaged row degrades instead of failing the whole request)
- Map ORM rows to ``ResumeResponse``

Pure mapping: no queries, no commits, no file IO. Must not import FastAPI
routers or the store.
"""

from __future__ import annotations

import json
import logging

from realmock.domains.resume.schemas.response import ResumeResponse
from realmock.platform.models import Resume
from realmock.platform.schemas import CandidateProfile

logger = logging.getLogger(__name__)


def load_parsed_profile(raw: str | None, resume_id: int | None = None) -> CandidateProfile:
    """Parse stored profile JSON; degrade to an empty profile on corruption."""
    try:
        return CandidateProfile(**json.loads(raw or "{}"))
    except Exception as e:
        logger.warning("Resume parsing JSON corruption: id=%s err=%s", resume_id, e)
        return CandidateProfile()


def load_analysis_dict(raw: str | None, resume_id: int | None = None) -> dict:
    """Parse stored analysis JSON; degrade to ``{}`` when damaged or not an object."""
    try:
        analysis = json.loads(raw or "{}")
        if not isinstance(analysis, dict):
            raise ValueError("analysis top level is not an object")
        return analysis
    except Exception:
        logger.warning("Resume evaluation JSON corrupted: id=%s", resume_id)
        return {}


def to_response(row: Resume, profile: CandidateProfile | None = None) -> ResumeResponse:
    """Assemble an API response from an ORM row; dirty JSON degrades, never 500."""
    return ResumeResponse(
        id=row.id,
        filename=row.filename,
        file_type=row.file_type,
        parsed_profile=profile if profile is not None else load_parsed_profile(row.parsed_profile, row.id),
        is_active=bool(row.is_active),
        score=row.score,
        analysis=load_analysis_dict(row.analysis, row.id),
        created_at=row.created_at,
        family_id=int(row.family_id or row.id or 0) or int(row.id or 0),
        version_n=max(1, int(row.version_n or 1)),
    )


__all__ = ["load_analysis_dict", "load_parsed_profile", "to_response"]
