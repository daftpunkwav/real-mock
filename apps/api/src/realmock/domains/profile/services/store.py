"""Profile persistence store.

Responsibilities:
- Get-or-create the single-tenant profile row
- Apply a schema-validated ``UserProfileUpdate`` onto mapped ORM columns
- Clear every update-contract field without deleting the row

Must not import FastAPI routers or HTTP types.

Single-tenant: there is no user id. Concurrent first-insert can create
duplicate rows; ``order_by(id)`` only makes "first" deterministic, it is not
a lock. Add a unique constraint when multi-user support exists.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from realmock.platform.models import UserProfile
from realmock.domains.profile.schemas import UserProfileUpdate
from realmock.domains.profile.schemas.field_meta import FIELD_MAX_LENGTH


def get_or_create_profile(db: Session) -> UserProfile:
    """Return the sole profile row, or insert a blank row.

    Required fields stay empty until the user fills them; do not seed placeholder copy.
    """
    profile = db.query(UserProfile).order_by(UserProfile.id).first()
    if not profile:
        profile = UserProfile()
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def apply_profile_update(db: Session, body: UserProfileUpdate) -> UserProfile:
    """Write a contract-validated update body onto the sole profile row.

    ``model_dump()`` keys are Update fields. ``contract_guard`` requires those
    names to be ORM columns, so setattr here is on mapped attributes.
    """
    profile = get_or_create_profile(db)
    data = body.model_dump()
    profile.set_tech_domains(data.pop("tech_domains"))
    for field, value in data.items():
        setattr(profile, field, value)
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return profile


def clear_profile(db: Session) -> UserProfile:
    """Blank every UserProfileUpdate field on the sole row; keep id / created_at.

    PUT cannot do this: required-field validators reject empty strings.
    Keys come from field_meta so a new catalog string field is cleared automatically.
    """
    profile = get_or_create_profile(db)
    for name in FIELD_MAX_LENGTH:
        setattr(profile, name, "")
    profile.set_tech_domains([])
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return profile
