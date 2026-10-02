"""Model-profile API (capability declarations): provider / channel / model / task-binding routes.

This file only assembles endpoints; request bodies, validation (including URL
format checks), and DB access live in
``realmock.domains.settings.services.model_registry`` / ``validation`` /
``vendor_apply``. Mounted under the ``/settings`` prefix alongside the
three-stage configuration routes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from realmock.domains.settings.schemas import (
    BindingsResponse,
    ChannelModelCatalogResponse,
    ModelOptionsResponse,
    ModelProfileResponse,
    ProviderChannelResponse,
    ProviderListResponse,
    ProviderNameResponse,
    RecommendedVendorsResponse,
    SettingsDeleteResponse,
    VendorApplyResponse,
)
from realmock.domains.settings.services.model_registry import (
    BindingUpdate,
    ChannelUpdate,
    ModelProfileCreate,
    ModelProfileUpdate,
    ProviderCreate,
    ProviderUpdate,
    list_bindings_payload,
    list_providers_payload,
    update_binding_record,
    upsert_channel,
)
from realmock.domains.settings.services.model_registry import (
    create_model as create_model_record,
)
from realmock.domains.settings.services.model_registry import (
    create_provider as create_provider_record,
)
from realmock.domains.settings.services.model_registry import (
    delete_model as delete_model_record,
)
from realmock.domains.settings.services.model_registry import (
    delete_provider as delete_provider_record,
)
from realmock.domains.settings.services.model_registry import (
    update_model as update_model_record,
)
from realmock.domains.settings.services.model_registry import (
    update_provider as update_provider_record,
)
from realmock.domains.settings.services.vendor_apply import apply_vendor, channel_model_catalog
from realmock.platform.database import get_db
from realmock.platform.services.pipeline.config import (
    get_provider_model_rows,
    profile_to_response,
)

router = APIRouter()


@router.get("/models", response_model=ModelOptionsResponse)
def list_model_options(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Flat model list for scene selector (enabled entries only, with ability bits and context windows)."""
    rows = get_provider_model_rows(db)
    return {
        "models": [
            profile_to_response(profile, provider) for profile, provider in rows if profile.enabled
        ]
    }


@router.get("/providers", response_model=ProviderListResponse)
def list_providers(db: Session = Depends(get_db)) -> dict[str, Any]:
    return list_providers_payload(db)


@router.get("/vendors", response_model=RecommendedVendorsResponse, response_model_exclude_none=True)
def recommended_vendors() -> dict[str, Any]:
    """Recommended (adapted) vendors tree: level 1 vendor, level 2 model type.

    Drives the settings-page "add provider" panel; entries carry catalog prefills
    plus the deep request template metadata when a vendor descriptor JSON exists.
    """
    from realmock.platform.vendors import recommended_vendors_payload

    return recommended_vendors_payload()


@router.post("/vendors/{vendor_id}/apply", response_model=VendorApplyResponse)
def apply_recommended_vendor(vendor_id: str, db: Session = Depends(get_db)) -> dict:
    """One-click provisioning: provider shell + one channel and default entry per adapted
    capability; Base URLs and names prefill from the vendor catalog, API Keys stay empty."""
    return apply_vendor(db, vendor_id)


@router.post("/providers", response_model=ProviderNameResponse)
def create_provider(body: ProviderCreate, db: Session = Depends(get_db)) -> dict:
    return create_provider_record(db, body)


@router.put("/providers/{provider_id}", response_model=ProviderNameResponse)
def update_provider(provider_id: int, body: ProviderUpdate, db: Session = Depends(get_db)) -> dict:
    return update_provider_record(db, provider_id, body)


@router.put("/providers/{provider_id}/channels/{kind}", response_model=ProviderChannelResponse)
def update_provider_channel(
    provider_id: int, kind: str, body: ChannelUpdate, db: Session = Depends(get_db)
) -> dict:
    return upsert_channel(db, provider_id, kind, body)


@router.get(
    "/providers/{provider_id}/channels/{kind}/catalog", response_model=ChannelModelCatalogResponse
)
def fetch_channel_model_catalog(provider_id: int, kind: str, db: Session = Depends(get_db)) -> dict:
    """Model ids offered for this channel: vendor descriptor list or the provider's
    OpenAI-compatible /models endpoint."""
    return channel_model_catalog(db, provider_id, kind)


@router.delete("/providers/{provider_id}", response_model=SettingsDeleteResponse)
def delete_provider(provider_id: int, db: Session = Depends(get_db)) -> dict:
    """Delete the provider and everything under it: model entries, channel settings,
    and task bindings pointing at its entries (the UI asks for confirmation first)."""
    return delete_provider_record(db, provider_id)


@router.post("/providers/{provider_id}/models", response_model=ModelProfileResponse)
def create_model(provider_id: int, body: ModelProfileCreate, db: Session = Depends(get_db)) -> dict:
    return create_model_record(db, provider_id, body)


@router.put("/models/{model_id}", response_model=ModelProfileResponse)
def update_model(model_id: int, body: ModelProfileUpdate, db: Session = Depends(get_db)) -> dict:
    return update_model_record(db, model_id, body)


@router.delete("/models/{model_id}", response_model=SettingsDeleteResponse)
def delete_model(model_id: int, db: Session = Depends(get_db)) -> dict:
    return delete_model_record(db, model_id)


@router.get("/bindings", response_model=BindingsResponse)
def get_bindings(db: Session = Depends(get_db)) -> dict[str, Any]:
    return list_bindings_payload(db)


@router.put("/bindings/{task}", response_model=BindingsResponse)
def update_binding(task: str, body: BindingUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    return update_binding_record(db, task, body)
