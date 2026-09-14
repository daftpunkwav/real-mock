"""Resume CRUD HTTP handlers: list / get / activate / delete / collection clears.

Responsibilities:
- Bind path operations to store persistence
- Translate missing rows into A1005
- Expose ``GET /limits`` from the domain catalog

Must not query SQLAlchemy models directly or interpret JSON blobs / file paths.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from realmock.platform.database import get_db
from realmock.platform.core.errors import raise_error
from realmock.domains.resume.schemas.limits import client_limits_payload
from realmock.domains.resume.schemas.response import ResumeDomainLimits
from realmock.domains.resume.services import resume_mappers, store


def get_resume_limits() -> ResumeDomainLimits:
    """Return static upload / analyze / dimension limits for the frontend catalog."""
    return ResumeDomainLimits.model_validate(client_limits_payload())


def list_resumes(db: Session = Depends(get_db)):
    """List all resume rows, newest first."""
    return [resume_mappers.to_response(row) for row in store.list_rows(db)]


def get_resume(resume_id: int, db: Session = Depends(get_db)):
    """Get one resume row."""
    row = store.get_row(db, resume_id)
    if not row:
        raise_error("A1005")
    return resume_mappers.to_response(row)


def activate_resume(resume_id: int, db: Session = Depends(get_db)):
    """Mark one resume row active (deactivates the rest)."""
    row = store.activate_row(db, resume_id)
    if not row:
        raise_error("A1005")
    return resume_mappers.to_response(row)


def delete_resume(resume_id: int, db: Session = Depends(get_db)):
    """Delete the resume and local files if they exist."""
    row = store.delete_row(db, resume_id)
    if not row:
        raise_error("A1005")
    return {"ok": True, "id": resume_id}


def clear_review_results(db: Session = Depends(get_db)):
    """Wipe deep-review JSON + scores for all resumes; files and rows stay."""
    return {"ok": True, "cleared": store.clear_review_results(db)}


def delete_all_resumes(db: Session = Depends(get_db)):
    """Delete every resume row and its files; review history goes with the rows."""
    return {"ok": True, "deleted": store.delete_all_rows(db)}
