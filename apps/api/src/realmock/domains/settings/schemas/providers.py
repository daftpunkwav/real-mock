"""Settings HTTP response schemas (model-entry system, vendors, GitHub, voice catalog).

Field-by-field mirror of the dicts returned by
``domains.settings.routes.models`` / ``integrations`` / ``stages``; the
handwritten frontend mirror lives in ``apps/web/src/lib/api/settingsHttp.ts``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ModelKind = Literal["chat", "stt", "tts"]


# ── Channels / model profiles ──────────────────────────────────────────────


class ProviderChannelResponse(BaseModel):
    """External channel view (``channel_to_response``; key masked to a boolean)."""

    kind: ModelKind
    vendor: str
    api_base: str
    full_url: bool
    protocol: str
    has_api_key: bool


class ModelCapabilitiesResponse(BaseModel):
    chat: bool
    vision: bool
    audio_input: bool
    audio_output: bool
    reasoning: bool


class ModelProfileResponse(BaseModel):
    """External view of one model entry (``profile_to_response``; no secret keys)."""

    id: int
    provider_id: int
    provider_name: str
    kind: ModelKind
    model: str
    display_name: str
    label: str
    context_window: int
    max_output: int
    capabilities: ModelCapabilitiesResponse
    extras: dict[str, Any]
    enabled: bool


class ProviderWithModelsResponse(BaseModel):
    id: int
    name: str
    enabled: bool
    website_url: str
    notes: str
    channels: list[ProviderChannelResponse]
    models: list[ModelProfileResponse]


class ProviderListResponse(BaseModel):
    providers: list[ProviderWithModelsResponse]


class ModelOptionsResponse(BaseModel):
    """Flat model list for the scene selector (enabled entries only)."""

    models: list[ModelProfileResponse]


class ProviderNameResponse(BaseModel):
    """Create/update provider result."""

    id: int
    name: str


class SettingsDeleteResponse(BaseModel):
    """Delete result for providers and model entries."""

    deleted: int


class ChannelModelCatalogResponse(BaseModel):
    """Model ids offered for one channel (vendor descriptor or /models endpoint)."""

    source: Literal["vendor", "remote"]
    models: list[str]


# ── Task bindings ──────────────────────────────────────────────────────────


class BindingFallback(BaseModel):
    handler: str
    mode: str


class TaskBindingView(BaseModel):
    task: ModelKind
    profile: ModelProfileResponse | None
    fallback: BindingFallback


class BindingsResponse(BaseModel):
    """Task → default handler map (keys fixed by ``STAGE_BY_TASK``)."""

    chat: TaskBindingView
    stt: TaskBindingView
    tts: TaskBindingView


# ── Recommended vendors ────────────────────────────────────────────────────


class VendorCapabilityDef(BaseModel):
    """Deep request template metadata from the vendor descriptor JSON."""

    transport: str
    models: list[str]
    request: dict[str, Any]
    notes: str


class RecommendedVendorCapability(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider_id: str
    label: str
    catalog_label: str
    default_model: str
    default_api_base: str
    hint: str
    adapted: bool
    # ``def`` is a Python keyword, so the field is named ``def_`` and serialized by alias.
    def_: VendorCapabilityDef | None = Field(default=None, alias="def")


class RecommendedVendorResponse(BaseModel):
    """Level 1 of the recommended-vendor cascade (capabilities keyed by model type)."""

    id: str
    label: str
    docs: dict[str, str]
    capabilities: dict[str, RecommendedVendorCapability]


class RecommendedVendorsResponse(BaseModel):
    vendors: list[RecommendedVendorResponse]


class VendorApplyResponse(BaseModel):
    """One-click provisioning result."""

    provider_id: int
    name: str
    created_provider: bool
    configured_kinds: list[ModelKind]


# ── GitHub integration ─────────────────────────────────────────────────────


class GithubStatusResponse(BaseModel):
    """Link status: configured flag plus tail mask, never the secret."""

    configured: bool
    tail: str


class GithubTestResponse(BaseModel):
    """Rate-limit probe result (success carries quota, failure carries a message)."""

    ok: bool
    message: str | None = None
    status: int | None = None
    limit: int | None = None
    remaining: int | None = None
    reset_in: int | None = None
    authenticated: bool | None = None


# ── Voice / reasoning catalog ──────────────────────────────────────────────


class VoiceProviderOptionResponse(BaseModel):
    """One catalog provider row (``catalog_schema._p`` shape)."""

    id: str
    label: str
    can_speech_recognize: bool
    can_interview_reason: bool
    can_speech_speak: bool
    recognize_via: Literal["native_audio", "transcribe_only", "none"]
    speak_via: Literal["native_audio", "tts_from_text", "none"]
    status: Literal["ready", "coming_soon"]
    default_model: str
    default_api_base: str
    hint: str
    vendor: str


class VoiceCatalogResponse(BaseModel):
    """Three-stage supplier capability catalog (``GET /settings/catalog``)."""

    reasoning: list[VoiceProviderOptionResponse]
    recognize: list[VoiceProviderOptionResponse]
    speak: list[VoiceProviderOptionResponse]


__all__ = [
    "BindingFallback",
    "BindingsResponse",
    "ChannelModelCatalogResponse",
    "GithubStatusResponse",
    "GithubTestResponse",
    "ModelCapabilitiesResponse",
    "ModelKind",
    "ModelOptionsResponse",
    "ModelProfileResponse",
    "ProviderChannelResponse",
    "ProviderListResponse",
    "ProviderNameResponse",
    "ProviderWithModelsResponse",
    "RecommendedVendorCapability",
    "RecommendedVendorResponse",
    "RecommendedVendorsResponse",
    "SettingsDeleteResponse",
    "TaskBindingView",
    "VendorApplyResponse",
    "VendorCapabilityDef",
    "VoiceCatalogResponse",
    "VoiceProviderOptionResponse",
]
