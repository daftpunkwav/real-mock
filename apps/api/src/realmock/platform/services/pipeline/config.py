"""Pipeline configuration orchestration entry point: StageConfig write path, migration trigger, and runtime resolution.

Public symbols remain importable from this module (tests and downstream code rely on this path); actual responsibilities
stay in orchestration functions in this file, while mechanical assembly is split into grouped modules in the same directory:

- ``secrets.py``: Key and extras JSON helpers
- ``stages.py``: persistence and views for the ``stage_configs`` table
- ``legacy.py``: legacy LLMSettings → stage conversion
- ``migration.py``: stage → provider + model entry + task binding (including ``allocate_provider_name``)
- ``resolve.py``: runtime assembly and binding for the model-entry system

Runtime configuration priority: ``model_profiles`` system (task_bindings → provider+model entry)
> legacy ``stage_configs`` > legacy ``llm_settings``. On first use, stage_configs are imported once
into the model-entry system; the stage_configs table is retained for rollback safety, but runtime no longer reads it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from realmock.platform.models.config_models import LlmProvider, ModelProfile
from realmock.platform.core.constants import DEFAULT_LLM_PROTOCOL
from realmock.platform.core.secrets import encrypt_secret
from realmock.platform.models import StageConfig
from realmock.platform.services.pipeline.legacy import get_llm_settings_row, migrate_legacy_to_stages
from realmock.platform.services.pipeline.migration import (
    STAGE_BY_TASK,
    TASK_BY_STAGE,
    DEFAULT_FALLBACK,
    allocate_provider_name,
    drop_legacy_provider_columns,
    ensure_provider_channels,
    migrate_stages_to_profiles,
)
from realmock.platform.services.pipeline.resolve import (
    _binding_config,
    _legacy_stage_config,
    _runtime_config_from_profile,
    get_provider_model_rows,
    profile_to_response,
)
from realmock.platform.services.pipeline.secrets import (
    SECRET_EXTRA_KEYS,
    SECRET_KEEP,
    maybe_encrypt,
    parse_json,
    public_extras,
    runtime_extras,
)
from realmock.platform.services.pipeline.stages import (
    STAGES,
    get_all_stage_configs,
    get_or_create_stage_config,
    stage_to_response,
)

__all__ = [
    "STAGES",
    "TASK_BY_STAGE",
    "STAGE_BY_TASK",
    "DEFAULT_FALLBACK",
    "SECRET_KEEP",
    "SECRET_EXTRA_KEYS",
    "maybe_encrypt",
    "parse_json",
    "public_extras",
    "runtime_extras",
    "get_or_create_stage_config",
    "get_all_stage_configs",
    "stage_to_response",
    "update_stage_config",
    "get_stage_config_map",
    "get_llm_settings_row",
    "migrate_legacy_to_stages",
    "allocate_provider_name",
    "drop_legacy_provider_columns",
    "ensure_provider_channels",
    "migrate_stages_to_profiles",
    "get_provider_model_rows",
    "profile_to_response",
    "resolve_model_config",
    "get_stage_config_for_runtime",
    "ensure_pipeline_migrated",
]


def update_stage_config(db: Session, stage: str, data: Any) -> StageConfig:
    row = get_or_create_stage_config(db, stage)
    caps = data.capabilities if data.capabilities else None
    fallback = data.fallback if data.fallback else None

    row.provider = data.provider or ""
    row.api_base = data.api_base or ""
    row.api_key = maybe_encrypt(data.api_key, row.api_key or "")
    row.protocol = data.protocol or DEFAULT_LLM_PROTOCOL
    row.model = data.model or ""
    row.max_tokens = data.max_tokens
    row.context_window = data.context_window
    if caps:
        row.supports_vision = bool(caps.supports_vision)
        row.supports_audio_input = bool(caps.supports_audio_input)
        row.supports_audio_output = bool(caps.supports_audio_output)
        row.supports_video_input = bool(caps.supports_video_input)
    if fallback:
        row.fallback_handler = fallback.handler or ""
        row.fallback_mode = fallback.mode or ""
    old_extras = parse_json(row.extras)
    new_extras = dict(old_extras)
    for key, value in (data.extras or {}).items():
        if key in SECRET_EXTRA_KEYS and value in (None, "", SECRET_KEEP):
            continue
        new_extras[key] = value
    for key in SECRET_EXTRA_KEYS:
        value = new_extras.get(key)
        if value and not str(value).startswith("enc:"):
            new_extras[key] = encrypt_secret(str(value)) or ""
    new_extras["source"] = "stage"
    row.extras = json.dumps(new_extras, ensure_ascii=False)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def get_stage_config_map(db: Session) -> dict[str, dict[str, Any]]:
    rows = get_all_stage_configs(db)
    # Migrate old tables by stages to avoid blocking other empty stages from being migrated when one stage is configured, and also to avoid
    # Overwrite custom configurations that have been saved but do not have a provider name filled in.
    if get_llm_settings_row(db) and any(
        not row.provider and not row.api_base and not row.model and not row.api_key
        for row in rows.values()
    ):
        rows = migrate_legacy_to_stages(db)
    return {stage: stage_to_response(row) for stage, row in rows.items()}


def get_stage_config_for_runtime(
    db: Session, stage: str, *, profile_id: int | None = None
) -> dict[str, Any]:
    """Compatibility entry point: all downstream components (LLM/STT/TTS/context compaction) obtain runtime configuration here.

    Internally, this now uses the model entry system (task_bindings → provider+entry) and supports
    scenario-level ``profile_id`` overrides; when the system is not enabled, it falls back to the legacy stage_configs path.
    """
    return resolve_model_config(db, stage, profile_id=profile_id)


def resolve_model_config(
    db: Session,
    stage: str,
    *,
    profile_id: int | None = None,
) -> dict[str, Any]:
    """Unified entry point for runtime model configuration.

    - An explicit ``profile_id`` (scenario override) → assemble that entry directly;
    - Otherwise, use the task binding (chat/stt/tts);
    - If the profile system is disabled or the entry is missing → fall back to the legacy stage_configs / llm_settings path.
    """
    task = TASK_BY_STAGE.get(stage, stage)
    if profile_id is not None:
        profile = db.query(ModelProfile).filter(ModelProfile.id == profile_id).first()
        if profile is not None:
            provider = db.query(LlmProvider).filter(LlmProvider.id == profile.provider_id).first()
            return _runtime_config_from_profile(db, profile, provider, stage)
    migrate_stages_to_profiles(db)
    config = _binding_config(db, task, stage)
    if config is not None:
        return config
    return _legacy_stage_config(db, stage)


def ensure_pipeline_migrated(db: Session) -> None:
    """One-time startup migration: legacy ``llm_settings`` → ``stage_configs`` → model entries + task bindings,
    then flat provider columns / split-provider rows → per-kind channels, finally physical
    removal of the superseded flat columns."""
    rows = get_all_stage_configs(db)
    if get_llm_settings_row(db) and any(
        not row.provider and not row.api_base and not row.model and not row.api_key
        for row in rows.values()
    ):
        migrate_legacy_to_stages(db)
    migrate_stages_to_profiles(db)
    ensure_provider_channels(db)
    drop_legacy_provider_columns(db)


# History alias (same as get_stage_config_for_runtime)
get_stage_config_for_runtime_v2 = get_stage_config_for_runtime
