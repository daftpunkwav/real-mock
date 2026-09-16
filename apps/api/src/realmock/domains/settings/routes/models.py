"""Model-profile API (capability declarations): provider / model / task-binding routes.

Request bodies and DB access live in ``realmock.domains.settings.services.model_registry``;
this file only assembles routes. Mounted under the ``/settings`` prefix alongside the three-stage
configuration routes (``realmock.domains.settings.routes``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from realmock.platform.models.config_models import LlmProvider, ModelProfile, TaskBinding
from realmock.platform.core.constants import DEFAULT_LLM_PROTOCOL
from realmock.platform.core.errors import ApiBusinessError, get_spec
from realmock.platform.database import get_db
from realmock.platform.services.pipeline.config import (
    get_provider_model_rows,
    profile_to_response,
)
from realmock.domains.settings.services.model_registry import (
    BindingUpdate,
    ModelProfileCreate,
    ModelProfileUpdate,
    ProviderCreate,
    ProviderUpdate,
    apply_provider_key,
    get_profile,
    get_provider,
    list_bindings_payload,
    list_providers_payload,
    merge_profile_extras,
    update_binding_record,
)

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

    Drives the settings-page "add provider" cascade; entries carry catalog prefills
    plus the deep request template metadata when a vendor descriptor JSON exists.
    """
    from realmock.platform.vendors import recommended_vendors_payload

    return recommended_vendors_payload()


@router.post("/providers")
def create_provider(body: ProviderCreate, db: Session = Depends(get_db)) -> dict:
    name = body.name.strip()
    if not name:
        raise ApiBusinessError(get_spec("A0007"), message="Provider name cannot be empty")
    if db.query(LlmProvider).filter(LlmProvider.name == name).first():
        raise ApiBusinessError(get_spec("A0007"), message=f"Provider '{name}' already exists")
    _safe_base(body.api_base, label="Base URL")
    row = LlmProvider(
        name=name,
        api_base=body.api_base.strip(),
        full_url=bool(body.full_url),
        protocol=body.protocol or DEFAULT_LLM_PROTOCOL,
        enabled=body.enabled,
    )
    apply_provider_key(row, body.api_key or "")
    db.add(row)
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
    if body.api_base is not None:
        _safe_base(body.api_base, label="Base URL")
        row.api_base = body.api_base.strip()
    if body.full_url is not None:
        row.full_url = body.full_url
    if body.protocol is not None:
        row.protocol = body.protocol
    if body.enabled is not None:
        row.enabled = body.enabled
    apply_provider_key(row, body.api_key)
    db.commit()
    return {"id": row.id, "name": row.name}


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: int, db: Session = Depends(get_db)) -> dict:
    row = get_provider(db, provider_id)
    if db.query(ModelProfile).filter(ModelProfile.provider_id == provider_id).count():
        raise ApiBusinessError(get_spec("A0007"), message="Delete all model entries under this provider first")
    db.delete(row)
    db.commit()
    return {"deleted": provider_id}


@router.post("/providers/{provider_id}/models")
def create_model(provider_id: int, body: ModelProfileCreate, db: Session = Depends(get_db)) -> dict:
    provider = get_provider(db, provider_id)
    model = body.model.strip()
    if not model:
        raise ApiBusinessError(get_spec("A0007"), message="Model name cannot be empty")
    dup = (
        db.query(ModelProfile)
        .filter(ModelProfile.provider_id == provider_id, ModelProfile.model == model)
        .first()
    )
    if dup:
        raise ApiBusinessError(get_spec("A0007"), message=f"Model '{model}' already exists under this provider")
    row = ModelProfile(
        provider_id=provider.id,
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
def update_binding(task: str, body: BindingUpdate, db: Session = Depends(get_db)) -> dict:
    return update_binding_record(db, task, body)
