"""Resume drop-down summary: a read-only list shared by prep/interview configuration pages."""

from __future__ import annotations

from sqlalchemy.orm import Session

from realmock.platform.models import Resume
from realmock.platform.schemas import ResumePickerItem


def list_resume_picker_items(db: Session) -> list[ResumePickerItem]:
    """Return resume id / file name / activation status / score, excluding analysis text and in-depth evaluation."""
    rows = db.query(Resume).order_by(Resume.created_at.desc()).all()
    return [
        ResumePickerItem(
            id=r.id,
            filename=r.filename,
            is_active=bool(r.is_active),
            score=r.score,
        )
        for r in rows
    ]
