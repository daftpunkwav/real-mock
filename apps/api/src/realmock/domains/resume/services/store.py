"""Resume persistence store: rows, families, and on-disk files.

Responsibilities:
- List / get / activate / insert / delete resume rows
- Enforce version-count and family-id invariants (error catalog)
- Unlink on-disk files when deleting a row
- Rename an uploaded temp file to the row-unique name

Row→response mapping lives in ``resume_mappers``; family/lineage queries
live in ``resume_versions``. Must not import FastAPI routers.

Single-tenant: there is no user id. Activate uses a two-step update in one
transaction; SQLite has no row locks, so the later commit wins while keeping
the "at most one active resume" invariant.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from realmock.platform.models import Resume
from realmock.platform.config import get_settings
from realmock.platform.core.errors import raise_error
from realmock.platform.core.security import assert_within_dir
from realmock.platform.schemas import CandidateProfile
from realmock.domains.resume.schemas.limits import MAX_RESUME_VERSIONS
from realmock.domains.resume.services import resume_versions
from realmock.domains.resume.services.files import find_resume_files

logger = logging.getLogger(__name__)


def list_rows(db: Session) -> list[Resume]:
    """Return all resume rows, newest first."""
    return db.query(Resume).order_by(Resume.created_at.desc()).all()


def get_row(db: Session, resume_id: int) -> Resume | None:
    """Return the row or None when missing."""
    return db.query(Resume).filter(Resume.id == resume_id).first()


def _assign_active(db: Session, resume_id: int) -> Resume | None:
    """Set ``resume_id`` active and clear other active flags. Does not commit."""
    row = db.query(Resume).filter(Resume.id == resume_id).with_for_update().first()
    if not row:
        return None
    db.query(Resume).filter(Resume.id != resume_id, Resume.is_active.is_(True)).update(
        {Resume.is_active: False}, synchronize_session=False
    )
    row.is_active = True
    return row


def activate_row(db: Session, resume_id: int) -> Resume | None:
    """Mark ``resume_id`` active and clear every other active flag.

    SQLite ignores FOR UPDATE; the two updates commit in one transaction so
    the later writer wins and the unique-active invariant still holds.
    """
    row = _assign_active(db, resume_id)
    if not row:
        return None
    db.commit()
    db.refresh(row)
    return row


def delete_row(db: Session, resume_id: int) -> Resume | None:
    """Delete the row and best-effort unlink matching files. None if missing."""
    row = get_row(db, resume_id)
    if not row:
        return None
    was_active = bool(row.is_active)
    family_id = resume_versions.family_id_of(row)
    try:
        for path in find_resume_files(row):
            path.unlink(missing_ok=True)
    except Exception as e:
        logger.warning("Ignore error when deleting resume file: %s", e)
    db.delete(row)
    db.flush()
    if was_active:
        successor = resume_versions.latest_in_family(db, family_id, exclude_id=resume_id)
        if successor is not None:
            _assign_active(db, successor.id)
    db.commit()
    return row


def clear_review_results(db: Session) -> int:
    """Wipe deep-review JSON + scores for every row; files and rows stay.

    Returns the number of rows that actually held review results.
    """
    cleared = 0
    for row in list_rows(db):
        if (row.analysis or "{}") != "{}" or row.score is not None:
            row.analysis = "{}"
            row.score = None
            cleared += 1
    db.commit()
    return cleared


def delete_all_rows(db: Session) -> int:
    """Delete every resume row and its on-disk files. Returns deleted count."""
    deleted = 0
    for row in list_rows(db):
        if delete_row(db, int(row.id)) is not None:
            deleted += 1
    return deleted


def insert_upload(
    db: Session,
    *,
    filename: str,
    file_type: str,
    raw_text: str,
    parsed: CandidateProfile,
    family_id: int | None = None,
    parse_status: str = "done",
) -> Resume:
    """Insert a newly uploaded resume and return the refreshed row.

    ``family_id is None`` starts a new family (version 1). Otherwise append
    the next version in that family. Cap and family existence are enforced
    here so HTTP prechecks cannot race past the limit. ``parse_status``
    defaults to ``done`` for direct/legacy callers; the async ingest path
    passes ``pending``.
    """
    row = Resume(
        filename=filename,
        file_type=file_type,
        raw_text=raw_text,
        parsed_profile=parsed.model_dump_json(),
        version_n=1,
        family_id=0,
        parse_status=parse_status,
    )
    if family_id is None:
        db.add(row)
        db.flush()
        row.family_id = int(row.id)
        row.version_n = 1
    else:
        fid = int(family_id)
        if fid < 1:
            raise_error("A1005")
        count = resume_versions.family_count(db, fid)
        if count < 1:
            raise_error("A1005")
        if count >= MAX_RESUME_VERSIONS:
            raise_error("A1008", max=MAX_RESUME_VERSIONS)
        row.family_id = fid
        row.version_n = resume_versions.max_version_n(db, fid) + 1
        db.add(row)
        db.flush()
    db.commit()
    db.refresh(row)
    return row


def finalize_stored_file(row: Resume, temp_path: Path, sanitized: str) -> None:
    """Rename ``{uuid}_{sanitized}`` to ``{id}_{sanitized}``; keep uuid name on failure."""
    upload_dir = Path(get_settings().upload_dir).resolve()
    try:
        final_path = assert_within_dir(upload_dir / f"{row.id}_{sanitized}", upload_dir)
        temp_path.rename(final_path)
    except Exception:
        logger.warning("Failed to rename resume file to row unique name id=%s", row.id, exc_info=True)


__all__ = [
    "activate_row",
    "clear_review_results",
    "delete_all_rows",
    "delete_row",
    "finalize_stored_file",
    "get_row",
    "insert_upload",
    "list_rows",
]
