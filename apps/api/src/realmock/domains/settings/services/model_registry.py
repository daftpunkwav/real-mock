"""Model entry system (capability-based declarations): request models and read/write services for providers / models / task bindings.

Extracted from the routing layer, which now retains only endpoint assembly and validation;
this module contains Pydantic request bodies and DB reads/writes and can be unit-tested independently.
"""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from realmock.platform.models.config_models import LlmProvider, LlmProviderChannel, ModelProfile, TaskBinding
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
    ensure_provider_channels,
    parse_json,
    migrate_stages_to_profiles,
    profile_to_response,
)

#: Channel kinds mirroring the task vocabulary; every provider owns at most one channel per kind.
CHANNEL_KINDS = ("chat", "stt", "tts")

# Capability convention keys stored inside ModelProfile.extras (no dedicated columns):
# - extras["reasoning"] = {"variants": [...], "defaultVariant": "..."} (enabled = cap_reasoning column)
# - extras["modalities"] = {"input": [...], "output": [...]}
_MODALITY_IN_VALUES = ("text", "image", "audio", "video", "pdf")
_MODALITY_OUT_VALUES = ("text", "audio")
_REASONING_VARIANTS_MAX = 8
_MODALITY_TOKEN_MAX = 32


def _valid_kind(kind: str) -> bool:
    return kind in CHANNEL_KINDS


class ChannelWrite(BaseModel):
    """Per-kind connection settings attached to a provider (create or upsert)."""

    kind: str = Field(..., min_length=1, max_length=10)
    vendor: str = Field(default="", max_length=50)
    api_base: str = Field(default="", max_length=500)
    full_url: bool = False
    protocol: str = DEFAULT_LLM_PROTOCOL
    api_key: str = ""


class ChannelUpdate(BaseModel):
    """Partial channel update; ``None`` fields keep their current value."""

    vendor: str | None = Field(default=None, max_length=50)
    api_base: str | None = Field(default=None, max_length=500)
    full_url: bool | None = None
    protocol: str | None = None
    api_key: str | None = None


class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    enabled: bool = True
    website_url: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=2000)
    channels: list[ChannelWrite] = Field(default_factory=list)


