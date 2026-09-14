"""Persistence and public view for the ``stage_configs`` table (secrets are not exposed).

The legacy table is retained for rollback safety; runtime has switched to the model-entry system. This module handles
seeding the legacy path, backfilling compatible empty records, and constructing the response view.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from realmock.platform.core.constants import DEFAULT_LLM_PROTOCOL, PipelineStage
from realmock.platform.models import StageConfig
from realmock.platform.services.pipeline.secrets import parse_json, public_extras

STAGES = [PipelineStage.RECOGNIZE, PipelineStage.REASON, PipelineStage.SPEAK]


def _empty_stage(stage: str) -> StageConfig:
    return StageConfig(stage=stage)


def get_or_create_stage_config(db: Session, stage: str) -> StageConfig:
    row = db.query(StageConfig).filter(StageConfig.stage == stage).first()
    if not row:
        row = StageConfig(
            stage=stage,
            supports_audio_input=stage == PipelineStage.RECOGNIZE,
            supports_audio_output=stage in (PipelineStage.REASON, PipelineStage.SPEAK),
            fallback_handler=("local" if stage == PipelineStage.RECOGNIZE else "edge" if stage == PipelineStage.SPEAK else ""),
            fallback_mode=("transcribe" if stage == PipelineStage.RECOGNIZE else "tts_from_text" if stage == PipelineStage.SPEAK else ""),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    elif not row.provider and not row.api_base and not row.model:
        # Compatible with earlier empty records that were created without dynamic default values.
        changed = False
        if stage == PipelineStage.RECOGNIZE and not row.supports_audio_input:
            row.supports_audio_input = True
            changed = True
        if stage in (PipelineStage.REASON, PipelineStage.SPEAK) and not row.supports_audio_output:
            row.supports_audio_output = True
            changed = True
        if stage == PipelineStage.RECOGNIZE and not row.fallback_handler:
            row.fallback_handler = "local"
            row.fallback_mode = "transcribe"
            changed = True
        if stage == PipelineStage.SPEAK and not row.fallback_handler:
            row.fallback_handler = "edge"
            row.fallback_mode = "tts_from_text"
            changed = True
        if changed:
            db.commit()
            db.refresh(row)
    return row


def load_stage_configs(db: Session) -> dict[str, StageConfig]:
    """Read the three stage configurations without mutation; fill missing stages with in-memory default instances, **without writing to the database**.

    Used by read paths such as runtime fallback resolution (`_legacy_stage_config`) to avoid the write side effect of an implicit
    ``get_or_create`` + commit; when persisted seed semantics are required, use
    :func:`get_all_stage_configs`.

    .. warning::

        In-memory fill-in instances have **not been flushed, so column defaults (max_tokens, etc.) do not apply**,
        and accessing them returns None; consumers must provide their own fallback (see ``_legacy_stage_config``).
    """
    rows = {row.stage: row for row in db.query(StageConfig).all()}
    for stage in STAGES:
        if stage not in rows:
            rows[stage] = _empty_stage(stage)
    return rows


def get_all_stage_configs(db: Session) -> dict[str, StageConfig]:
    """Load and ensure three-stage rows exist (drop library creation when missing) - write semantics for configuration pages/migrations."""
    rows = {row.stage: row for row in db.query(StageConfig).all()}
    for stage in STAGES:
        if stage not in rows:
            rows[stage] = get_or_create_stage_config(db, stage)
    return rows


def stage_to_response(row: StageConfig) -> dict[str, Any]:
    return {
        "stage": row.stage,
        "provider": row.provider or "",
        "api_base": row.api_base or "",
        "protocol": row.protocol or DEFAULT_LLM_PROTOCOL,
        "model": row.model or "",
        "max_tokens": row.max_tokens,
        "context_window": row.context_window,
        "capabilities": {
            "supports_vision": bool(row.supports_vision),
            "supports_audio_input": bool(row.supports_audio_input),
            "supports_audio_output": bool(row.supports_audio_output),
            "supports_video_input": bool(row.supports_video_input),
        },
        "fallback": {
            "handler": row.fallback_handler or "",
            "mode": row.fallback_mode or "",
        },
        "extras": public_extras(parse_json(row.extras)),
        "has_api_key": bool(row.api_key),
        "updated_at": row.updated_at,
    }
