"""Model-profile API (capability declarations): provider / channel / model / task-binding routes.

Request bodies and DB access live in ``realmock.domains.settings.services.model_registry``
and ``vendor_apply``; this file only assembles routes and validates URL formats. Mounted
under the ``/settings`` prefix alongside the three-stage configuration routes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from realmock.platform.models.config_models import LlmProvider, LlmProviderChannel, ModelProfile, TaskBinding
from realmock.platform.core.errors import ApiBusinessError, get_spec
from realmock.platform.database import get_db
from realmock.platform.services.pipeline.config import (
    get_provider_model_rows,
    profile_to_response,
)
from realmock.domains.settings.services.model_registry import (
    BindingUpdate,
    CHANNEL_KINDS,
    ModelProfileCreate,
    ModelProfileUpdate,
    ChannelUpdate,
    ProviderCreate,
    ProviderUpdate,
    apply_channel_key,
    get_profile,
    get_provider,
    list_bindings_payload,
    list_providers_payload,
    merge_profile_extras,
    upsert_channel,
    update_binding_record,
)
from realmock.domains.settings.services.vendor_apply import apply_vendor, channel_model_catalog

router = APIRouter()


def _safe_base(url: str, *, label: str) -> None:
    """Validate URL protocol format only (same policy as stage config)."""
    from urllib.parse import urlparse

    from realmock.platform.config import get_settings

    if not (url or "").strip():
        return
    parsed = urlparse(url.strip())
    require_https = bool(get_settings().is_prod)
    scheme_ok = parsed.scheme == "https" if require_https else parsed.scheme in ("http", "https")
    if not scheme_ok or not parsed.hostname:
        raise ApiBusinessError(
            get_spec("A0007"),
            message=(
                f"Invalid {label}: only http(s) URLs are allowed"
                + (" (production requires https)" if require_https else "")
                + "; check and retry, or use Test to verify connectivity"
            ),
        )


@router.get("/models")
def list_model_options(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Flat model list for scene selector (enabled entries only, with ability bits and context windows)."""
    rows = get_provider_model_rows(db)
    return {
        "models": [
            profile_to_response(profile, provider)
            for profile, provider in rows
            if profile.enabled
        ]
    }


@router.get("/providers")
def list_providers(db: Session = Depends(get_db)) -> dict[str, Any]:
    return list_providers_payload(db)


@router.get("/vendors")
def recommended_vendors() -> dict[str, Any]:
    """Recommended (adapted) vendors tree: level 1 vendor, level 2 model type.

    Drives the settings-page "add provider" panel; entries carry catalog prefills
    plus the deep request template metadata when a vendor descriptor JSON exists.
    """
    from realmock.platform.vendors import recommended_vendors_payload

    return recommended_vendors_payload()


@router.post("/vendors/{vendor_id}/apply")
def apply_recommended_vendor(vendor_id: str, db: Session = Depends(get_db)) -> dict:
    """One-click provisioning: provider shell + one channel and default entry per adapted
    capability; Base URLs and names prefill from the vendor catalog, API Keys stay empty."""
    return apply_vendor(db, vendor_id)


@router.post("/providers")
def create_provider(body: ProviderCreate, db: Session = Depends(get_db)) -> dict:
    name = body.name.strip()
    if not name:
        raise ApiBusinessError(get_spec("A0007"), message="Provider name cannot be empty")
    if db.query(LlmProvider).filter(LlmProvider.name == name).first():
        raise ApiBusinessError(get_spec("A0007"), message=f"Provider '{name}' already exists")
    for channel in body.channels:
        _safe_base(channel.api_base, label="Base URL")
        if channel.kind not in CHANNEL_KINDS:
            raise ApiBusinessError(get_spec("A0007"), message=f"Unknown channel kind: {channel.kind}")
    _safe_base(body.website_url, label="Website URL")
    row = LlmProvider(
        name=name,
        enabled=body.enabled,
        website_url=body.website_url.strip(),
        notes=body.notes.strip(),
    )
    db.add(row)
    db.flush()
    for channel in body.channels:
        channel_row = LlmProviderChannel(
            provider_id=row.id,
            kind=channel.kind,
            vendor=channel.vendor.strip(),
            api_base=channel.api_base.strip(),
            full_url=channel.full_url,
            protocol=channel.protocol,
        )
        apply_channel_key(channel_row, channel.api_key)
        db.add(channel_row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name}


@router.put("/providers/{provider_id}")
def update_provider(provider_id: int, body: ProviderUpdate, db: Session = Depends(get_db)) -> dict:
    row = get_provider(db, provider_id)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise ApiBusinessError(get_spec("A0007"), message="Provider name cannot be empty")
        exists = db.query(LlmProvider).filter(LlmProvider.name == name, LlmProvider.id != provider_id).first()
        if exists:
            raise ApiBusinessError(get_spec("A0007"), message=f"Provider '{name}' already exists")
        row.name = name
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.website_url is not None:
        _safe_base(body.website_url, label="Website URL")
        row.website_url = body.website_url.strip()
    if body.notes is not None:
        row.notes = body.notes.strip()
    db.commit()
    return {"id": row.id, "name": row.name}


