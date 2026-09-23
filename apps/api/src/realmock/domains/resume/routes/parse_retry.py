"""Resume background-parse retry HTTP handler.

Responsibilities:
- Re-dispatch parsing for a row whose previous attempt failed
- Reject retries while parsing is still pending (409, A1009)
- Reject retries while the row holds no on-disk file

This module must not query SQLAlchemy models directly.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from realmock.domains.resume.schemas.response import ResumeResponse
from realmock.domains.resume.services import resume_mappers, store
from realmock.domains.resume.services.files import find_resume_file
from realmock.domains.resume.services.ingest import (
    PARSE_STATUS_FAILED,
    PARSE_STATUS_PENDING,
    schedule_resume_parse,
)
from realmock.platform.core.errors import raise_error
from realmock.platform.database import get_db


async def retry_resume_parse(
    resume_id: int,
    db: Session = Depends(get_db),
) -> ResumeResponse:
    """Re-run background parsing for a failed resume row.

    ``done`` rows are also accepted (re-parse overwrites the stored result);
    only an in-flight ``pending`` row is rejected.
    """
    row = store.get_row(db, resume_id)
    if not row:
        raise_error("A1005")
    if row.parse_status == PARSE_STATUS_PENDING:
        raise_error("A1009")
    if find_resume_file(row) is None:
        raise_error("B1001")

    row.parse_status = PARSE_STATUS_PENDING
    row.parse_error = ""
    row.parsed_profile = "{}"
    row.raw_text = ""
    db.commit()
    db.refresh(row)
    schedule_resume_parse(int(row.id))
    return resume_mappers.to_response(row)


__all__ = ["retry_resume_parse"]
