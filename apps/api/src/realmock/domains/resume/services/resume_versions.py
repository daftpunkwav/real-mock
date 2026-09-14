"""Resume version lineage: family identity and scored-history lookup.

Responsibilities:
- Resolve family ids (including legacy ``family_id=0`` rows)
- Count / locate versions inside a family
- Find the nearest lower scored version for prior-version reference

Read-only queries. Must not import FastAPI routers or mutate rows.
"""

from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from realmock.domains.resume.schemas.limits import MIN_SCORED_DIMENSIONS
from realmock.domains.resume.services.resume_mappers import load_analysis_dict
from realmock.platform.models import Resume


def family_id_of(row: Resume) -> int:
    """Resolved family id; treats 0/NULL as a singleton family of ``row.id``."""
    return int(row.family_id) if row.family_id else int(row.id or 0)


def _in_family(family_id: int):
    """Match rows whose lineage id is ``family_id``, including a legacy ancestor with family_id=0."""
    return or_(Resume.family_id == family_id, Resume.id == family_id)


def family_count(db: Session, family_id: int) -> int:
    return int(db.query(func.count(Resume.id)).filter(_in_family(family_id)).scalar() or 0)


def max_version_n(db: Session, family_id: int) -> int:
    """Highest ``version_n`` in the family; 0 when the family has no rows."""
    return int(db.query(func.max(Resume.version_n)).filter(_in_family(family_id)).scalar() or 0)


def latest_in_family(
    db: Session, family_id: int, *, exclude_id: int | None = None
) -> Resume | None:
    q = db.query(Resume).filter(_in_family(family_id))
    if exclude_id is not None:
        q = q.filter(Resume.id != exclude_id)
    return q.order_by(Resume.version_n.desc(), Resume.id.desc()).first()


def previous_scored_row(db: Session, row: Resume) -> Resume | None:
    """Nearest lower version in the family that already has analysis JSON."""
    fid = family_id_of(row)
    if not fid:
        return None
    candidates = (
        db.query(Resume)
        .filter(_in_family(fid), Resume.version_n < int(row.version_n or 1))
        .order_by(Resume.version_n.desc())
        .all()
    )
    for item in candidates:
        blob = load_analysis_dict(item.analysis, item.id)
        dims = blob.get("dimension_scores")
        if isinstance(dims, dict) and len(dims) >= MIN_SCORED_DIMENSIONS:
            return item
    return None


__all__ = [
    "family_count",
    "family_id_of",
    "latest_in_family",
    "max_version_n",
    "previous_scored_row",
]
