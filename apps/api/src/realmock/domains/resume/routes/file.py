"""HTTP handlers for original resume file download and paginated PDF preview.

Responsibilities:
- Stream the stored file (inline vs attachment)
- Return PDF page count and server-rendered PNG pages

File lookup lives in ``files``; persistence lookup lives in the store.
This module must not query SQLAlchemy models directly or hard-code MIME maps.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from realmock.platform.models import Resume
from realmock.platform.core.errors import ApiBusinessError, raise_error
from realmock.platform.database import get_db
from realmock.domains.resume.schemas.limits import FILE_MIME
from realmock.domains.resume.services.files import find_resume_file
from realmock.domains.resume.services.render import pdf_page_count, render_pdf_page_png
from realmock.domains.resume.services import store

logger = logging.getLogger(__name__)


def _load_resume_with_file(resume_id: int, db: Session) -> tuple[Resume, Path]:
    """Load the row and locate the stored file; missing either is A1005."""
    resume = store.get_row(db, resume_id)
    if not resume:
        raise_error("A1005")
    path = find_resume_file(resume)
    if path is None:
        raise_error("A1005")
    return resume, path


def get_resume_file(
    resume_id: int,
    download: int = 0,
    db: Session = Depends(get_db),
):
    """Return the original file: inline preview by default, attachment when ``download=1``."""
    resume, path = _load_resume_with_file(resume_id, db)
    return FileResponse(
        path,
        media_type=FILE_MIME.get(resume.file_type.lower(), "application/octet-stream"),
        filename=resume.filename,
        content_disposition_type="attachment" if download else "inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )


def get_resume_pages_meta(resume_id: int, db: Session = Depends(get_db)):
    """Paged preview meta; only PDF is page-rendered, other formats return pages=0."""
    resume, path = _load_resume_with_file(resume_id, db)
    if resume.file_type.lower() != "pdf":
        return {"pages": 0}
    try:
        return {"pages": pdf_page_count(path)}
    except ApiBusinessError:
        raise
    except Exception as e:
        logger.warning("Failed to read resume page number id=%s: %s", resume_id, e)
        raise_error("A1004", cause=e)


def get_resume_page_image(resume_id: int, page_no: int, db: Session = Depends(get_db)):
    """Return a server-rendered PNG of the requested page (1-based)."""
    resume, path = _load_resume_with_file(resume_id, db)
    if resume.file_type.lower() != "pdf":
        raise_error("A0404")
    try:
        png = render_pdf_page_png(path, page_no)
    except ValueError as e:
        logger.debug("The resume page number is out of bounds id=%s page=%s: %s", resume_id, page_no, e)
        raise_error("A0404", cause=e)
    except ApiBusinessError:
        raise
    except Exception as e:
        logger.warning("Resume page rendering failed id=%s page=%s: %s", resume_id, page_no, e)
        raise_error("A1004", cause=e)
    return Response(
        content=png,
        media_type="image/png",
        headers={"X-Content-Type-Options": "nosniff"},
    )