@router.put("/providers/{provider_id}/channels/{kind}")
def update_provider_channel(
    provider_id: int, kind: str, body: ChannelUpdate, db: Session = Depends(get_db)
) -> dict:
    if kind not in CHANNEL_KINDS:
        raise ApiBusinessError(get_spec("A0007"), message=f"Unknown channel kind: {kind}")
    if body.api_base is not None:
        _safe_base(body.api_base, label="Base URL")
    return upsert_channel(db, provider_id, kind, body)


@router.get("/providers/{provider_id}/channels/{kind}/catalog")
def fetch_channel_model_catalog(provider_id: int, kind: str, db: Session = Depends(get_db)) -> dict:
    """Model ids offered for this channel: vendor descriptor list or the provider's
    OpenAI-compatible /models endpoint."""
    return channel_model_catalog(db, provider_id, kind)


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: int, db: Session = Depends(get_db)) -> dict:
    """Delete the provider and everything under it: model entries, channel settings,
    and task bindings pointing at its entries (the UI asks for confirmation first)."""
    row = get_provider(db, provider_id)
    profile_ids = [
        pid
        for (pid,) in db.query(ModelProfile.id)
        .filter(ModelProfile.provider_id == provider_id)
        .all()
    ]
    if profile_ids:
        db.query(TaskBinding).filter(TaskBinding.profile_id.in_(profile_ids)).delete(
            synchronize_session=False
        )
    db.query(ModelProfile).filter(ModelProfile.provider_id == provider_id).delete(
        synchronize_session=False
    )
    db.query(LlmProviderChannel).filter(LlmProviderChannel.provider_id == provider_id).delete(
        synchronize_session=False
    )
    db.delete(row)
    db.commit()
    return {"deleted": provider_id}


@router.post("/providers/{provider_id}/models")
def create_model(provider_id: int, body: ModelProfileCreate, db: Session = Depends(get_db)) -> dict:
    provider = get_provider(db, provider_id)
    model = body.model.strip()
    if not model:
        raise ApiBusinessError(get_spec("A0007"), message="Model name cannot be empty")
    if body.kind not in CHANNEL_KINDS:
        raise ApiBusinessError(get_spec("A0007"), message=f"Unknown model type: {body.kind}")
    dup = (
        db.query(ModelProfile)
        .filter(ModelProfile.provider_id == provider_id, ModelProfile.model == model)
        .first()
    )
    if dup:
        raise ApiBusinessError(get_spec("A0007"), message=f"Model '{model}' already exists under this provider")
    row = ModelProfile(
        provider_id=provider.id,
        kind=body.kind,
        model=model,
        display_name=body.display_name.strip(),
        context_window=body.context_window,
        max_output=body.max_output,
        cap_chat=body.capabilities.chat,
        cap_vision=body.capabilities.vision,
        cap_audio_in=body.capabilities.audio_input,
        cap_audio_out=body.capabilities.audio_output,
        cap_reasoning=body.capabilities.reasoning,
        enabled=body.enabled,
    )
    row.extras = merge_profile_extras(row, body.extras)
    db.add(row)
    db.commit()
    db.refresh(row)
    return profile_to_response(row, provider)


@router.put("/models/{model_id}")
def update_model(model_id: int, body: ModelProfileUpdate, db: Session = Depends(get_db)) -> dict:
    row = get_profile(db, model_id)
    if body.model is not None:
        model = body.model.strip()
        dup = (
            db.query(ModelProfile)
            .filter(
                ModelProfile.provider_id == row.provider_id,
                ModelProfile.model == model,
                ModelProfile.id != model_id,
            )
            .first()
        )
        if dup:
            raise ApiBusinessError(get_spec("A0007"), message=f"Model '{model}' already exists under this provider")
        row.model = model
    if body.kind is not None:
        if body.kind not in CHANNEL_KINDS:
            raise ApiBusinessError(get_spec("A0007"), message=f"Unknown model type: {body.kind}")
        row.kind = body.kind
    if body.display_name is not None:
        row.display_name = body.display_name.strip()
    if body.context_window is not None:
        row.context_window = body.context_window
    if body.max_output is not None:
        row.max_output = body.max_output
    if body.capabilities is not None:
        row.cap_chat = body.capabilities.chat
        row.cap_vision = body.capabilities.vision
        row.cap_audio_in = body.capabilities.audio_input
        row.cap_audio_out = body.capabilities.audio_output
        row.cap_reasoning = body.capabilities.reasoning
    if body.enabled is not None:
        row.enabled = body.enabled
    row.extras = merge_profile_extras(row, body.extras)
    db.commit()
    db.refresh(row)
    provider = db.query(LlmProvider).filter(LlmProvider.id == row.provider_id).first()
    return profile_to_response(row, provider)


@router.delete("/models/{model_id}")
def delete_model(model_id: int, db: Session = Depends(get_db)) -> dict:
    row = get_profile(db, model_id)
    if db.query(TaskBinding).filter(TaskBinding.profile_id == model_id).count():
        raise ApiBusinessError(
            get_spec("A0007"),
            message="This model is bound to a task; change the default processor first",
        )
    db.delete(row)
    db.commit()
    return {"deleted": model_id}


@router.get("/bindings")
def get_bindings(db: Session = Depends(get_db)) -> dict[str, Any]:
    return list_bindings_payload(db)


@router.put("/bindings/{task}")
def update_binding(task: str, body: BindingUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    return update_binding_record(db, task, body)
