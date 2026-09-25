"""Resume ingest pipeline: disk placement, background LLM extract/parse, persistence.

Responsibilities:
- Place uploaded bytes on disk under a collision-free temp name
- Create the row immediately (``parse_status="pending"``) so upload returns fast
- Parse in a background task: extract text, parse with LLM (or degraded
  profile without a key), then persist the result

Routes own HTTP transport (multipart read, extension / size / magic checks,
family and version prechecks). This module must not import FastAPI.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from realmock.platform.core.background import spawn_background
from realmock.domains.resume.schemas.limits import (
    PARSE_FALLBACK_SUMMARY_CHARS,
    RAW_TEXT_STORE_CHARS,
)
from realmock.domains.resume.schemas.response import ResumeResponse
from realmock.domains.resume.services import resume_mappers, store
from realmock.domains.resume.services.extract import extract_resume_text
from realmock.domains.resume.services.files import find_resume_file
from realmock.domains.resume.services.parser import parse_resume_with_llm
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.config import get_settings
from realmock.platform.core.errors import raise_error
from realmock.platform.core.security import assert_within_dir, sanitize_filename
from realmock.platform.database import api_db_session
from realmock.platform.models import Resume
from realmock.platform.schemas import CandidateProfile

logger = logging.getLogger(__name__)

# Held references so fire-and-forget tasks are not garbage-collected mid-parse.


PARSE_STATUS_PENDING = "pending"
PARSE_STATUS_DONE = "done"
PARSE_STATUS_FAILED = "failed"


def _store_parse_failure(row_id: int, code: str) -> None:
    """Mark a row failed with the error code; a deleted row is ignored."""
    with api_db_session() as db:
        row = store.get_row(db, row_id)
        if row is None:
            return
        row.parse_status = PARSE_STATUS_FAILED
        row.parse_error = code
        db.commit()


def sweep_stale_pending_parses() -> int:
    """Mark rows stuck in ``pending`` as failed (B1002) — startup cleanup.

    A pending row that survives a process restart has lost its in-flight
    parse task and would otherwise spin as "parsing" forever. Rows are NOT
    re-parsed automatically (that would fire LLM calls at startup); the
    frontend offers an explicit retry instead.
    """
    with api_db_session() as db:
        rows = (
            db.query(Resume)
            .filter(Resume.parse_status == PARSE_STATUS_PENDING)
            .all()
        )
        if not rows:
            return 0
        for row in rows:
            row.parse_status = PARSE_STATUS_FAILED
            row.parse_error = "B1002"
        db.commit()
        logger.info("Marked %d interrupted resume parse(s) as failed (B1002)", len(rows))
        return len(rows)


async def _parse_resume_row(row_id: int) -> None:
    """Background parse for one uploaded resume row.

    Runs with its own DB session (held for the whole pipeline, same lifetime
    as the pre-async upload request) because the upload request's session is
    closed by the time this task executes. Any failure lands in the row
    (``parse_status="failed"`` + error code) instead of surfacing as an HTTP
    error; the file stays on disk so the row can be retried.
    """
    try:
        with api_db_session() as db:
            row = store.get_row(db, row_id)
            if row is None:
                return
            file_path = find_resume_file(row)
            if file_path is None:
                _store_parse_failure(row_id, "B1001")
                return
            try:
                llm = LLMClient.from_db(db)
                raw_text = await extract_resume_text(file_path, row.file_type, llm, db)
            except Exception as e:
                code = getattr(e, "error_code", None) or "A1004"
                logger.warning("Background resume parse failed id=%s: %s", row_id, e)
                _store_parse_failure(row_id, code)
                return
            if llm.api_key:
                try:
                    parsed = await parse_resume_with_llm(raw_text, llm)
                except Exception as e:
                    logger.warning("Background resume parse failed id=%s: %s", row_id, e)
                    _store_parse_failure(row_id, "A1004")
                    return
            else:
                parsed = CandidateProfile(
                    summary=raw_text[:PARSE_FALLBACK_SUMMARY_CHARS],
                    parse_degraded=True,
                )
            target = store.get_row(db, row_id)
            if target is None:
                return
            target.raw_text = raw_text[:RAW_TEXT_STORE_CHARS]
            target.parsed_profile = parsed.model_dump_json()
            target.parse_status = PARSE_STATUS_DONE
            target.parse_error = ""
            db.commit()
    except Exception:
        logger.exception("Background resume parse crashed id=%s", row_id)
        _store_parse_failure(row_id, "B0001")


def schedule_resume_parse(row_id: int) -> None:
    """Dispatch the background parse task for one row."""

    async def _runner() -> None:
        try:
            await _parse_resume_row(row_id)
        except Exception:
            logger.exception("Resume parse task crashed id=%s", row_id)
            _store_parse_failure(row_id, "B0001")

    spawn_background(_runner(), label=f"resume-parse-{row_id}")


def _pending_profile() -> CandidateProfile:
    """Empty profile shown while parsing is still pending."""
    return CandidateProfile()


async def ingest_resume_content(
    db: Session,
    *,
    filename: str,
    file_type: str,
    content: bytes,
    family_id: int | None = None,
) -> ResumeResponse:
    """Persist one validated upload and return immediately (parse is async).

    The HTTP request only covers validation, disk placement, and the row
    insert (``parse_status="pending"``); the LLM extract/parse runs in a
    background task and fills the row in place.
    """
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
        resume = store.insert_upload(
            db,
            filename=filename,
            file_type=file_type,
            raw_text="",
            parsed=_pending_profile(),
            family_id=family_id,
            parse_status=PARSE_STATUS_PENDING,
        )
    except Exception:
        file_path.unlink(missing_ok=True)
        raise

    store.finalize_stored_file(resume, file_path, sanitized)
    schedule_resume_parse(int(resume.id))
    return resume_mappers.to_response(resume, _pending_profile())


__all__ = [
    "PARSE_STATUS_DONE",
    "PARSE_STATUS_FAILED",
    "PARSE_STATUS_PENDING",
    "ingest_resume_content",
    "schedule_resume_parse",
    "sweep_stale_pending_parses",
]
