"""Recommended-vendor provisioning: one vendor click → provider + channels + default entries.

Also serves the per-channel model catalog ("fetch model list"): vendor descriptor lists
first, then the OpenAI-compatible ``GET /models`` endpoint for unadapted channels.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session

from realmock.platform.core.errors import ApiBusinessError, get_spec
from realmock.platform.core.secrets import decrypt_secret
from realmock.platform.models.config_models import LlmProvider, LlmProviderChannel, ModelProfile
from realmock.platform.vendors import CAPABILITIES, vendor_def, recommended_vendors_payload
from realmock.domains.settings.services.model_registry import get_provider

#: Vendor capability name → channel kind (the two vocabularies meet here).
KIND_BY_CAPABILITY = {"reasoning": "chat", "recognize": "stt", "speak": "tts"}
CAPABILITY_BY_KIND = {kind: capability for capability, kind in KIND_BY_CAPABILITY.items()}

# Capability bits stamped onto the default model entry seeded for each channel kind.
_KIND_CAPABILITY_CAPS = {
    "chat": {"cap_chat": True},
    "stt": {"cap_audio_in": True},
    "tts": {"cap_audio_out": True},
}

_LLM_PROTOCOLS = ("openai_chat", "anthropic_messages", "openai_responses")


def _apply_error(message: str) -> ApiBusinessError:
    return ApiBusinessError(get_spec("A0007"), message=message)


def _protocol_for_channel(capability_entry: dict[str, Any], kind: str) -> str:
    """Chat channels honor the vendor transport when it is a known LLM protocol; voice
    channels keep the default (their adapters route by vendor id, not protocol)."""
    if kind == "chat":
        transport = str(capability_entry.get("def", {}).get("transport") or "")
        if transport in _LLM_PROTOCOLS:
            return transport
    return "openai_chat"


def apply_vendor(db: Session, vendor_id: str) -> dict[str, Any]:
    """Create (or reuse) the provider named after ``vendor_id`` and backfill every adapted
    capability as a channel plus one default model entry. Existing channel settings and
    entries are never overwritten; API Keys stay empty for the user to fill."""
    vendor = next(
        (v for v in recommended_vendors_payload().get("vendors", []) if v.get("id") == vendor_id),
        None,
    )
    if vendor is None:
        raise _apply_error(f"Unknown recommended vendor: {vendor_id}")
    label = vendor.get("label") or vendor_id

    provider = (
        db.query(LlmProvider)
        .filter(LlmProvider.name.ilike(label))
        .first()
    )
    created_provider = provider is None
    if provider is None:
        provider = LlmProvider(name=label)
        db.add(provider)
        db.flush()

    configured_kinds: list[str] = []
    for capability in CAPABILITIES:
        entry = vendor.get("capabilities", {}).get(capability)
        if not entry:
            continue
        kind = KIND_BY_CAPABILITY[capability]
        default_api_base = entry.get("default_api_base") or ""
        default_model = entry.get("default_model") or ""
        channel = (
            db.query(LlmProviderChannel)
            .filter(
                LlmProviderChannel.provider_id == provider.id,
                LlmProviderChannel.kind == kind,
            )
            .first()
        )
        if channel is None:
            if not default_api_base:
                continue
            db.add(
                LlmProviderChannel(
                    provider_id=provider.id,
                    kind=kind,
                    vendor=vendor_id,
                    api_base=default_api_base,
                    protocol=_protocol_for_channel(entry, kind),
                )
            )
            configured_kinds.append(kind)
        elif not channel.vendor:
            # Untagged legacy channel: adopt the vendor id so deep adapters engage.
            channel.vendor = vendor_id

        if default_model:
            has_entry = (
                db.query(ModelProfile)
                .filter(ModelProfile.provider_id == provider.id, ModelProfile.kind == kind)
                .count()
                > 0
            )
            if not has_entry:
                db.add(
                    ModelProfile(provider_id=provider.id, kind=kind, model=default_model, **_KIND_CAPABILITY_CAPS[kind])
                )
    db.commit()
    return {
        "provider_id": provider.id,
        "name": provider.name,
        "created_provider": created_provider,
        "configured_kinds": configured_kinds,
    }


def _fetch_remote_models(channel: LlmProviderChannel) -> list[str]:
    """Pull the model id list from an OpenAI-compatible ``GET {api_base}/models`` endpoint."""
    api_key = channel.api_key or ""
    if api_key.startswith("enc:"):
        api_key = decrypt_secret(api_key) or ""
    url = channel.api_base.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = httpx.get(url, headers=headers, timeout=10.0)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        raise _apply_error(f"Failed to fetch the model list: {e}") from e
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise _apply_error("Model list response has an unexpected shape (expected {data: [{id}]}).")
    models = sorted(
        {str(row.get("id")) for row in rows if isinstance(row, dict) and row.get("id")}
    )
    if not models:
        raise _apply_error("The endpoint returned an empty model list.")
    return models


def channel_model_catalog(db: Session, provider_id: int, kind: str) -> dict[str, Any]:
    """Model ids offered for ``kind`` on this provider: vendor descriptor list, else the
    OpenAI-compatible /models endpoint. Raises when neither source is available."""
    if kind not in CAPABILITY_BY_KIND:
        raise _apply_error(f"Unknown channel kind: {kind}")
    provider = get_provider(db, provider_id)
    channel = (
        db.query(LlmProviderChannel)
        .filter(
            LlmProviderChannel.provider_id == provider.id,
            LlmProviderChannel.kind == kind,
        )
        .first()
    )
    if channel is None:
        raise _apply_error("This model type is not configured on the provider yet; save the channel first.")
    capability = CAPABILITY_BY_KIND[kind]
    capability_def = (vendor_def(channel.vendor) or {}).get("capabilities", {}).get(capability)
    if isinstance(capability_def, dict) and capability_def.get("models"):
        return {"source": "vendor", "models": list(capability_def["models"])}
    if channel.protocol in ("openai_chat", "openai_responses") and channel.api_base and not channel.full_url:
        return {"source": "remote", "models": _fetch_remote_models(channel)}
    raise _apply_error(
        "No model catalog source: configure an adapted vendor on the channel, or use an OpenAI-compatible Base URL."
    )
