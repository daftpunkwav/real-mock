"""Runtime assembly for the model-entry system: bindings / providers → flat runtime dict.

- ``_runtime_config_from_profile``: entry → flat dict matching the legacy stage runtime dict;
- ``_binding_config``: assemble by task binding; ``_legacy_stage_config``: fallback for the legacy path;
- ``profile_to_response`` / ``get_provider_model_rows``: external views of model entries.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from realmock.platform.models.config_models import LlmProvider, ModelProfile, TaskBinding
from realmock.platform.capabilities.ai.llm.defaults import (
    resolve_context_window,
    resolve_max_output_tokens,
)
from realmock.platform.core.constants import DEFAULT_LLM_PROTOCOL
from realmock.platform.core.secrets import decrypt_secret
from realmock.platform.models import StageConfig
from realmock.platform.services.pipeline.legacy import get_llm_settings_row, migrate_legacy_to_stages
from realmock.platform.services.pipeline.migration import TASK_BY_STAGE, DEFAULT_FALLBACK
from realmock.platform.services.pipeline.secrets import _dec, parse_json, public_extras, runtime_extras
from realmock.platform.services.pipeline.stages import load_stage_configs, stage_to_response


def _profile_extras(profile: ModelProfile) -> dict[str, Any]:
    return runtime_extras(parse_json(profile.extras))


def profile_to_response(profile: ModelProfile, provider: LlmProvider | None) -> dict[str, Any]:
    """External view of model entries (keys are not leaked; extras eliminates sensitive keys)."""
    return {
        "id": profile.id,
        "provider_id": profile.provider_id,
        "provider_name": (provider.name if provider else "") or "",
        "model": profile.model,
        "display_name": profile.display_name or "",
        "label": profile.display_name or profile.model,
        "context_window": profile.context_window,
        "max_output": profile.max_output,
        "capabilities": {
            "chat": bool(profile.cap_chat),
            "vision": bool(profile.cap_vision),
            "audio_input": bool(profile.cap_audio_in),
            "audio_output": bool(profile.cap_audio_out),
            "reasoning": bool(profile.cap_reasoning),
        },
        "extras": public_extras(_profile_extras(profile)),
        "enabled": bool(profile.enabled),
    }


def get_provider_model_rows(db: Session) -> list[tuple[ModelProfile, LlmProvider | None]]:
    profiles = db.query(ModelProfile).order_by(ModelProfile.provider_id, ModelProfile.id).all()
    providers = {p.id: p for p in db.query(LlmProvider).all()}
    return [(profile, providers.get(profile.provider_id)) for profile in profiles]


def _runtime_config_from_profile(
    profile: ModelProfile,
    provider: LlmProvider | None,
    stage: str,
    fallback: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble vendor + model entries into a flat dict isomorphic to the old stage runtime dict."""
    extras = _profile_extras(profile)
    fb = fallback or DEFAULT_FALLBACK.get(TASK_BY_STAGE.get(stage, "chat"), {})
    api_key = ""
    if provider is not None:
        raw = provider.api_key or ""
        if raw.startswith("enc:"):
            try:
                api_key = decrypt_secret(raw) or ""
            except Exception as e:
                raise ValueError(f"supplier {provider.name} API Key decryption failed, please go to the settings page to save again.") from e
        else:
            api_key = raw
    return {
        "stage": stage,
        "profile_id": profile.id,
        "provider": (provider.name if provider else "") or "",
        "api_base": (provider.api_base if provider else "") or "",
        "api_key": api_key,
        "protocol": (provider.protocol if provider else "") or DEFAULT_LLM_PROTOCOL,
        "model": profile.model or "",
        "max_tokens": resolve_max_output_tokens(profile.max_output),
        "context_window": resolve_context_window(profile.context_window),
        "supports_vision": bool(profile.cap_vision),
        "supports_audio_input": bool(profile.cap_audio_in),
        "supports_audio_output": bool(profile.cap_audio_out),
        "supports_video_input": False,
        # Each entry declares this explicitly under capability-based configuration; the legacy stage_configs fallback path is always False (consistent with current behavior and sends no thinking parameters)
        "reasoning_capable": bool(profile.cap_reasoning),
        "fallback_handler": fb.get("handler", ""),
        "fallback_mode": fb.get("mode", ""),
        "extras": extras,
    }


def _binding_config(db: Session, task: str, stage: str) -> dict[str, Any] | None:
    """Assemble runtime dict according to task binding; return None if the system is not enabled (no binding)."""
    binding = db.query(TaskBinding).filter(TaskBinding.task == task).first()
    if binding is None:
        return None
    profile = db.query(ModelProfile).filter(ModelProfile.id == binding.profile_id).first()
    if profile is None:
        return None
    provider = db.query(LlmProvider).filter(LlmProvider.id == profile.provider_id).first()
    return _runtime_config_from_profile(
        profile,
        provider,
        stage,
        fallback={"handler": binding.fallback_handler or "", "mode": binding.fallback_mode or ""},
    )


def _legacy_stage_config(db: Session, stage: str) -> dict[str, Any]:
    # Read path: read-only loading, missing lines are filled in by default in memory, and will not be dropped implicitly.
    rows = load_stage_configs(db)
    if get_llm_settings_row(db) and any(
        not row.provider and not row.api_base and not row.model and not row.api_key
        for row in rows.values()
    ):
        rows = migrate_legacy_to_stages(db)
    row = rows.get(stage)
    if not row:
        return stage_to_response(StageConfig(stage=stage))
    extras = runtime_extras(parse_json(row.extras))
    # In-memory fill-in instances never flush, so column defaults do not apply.
    # Resolve missing/zero values through the shared token-budget helpers.
    max_tokens = resolve_max_output_tokens(row.max_tokens)
    context_window = resolve_context_window(row.context_window)
    return {
        "provider": row.provider or extras.get("provider") or "",
        "api_base": row.api_base or "",
        "api_key": _dec(row, "api_key"),
        "protocol": row.protocol or DEFAULT_LLM_PROTOCOL,
        "model": row.model or "",
        "max_tokens": max_tokens,
        "context_window": context_window,
        "supports_vision": bool(row.supports_vision),
        "supports_audio_input": bool(row.supports_audio_input),
        "supports_audio_output": bool(row.supports_audio_output),
        "supports_video_input": bool(row.supports_video_input),
        "fallback_handler": row.fallback_handler or "",
        "fallback_mode": row.fallback_mode or "",
        "extras": extras,
        "reasoning_capable": False,
    }