class ProviderUpdate(BaseModel):
    """Partial provider update; ``None`` fields keep their current value."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    website_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


class ModelCapabilitiesIn(BaseModel):
    chat: bool = False
    vision: bool = False
    audio_input: bool = False
    audio_output: bool = False
    reasoning: bool = False


class ModelProfileCreate(BaseModel):
    model: str = Field(..., min_length=1, max_length=200)
    kind: str = "chat"
    display_name: str = Field(default="", max_length=200)
    context_window: int = Field(default=DEFAULT_CONTEXT_WINDOW, ge=0)
    max_output: int = Field(default=DEFAULT_MAX_OUTPUT_TOKENS, ge=1)
    capabilities: ModelCapabilitiesIn = ModelCapabilitiesIn(chat=True)
    extras: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ModelProfileUpdate(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=200)
    kind: str | None = Field(default=None, min_length=1, max_length=10)
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


def get_channel(db: Session, provider_id: int, kind: str) -> LlmProviderChannel | None:
    return (
        db.query(LlmProviderChannel)
        .filter(LlmProviderChannel.provider_id == provider_id, LlmProviderChannel.kind == kind)
        .first()
    )


def apply_channel_key(channel: LlmProviderChannel, raw_key: str | None) -> None:
    if raw_key is None or raw_key == SECRET_KEEP:
        return
    # encrypt_secret only yields None for falsy input, excluded by the guard.
    channel.api_key = cast("str", encrypt_secret(raw_key)) if raw_key else ""


def channel_to_response(channel: LlmProviderChannel) -> dict[str, Any]:
    """External channel view (key masked to a boolean)."""
    return {
        "kind": channel.kind,
        "vendor": channel.vendor or "",
        "api_base": channel.api_base or "",
        "full_url": bool(channel.full_url),
        "protocol": channel.protocol or DEFAULT_LLM_PROTOCOL,
        "has_api_key": bool(channel.api_key),
    }


def _norm_token_list(
    value: Any, *, allowed: tuple[str, ...] | None = None, limit: int
) -> list[str]:
    """Coerce a JSON value into a normalized token list; unusable items are dropped.

    ``allowed=None`` accepts any token (free-form vocabularies such as reasoning
    variants); otherwise tokens outside ``allowed`` are dropped.
    """
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[: limit * 2]:
        token = str(item or "").strip().lower()[:_MODALITY_TOKEN_MAX]
        if not token or token in out or (allowed is not None and token not in allowed):
            continue
        out.append(token)
        if len(out) >= limit:
            break
    return out


def _normalize_capability_extras(extras: dict[str, Any]) -> dict[str, Any]:
    """Coerce the capability convention keys (``reasoning`` / ``modalities``) in place.

    The model form owns validation; this is the defensive backstop so malformed
    client payloads never enter storage. An empty/invalid convention key is removed
    rather than kept half-formed.
    """
    if "reasoning" in extras:
        reasoning = extras.get("reasoning")
        cleaned: dict[str, Any] = {}
        if isinstance(reasoning, dict):
            variants = _norm_token_list(reasoning.get("variants"), limit=_REASONING_VARIANTS_MAX)
            default = str(reasoning.get("defaultVariant") or "").strip().lower()
            if variants:
                cleaned["variants"] = variants
            if default and default in variants:
                cleaned["defaultVariant"] = default
        if cleaned:
            extras["reasoning"] = cleaned
        else:
            extras.pop("reasoning", None)

    if "modalities" in extras:
        modalities = extras.get("modalities")
        cleaned = {}
        if isinstance(modalities, dict):
            modal_in = _norm_token_list(modalities.get("input"), allowed=_MODALITY_IN_VALUES, limit=8)
            modal_out = _norm_token_list(modalities.get("output"), allowed=_MODALITY_OUT_VALUES, limit=4)
            if modal_in:
                cleaned["input"] = modal_in
            if modal_out:
                cleaned["output"] = modal_out
        if cleaned:
            extras["modalities"] = cleaned
        else:
            extras.pop("modalities", None)
    return extras


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
    merged = _normalize_capability_extras(merged)
    return json.dumps(merged, ensure_ascii=False)


def list_providers_payload(db: Session) -> dict[str, Any]:
    ensure_provider_channels(db)
    providers = db.query(LlmProvider).order_by(LlmProvider.id).all()
    items = []
    for provider in providers:
        models = (
            db.query(ModelProfile)
            .filter(ModelProfile.provider_id == provider.id)
            .order_by(ModelProfile.id)
            .all()
        )
        channels = (
            db.query(LlmProviderChannel)
            .filter(LlmProviderChannel.provider_id == provider.id)
            .order_by(LlmProviderChannel.id)
            .all()
        )
        items.append(
            {
                "id": provider.id,
                "name": provider.name,
                "enabled": bool(provider.enabled),
                "website_url": provider.website_url or "",
                "notes": provider.notes or "",
                "channels": [channel_to_response(c) for c in channels],
                "models": [profile_to_response(m, provider) for m in models],
            }
        )
    return {"providers": items}


def upsert_channel(db: Session, provider_id: int, kind: str, body: ChannelUpdate) -> dict[str, Any]:
    """Create or partially update one provider channel; unknown kind is rejected."""
    if not _valid_kind(kind):
        raise ApiBusinessError(get_spec("A0007"), message=f"Unknown channel kind: {kind}")
    provider = get_provider(db, provider_id)
    channel = get_channel(db, provider.id, kind)
    if channel is None:
        channel = LlmProviderChannel(provider_id=provider.id, kind=kind)
        db.add(channel)
    if body.vendor is not None:
        channel.vendor = body.vendor.strip()
    if body.api_base is not None:
        channel.api_base = body.api_base.strip()
    if body.full_url is not None:
        channel.full_url = body.full_url
    if body.protocol is not None:
        channel.protocol = body.protocol
    apply_channel_key(channel, body.api_key)
    db.commit()
    db.refresh(channel)
    return channel_to_response(channel)


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
