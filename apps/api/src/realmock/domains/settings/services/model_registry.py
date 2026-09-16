"""Model entry system (capability-based declarations): request models and read/write services for providers / models / task bindings.

Extracted from the routing layer, which now retains only endpoint assembly and validation;
this module contains Pydantic request bodies and DB reads/writes and can be unit-tested independently.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from realmock.platform.models.config_models import LlmProvider, ModelProfile, TaskBinding
from realmock.platform.core.constants import DEFAULT_LLM_PROTOCOL
from realmock.platform.capabilities.ai.llm.defaults import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MAX_OUTPUT_TOKENS,
)
from realmock.platform.core.errors import ApiBusinessError, get_spec, raise_error
from realmock.platform.core.secrets import encrypt_secret
from realmock.platform.services.pipeline.config import (
    DEFAULT_FALLBACK,
    SECRET_EXTRA_KEYS,
    SECRET_KEEP,
    STAGE_BY_TASK,
    parse_json,
    migrate_stages_to_profiles,
    profile_to_response,
)


class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    api_base: str = ""
    full_url: bool = False
    protocol: str = DEFAULT_LLM_PROTOCOL
    api_key: str = ""
    enabled: bool = True


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    api_base: str | None = None
    full_url: bool | None = None
    protocol: str | None = None
    api_key: str | None = None
    enabled: bool | None = None


class ModelCapabilitiesIn(BaseModel):
    chat: bool = False
    vision: bool = False
    audio_input: bool = False
    audio_output: bool = False
    reasoning: bool = False


class ModelProfileCreate(BaseModel):
    model: str = Field(..., min_length=1, max_length=200)
    display_name: str = Field(default="", max_length=200)
    context_window: int = Field(default=DEFAULT_CONTEXT_WINDOW, ge=0)
    max_output: int = Field(default=DEFAULT_MAX_OUTPUT_TOKENS, ge=1)
    capabilities: ModelCapabilitiesIn = ModelCapabilitiesIn(chat=True)
    extras: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ModelProfileUpdate(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    context_window: int | None = Field(default=None, ge=0)
    max_output: int | None = Field(default=None, ge=1)
    capabilities: ModelCapabilitiesIn | None = None
    extras: dict[str, Any] | None = None
    enabled: bool | None = None


class BindingUpdate(BaseModel):
    profile_id: int
    fallback_handler: str | None = ""
    fallback_mode: str | None = ""


def get_provider(db: Session, provider_id: int) -> LlmProvider:
    row = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
    if not row:
        raise_error("A4005")
    return row


def get_profile(db: Session, model_id: int) -> ModelProfile:
    row = db.query(ModelProfile).filter(ModelProfile.id == model_id).first()
    if not row:
        raise_error("A4005")
    return row


def apply_provider_key(row: LlmProvider, raw_key: str | None) -> None:
    if raw_key is None or raw_key == SECRET_KEEP:
        return
    row.api_key = encrypt_secret(raw_key) if raw_key else ""


def merge_profile_extras(row: ModelProfile, extras: dict[str, Any] | None) -> str:
    current = parse_json(row.extras)
    if extras is None:
        return row.extras or "{}"
    merged = dict(current)
    for key, value in extras.items():
        if key in SECRET_EXTRA_KEYS and value in (None, "", SECRET_KEEP):
            continue
        merged[key] = value
    for key in SECRET_EXTRA_KEYS:
        value = merged.get(key)
        if value and not str(value).startswith("enc:"):
            merged[key] = encrypt_secret(str(value)) or ""
    return json.dumps(merged, ensure_ascii=False)


def list_providers_payload(db: Session) -> dict[str, Any]:
    providers = db.query(LlmProvider).order_by(LlmProvider.id).all()
    items = []
    for provider in providers:
        models = (
            db.query(ModelProfile)
            .filter(ModelProfile.provider_id == provider.id)
            .order_by(ModelProfile.id)
            .all()
        )
        items.append(
            {
                "id": provider.id,
                "name": provider.name,
                "api_base": provider.api_base or "",
                "full_url": bool(provider.full_url),
                "protocol": provider.protocol or DEFAULT_LLM_PROTOCOL,
                "enabled": bool(provider.enabled),
                "has_api_key": bool(provider.api_key),
                "models": [profile_to_response(m, provider) for m in models],
            }
        )
    return {"providers": items}


def list_bindings_payload(db: Session) -> dict[str, Any]:
    migrate_stages_to_profiles(db)
    out: dict[str, Any] = {}
    for task, stage in STAGE_BY_TASK.items():
        binding = db.query(TaskBinding).filter(TaskBinding.task == task).first()
        profile = (
            db.query(ModelProfile).filter(ModelProfile.id == binding.profile_id).first()
            if binding
            else None
        )
        provider = (
            db.query(LlmProvider).filter(LlmProvider.id == profile.provider_id).first()
            if profile
            else None
        )
        out[task] = {
            "task": task,
            "profile": profile_to_response(profile, provider) if profile else None,
            "fallback": {
                "handler": (binding.fallback_handler if binding else "") or DEFAULT_FALLBACK[task]["handler"],
                "mode": (binding.fallback_mode if binding else "") or DEFAULT_FALLBACK[task]["mode"],
            },
        }
    return out


def update_binding_record(db: Session, task: str, body: BindingUpdate) -> dict[str, Any]:
    if task not in STAGE_BY_TASK:
        raise ApiBusinessError(get_spec("A0007"), message=f"Unknown task: {task}")
    profile = get_profile(db, body.profile_id)
    caps_map = {"chat": "cap_chat", "stt": "cap_audio_in", "tts": "cap_audio_out"}
    if not getattr(profile, caps_map[task]):
        raise ApiBusinessError(
            get_spec("A0007"),
            message="Selected model entry does not declare the capability required for this task",
        )
    binding = db.query(TaskBinding).filter(TaskBinding.task == task).first()
    if binding is None:
        binding = TaskBinding(task=task, profile_id=body.profile_id)
        db.add(binding)
    binding.profile_id = body.profile_id
    if body.fallback_handler is not None:
        binding.fallback_handler = body.fallback_handler
    if body.fallback_mode is not None:
        binding.fallback_mode = body.fallback_mode
    db.commit()
    return list_bindings_payload(db)
