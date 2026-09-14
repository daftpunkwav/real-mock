"""Resume upload HTTP handler.

Responsibilities:
- Enforce catalog size / extension / magic-number rules on the HTTP payload
- Delegate disk placement, LLM extract/parse, and persistence to ``services.ingest``

Validation numbers live in ``schemas.limits``. Persistence lives in the store.
This module must not query SQLAlchemy models directly, call the LLM, or
touch the store beyond family/version prechecks.
"""

from __future__ import annotations

from fastapi import Depends, File, UploadFile
from sqlalchemy.orm import Session

from realmock.platform.core.errors import raise_error
from realmock.platform.core.security import sniff_extension
from realmock.platform.database import get_db
from realmock.domains.resume.schemas.limits import (
    ALLOWED_EXTENSIONS,
    FILENAME_MAX_LENGTH,
    MAX_RESUME_VERSIONS,
    MAX_UPLOAD_BYTES,
)
from realmock.domains.resume.services import resume_versions, store
from realmock.domains.resume.services.ingest import ingest_resume_content


async def ingest_uploaded_file(
    file: UploadFile,
    db: Session,
    *,
    family_id: int | None = None,
):
    """Validate the HTTP payload, then delegate to the ingest service.

    ``family_id is None`` starts a new family (v1). Otherwise appends a version.
    """
    filename = (file.filename or "").strip()
    if not filename:
        raise_error("A1001")
    # Raw filename is persisted verbatim (disk name is sanitized separately);
    # reject overlong names here instead of leaking a DB DataError as 500.
    # (ext needs no length check: the allowlist constrains it to <= 4 chars.)
    if len(filename) > FILENAME_MAX_LENGTH:
        raise_error("A0003", max=FILENAME_MAX_LENGTH)

    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise_error("A1002", exts=", ".join(sorted(ALLOWED_EXTENSIONS)))

    total = 0
    chunks: list[bytes] = []
    while chunk := await file.read(64 * 1024):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise_error("A0413", max=MAX_UPLOAD_BYTES // (1024 * 1024))
        chunks.append(chunk)
    content = b"".join(chunks)
    del chunks

    if total == 0:
        raise_error("A0005")

    if not sniff_extension(content[:8], ext):
        raise_error("A1003")

    return await ingest_resume_content(
        db, filename=filename, file_type=ext, content=content, family_id=family_id
    )


async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a resume file as a new family (v1)."""
    return await ingest_uploaded_file(file, db)


async def upload_resume_version(
    resume_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Append a file as a new version of an existing family."""
    row = store.get_row(db, resume_id)
    if not row:
        raise_error("A1005")
    family_id = resume_versions.family_id_of(row)
    if resume_versions.family_count(db, family_id) >= MAX_RESUME_VERSIONS:
        raise_error("A1008", max=MAX_RESUME_VERSIONS)
    return await ingest_uploaded_file(file, db, family_id=family_id)
