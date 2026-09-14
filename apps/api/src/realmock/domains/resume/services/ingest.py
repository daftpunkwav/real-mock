"""Resume ingest pipeline: disk placement, LLM extract/parse, persistence.

Responsibilities:
- Place uploaded bytes on disk under a collision-free temp name
- Extract text, parse with LLM (or degraded profile without a key), persist

Routes own HTTP transport (multipart read, extension / size / magic checks,
family and version prechecks). This module must not import FastAPI.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from realmock.domains.resume.schemas.limits import (
    PARSE_FALLBACK_SUMMARY_CHARS,
    RAW_TEXT_STORE_CHARS,
)
from realmock.domains.resume.schemas.response import ResumeResponse
from realmock.domains.resume.services import resume_mappers, store
from realmock.domains.resume.services.extract import extract_resume_text
from realmock.domains.resume.services.parser import parse_resume_with_llm
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.config import get_settings
from realmock.platform.core.errors import raise_error
from realmock.platform.core.security import assert_within_dir, sanitize_filename
from realmock.platform.schemas import CandidateProfile

logger = logging.getLogger(__name__)


async def ingest_resume_content(
    db: Session,
    *,
    filename: str,
    file_type: str,
    content: bytes,
    family_id: int | None = None,
) -> ResumeResponse:
    """Persist one validated upload; returns the API response model."""
    upload_dir = Path(get_settings().upload_dir).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    sanitized = sanitize_filename(filename)
    safe_name = f"{uuid.uuid4().hex[:8]}_{sanitized}"
    file_path = assert_within_dir(Path(safe_name), upload_dir)
    try:
        file_path.write_bytes(content)
    except OSError as e:
        logger.warning("Resume placement failed %s: %s", safe_name, e)
        file_path.unlink(missing_ok=True)
        raise_error("B1001", cause=e)

    try:
        llm = LLMClient.from_db(db)
        raw_text = await extract_resume_text(file_path, file_type, llm, db)

        if llm.api_key:
            parsed = await parse_resume_with_llm(raw_text, llm)
        else:
            parsed = CandidateProfile(
                summary=raw_text[:PARSE_FALLBACK_SUMMARY_CHARS],
                parse_degraded=True,
            )

        resume = store.insert_upload(
            db,
            filename=filename,
            file_type=file_type,
            raw_text=raw_text[:RAW_TEXT_STORE_CHARS],
            parsed=parsed,
            family_id=family_id,
        )
    except Exception:
        file_path.unlink(missing_ok=True)
        raise

    store.finalize_stored_file(resume, file_path, sanitized)
    return resume_mappers.to_response(resume, parsed)


__all__ = ["ingest_resume_content"]
