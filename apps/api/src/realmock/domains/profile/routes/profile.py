"""Profile HTTP endpoints.

GET / PUT ``/profile`` and POST ``/profile/clear``.

Responsibilities:
- Bind FastAPI path operations to schema-validated bodies and store functions
- Fail fast at import if the Update contract drifted from the ORM / field_meta

Validation lives in schemas; persistence lives in the store. This module must
not query SQLAlchemy models directly or interpret field lengths.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from realmock.platform.database import get_db
from realmock.domains.profile.schemas import UserProfileResponse, UserProfileUpdate
from realmock.domains.profile.services import contract_guard, store

# Import-time guard: Update fields must map to ORM columns before setattr in the store.
contract_guard.assert_profile_contract_aligned()

router = APIRouter()


@router.get("", response_model=UserProfileResponse)
def get_profile(db: Session = Depends(get_db)) -> UserProfileResponse:
    """Read the sole profile row (get-or-create).

    Args:
        db: API database session (injected).

    Returns:
        The profile read response.
    """
    return UserProfileResponse.model_validate(store.get_or_create_profile(db))


@router.put("", response_model=UserProfileResponse)
def update_profile(body: UserProfileUpdate, db: Session = Depends(get_db)) -> UserProfileResponse:
    """Full PUT update of the sole profile row.

    Args:
        body: Validated full update payload.
        db: API database session (injected).

    Returns:
        The updated profile read response.
    """
    return UserProfileResponse.model_validate(store.apply_profile_update(db, body))


@router.post("/clear", response_model=UserProfileResponse)
def clear_profile(db: Session = Depends(get_db)) -> UserProfileResponse:
    """Blank every update-contract field; keep the row id. PUT cannot do this (required fields)."""
    return UserProfileResponse.model_validate(store.clear_profile(db))
