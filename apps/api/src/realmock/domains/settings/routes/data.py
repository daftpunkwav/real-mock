"""Data-management routes: wipe all business content (configuration stays)."""

from __future__ import annotations

from fastapi import APIRouter

from realmock.domains.settings.schemas.data import DataClearResponse
from realmock.platform.services.data_reset import clear_all_business_data

router = APIRouter()


@router.post("/data/clear", response_model=DataClearResponse)
def clear_all_data() -> DataClearResponse:
    """Wipe every user-content store: sessions, resumes, profile, uploads, growth.

    Deliberately destructive and deliberately unscoped: the settings page gates
    this behind a two-step dialog (typed acknowledgement checkbox), so the
    endpoint itself stays parameter-free.
    """
    return DataClearResponse.model_validate(clear_all_business_data())
