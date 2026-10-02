"""Model entry system (capability-based declarations): request models and read/write services for providers / models / task bindings.

The routing layer retains only endpoint assembly and validation;
this module contains Pydantic request bodies and DB reads/writes and can be unit-tested independently.
"""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from realmock.domains.settings.services.validation import safe_base
from realmock.platform.capabilities.ai.llm.defaults import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MAX_OUTPUT_TOKENS,
)
from realmock.platform.core.constants import DEFAULT_LLM_PROTOCOL
from realmock.platform.core.errors import ApiBusinessError, get_spec, raise_error
from realmock.platform.core.secrets import encrypt_secret
from realmock.platform.models.config_models import (
    LlmProvider,
    LlmProviderChannel,
    ModelProfile,
    TaskBinding,
)
from realmock.platform.services.pipeline.config import (
    DEFAULT_FALLBACK,
    SECRET_EXTRA_KEYS,
    SECRET_KEEP,
    STAGE_BY_TASK,
    ensure_provider_channels,
    migrate_stages_to_profiles,
    parse_json,
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


# Per-kind connection settings attached to a provider (create or upsert).
class ChannelWrite(BaseModel):
    kind: str = Field(..., min_length=1, max_length=10)
    vendor: str = Field(default="", max_length=50)
    api_base: str = Field(default="", max_length=500)
    full_url: bool = False
    protocol: str = DEFAULT_LLM_PROTOCOL
    api_key: str = ""


# Partial channel update; ``None`` fields keep their current value.
class ChannelUpdate(BaseModel):
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


# Partial provider update; ``None`` fields keep their current value.
class ProviderUpdate(BaseModel):
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
            modal_in = _norm_token_list(
                modalities.get("input"), allowed=_MODALITY_IN_VALUES, limit=8
            )
            modal_out = _norm_token_list(
                modalities.get("output"), allowed=_MODALITY_OUT_VALUES, limit=4
            )
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
        raise ApiBusinessError(get_spec("A0001"), message=f"Unknown channel kind: {kind}")
    if body.api_base is not None:
        safe_base(body.api_base, label="Base URL")
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


def create_provider(db: Session, body: ProviderCreate) -> dict[str, Any]:
    """Validate and persist a new provider with its channels."""
    name = body.name.strip()
    if not name:
        raise ApiBusinessError(get_spec("A0001"), message="Provider name cannot be empty")
    if db.query(LlmProvider).filter(LlmProvider.name == name).first():
        raise ApiBusinessError(get_spec("A0001"), message=f"Provider '{name}' already exists")
    for channel in body.channels:
        safe_base(channel.api_base, label="Base URL")
        if channel.kind not in CHANNEL_KINDS:
            raise ApiBusinessError(
                get_spec("A0001"), message=f"Unknown channel kind: {channel.kind}"
            )
    safe_base(body.website_url, label="Website URL")
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


def update_provider(db: Session, provider_id: int, body: ProviderUpdate) -> dict[str, Any]:
    """Partially update a provider; ``None`` fields keep their current value."""
    row = get_provider(db, provider_id)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise ApiBusinessError(get_spec("A0001"), message="Provider name cannot be empty")
        exists = (
            db.query(LlmProvider)
            .filter(LlmProvider.name == name, LlmProvider.id != provider_id)
            .first()
        )
        if exists:
            raise ApiBusinessError(get_spec("A0001"), message=f"Provider '{name}' already exists")
        row.name = name
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.website_url is not None:
        safe_base(body.website_url, label="Website URL")
        row.website_url = body.website_url.strip()
    if body.notes is not None:
        row.notes = body.notes.strip()
    db.commit()
    return {"id": row.id, "name": row.name}


def delete_provider(db: Session, provider_id: int) -> dict[str, Any]:
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


def create_model(db: Session, provider_id: int, body: ModelProfileCreate) -> dict[str, Any]:
    """Validate and persist one model entry under a provider."""
    provider = get_provider(db, provider_id)
    model = body.model.strip()
    if not model:
        raise ApiBusinessError(get_spec("A0001"), message="Model name cannot be empty")
    if body.kind not in CHANNEL_KINDS:
        raise ApiBusinessError(get_spec("A0001"), message=f"Unknown model type: {body.kind}")
    dup = (
        db.query(ModelProfile)
        .filter(ModelProfile.provider_id == provider_id, ModelProfile.model == model)
        .first()
    )
    if dup:
        raise ApiBusinessError(
            get_spec("A0001"), message=f"Model '{model}' already exists under this provider"
        )
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


def update_model(db: Session, model_id: int, body: ModelProfileUpdate) -> dict[str, Any]:
    """Partially update one model entry; ``None`` fields keep their current value."""
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
            raise ApiBusinessError(
                get_spec("A0001"), message=f"Model '{model}' already exists under this provider"
            )
        row.model = model
    if body.kind is not None:
        if body.kind not in CHANNEL_KINDS:
            raise ApiBusinessError(get_spec("A0001"), message=f"Unknown model type: {body.kind}")
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


def delete_model(db: Session, model_id: int) -> dict[str, Any]:
    """Delete one model entry unless a task binding still points at it."""
    row = get_profile(db, model_id)
    if db.query(TaskBinding).filter(TaskBinding.profile_id == model_id).count():
        raise ApiBusinessError(
            get_spec("A0001"),
            message="This model is bound to a task; change the default processor first",
        )
    db.delete(row)
    db.commit()
    return {"deleted": model_id}


def list_bindings_payload(db: Session) -> dict[str, Any]:
    migrate_stages_to_profiles(db)
    # One batched query per table instead of 3 queries per task, then join in
    # memory: same rows as the per-task lookups, ~3 queries total.
    bindings = {
        b.task: b for b in db.query(TaskBinding).filter(TaskBinding.task.in_(STAGE_BY_TASK)).all()
    }
    profiles: dict[int, ModelProfile] = {}
    if bindings:
        profile_rows = (
            db.query(ModelProfile)
            .filter(ModelProfile.id.in_([b.profile_id for b in bindings.values()]))
            .all()
        )
        profiles = {p.id: p for p in profile_rows}
    provider_ids = {p.provider_id for p in profiles.values()}
    providers: dict[int, LlmProvider] = {}
    if provider_ids:
        provider_rows = db.query(LlmProvider).filter(LlmProvider.id.in_(provider_ids)).all()
        providers = {pr.id: pr for pr in provider_rows}
    out: dict[str, Any] = {}
    for task, stage in STAGE_BY_TASK.items():
        binding = bindings.get(task)
        profile = profiles.get(binding.profile_id) if binding else None
        provider = providers.get(profile.provider_id) if profile else None
        out[task] = {
            "task": task,
            "profile": profile_to_response(profile, provider) if profile else None,
            "fallback": {
                "handler": (binding.fallback_handler if binding else "")
                or DEFAULT_FALLBACK[task]["handler"],
                "mode": (binding.fallback_mode if binding else "")
                or DEFAULT_FALLBACK[task]["mode"],
            },
        }
    return out


def update_binding_record(db: Session, task: str, body: BindingUpdate) -> dict[str, Any]:
    if task not in STAGE_BY_TASK:
        raise ApiBusinessError(get_spec("A0001"), message=f"Unknown task: {task}")
    profile = get_profile(db, body.profile_id)
    caps_map = {"chat": "cap_chat", "stt": "cap_audio_in", "tts": "cap_audio_out"}
    if not getattr(profile, caps_map[task]):
        raise ApiBusinessError(
            get_spec("A0001"),
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
