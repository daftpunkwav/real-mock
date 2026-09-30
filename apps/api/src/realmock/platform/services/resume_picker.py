"""Resume drop-down summary: a read-only list shared by prep/interview configuration pages."""

from __future__ import annotations

from sqlalchemy.orm import Session, defer

from realmock.platform.models import Resume
from realmock.platform.schemas import ResumePickerItem


def list_resume_picker_items(db: Session) -> list[ResumePickerItem]:
    """Return resume id / file name / activation status / score, excluding analysis text and in-depth evaluation."""
    # Summary projection only: defer the full resume text / parsed profile /
    # analysis payloads so the drop-down never loads them for every row.
    rows = (
        db.query(Resume)
        .options(
            defer(Resume.raw_text),
            defer(Resume.parsed_profile),
            defer(Resume.analysis),
        )
        .order_by(Resume.created_at.desc())
        .all()
    )
    return [
        ResumePickerItem(
            id=r.id,
            filename=r.filename,
            is_active=bool(r.is_active),
            score=r.score,
        )
        for r in rows
    ]
